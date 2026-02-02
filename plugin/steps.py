"""Custom steps for pdf-to-image upload plugin."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import pymupdf

from synapse_sdk.plugins.actions.upload.context import UploadContext
from synapse_sdk.plugins.steps import BaseStep, StepResult


class ExtractPdfImagesStep(BaseStep[UploadContext]):
    """Extract images from PDF files and replace organized_files with image entries.

    Each page of a PDF file is rendered as a separate image file (PNG or JPG)
    with PDF metadata preserved.

    Reads extra_params from context:
        - output_format (str): Output image format ('png' or 'jpg'). Default: 'png'.
        - dpi (int): Rendering resolution in DPI. Default: 200.
        - group_name (str | None): Group name to assign to all data units.
    """

    PDF_EXTENSIONS = {'.pdf'}

    @property
    def name(self) -> str:
        return 'extract_pdf_images'

    @property
    def progress_weight(self) -> float:
        return 0.15

    def can_skip(self, context: UploadContext) -> bool:
        """Skip if no PDF files found in organized_files."""
        for file_group in context.organized_files:
            for file_path in file_group.get('files', {}).values():
                if isinstance(file_path, list):
                    file_path = file_path[0] if file_path else None
                if file_path and Path(file_path).suffix.lower() in self.PDF_EXTENSIONS:
                    return False
        return True

    def execute(self, context: UploadContext) -> StepResult:
        extra = context.params.get('extra_params') or {}
        output_format = extra.get('output_format', 'png')
        dpi = int(extra.get('dpi', 200))
        group_name = extra.get('group_name')

        temp_dir = self._create_temp_directory(context)
        processed_files: list[dict[str, Any]] = []
        total_images_extracted = 0

        try:
            for file_group in context.organized_files:
                files_dict = file_group.get('files', {})
                meta = file_group.get('meta', {})

                for spec_name, file_path in files_dict.items():
                    if isinstance(file_path, list):
                        file_path = file_path[0] if file_path else None
                    if file_path is None:
                        continue

                    file_path = Path(file_path)
                    if file_path.suffix.lower() not in self.PDF_EXTENSIONS:
                        processed_files.append(file_group)
                        continue

                    extracted_images, pdf_metadata = self._extract_images(
                        file_path, temp_dir, output_format, dpi, context,
                    )

                    if not extracted_images:
                        context.log(
                            'pdf_image_extraction_skip',
                            {'file': file_path.name, 'reason': 'no images extracted'},
                        )
                        continue

                    page_count = len(extracted_images)
                    for i, image_path in enumerate(extracted_images):
                        page_meta: dict[str, Any] = {
                            **meta,
                            'origin_file_name': file_path.name,
                            'origin_file_format': 'pdf',
                            'origin_pdf_path': str(file_path),
                            **pdf_metadata,
                            'page_count': page_count,
                            'page_index': i + 1,
                            'dpi': dpi,
                            'output_format': output_format,
                        }

                        entry: dict[str, Any] = {
                            'files': {spec_name: Path(image_path)},
                            'meta': page_meta,
                        }
                        if group_name:
                            entry['groups'] = [group_name]

                        processed_files.append(entry)

                    total_images_extracted += page_count

            context.organized_files = processed_files

            context.params['cleanup_temp'] = True
            context.params['temp_path'] = str(temp_dir)

            context.log(
                'pdf_image_extraction_complete',
                {'total_images': total_images_extracted, 'total_entries': len(processed_files)},
            )

            return StepResult(
                success=True,
                data={'images_extracted': total_images_extracted},
                rollback_data={'temp_dir': str(temp_dir)},
            )

        except Exception as e:
            return StepResult(success=False, error=f'PDF image extraction failed: {e}')

    def rollback(self, context: UploadContext, result: StepResult) -> None:
        temp_dir = result.rollback_data.get('temp_dir')
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_temp_directory(self, context: UploadContext) -> Path:
        base = context.pathlib_cwd if context.pathlib_cwd else Path(os.getcwd())
        temp_dir = base / 'temp_pdf_images'
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def _get_pdf_metadata(self, doc: pymupdf.Document) -> dict[str, Any]:
        """Extract metadata from a PDF document."""
        metadata: dict[str, Any] = {}

        pdf_meta = doc.metadata or {}
        meta_fields = {
            'title': 'title',
            'author': 'author',
            'subject': 'subject',
            'creator': 'creator',
            'producer': 'producer',
            'creationDate': 'creation_date',
            'modDate': 'modification_date',
        }
        for pdf_key, meta_key in meta_fields.items():
            value = pdf_meta.get(pdf_key)
            if value:
                metadata[meta_key] = value

        if doc.page_count > 0:
            first_page = doc[0]
            rect = first_page.rect
            metadata['page_width'] = round(rect.width, 2)
            metadata['page_height'] = round(rect.height, 2)

        return metadata

    def _extract_images(
        self,
        pdf_path: Path,
        output_dir: Path,
        output_format: str,
        dpi: int,
        context: UploadContext,
    ) -> tuple[list[str], dict[str, Any]]:
        """Extract images from a single PDF file.

        Returns:
            (list of extracted image paths, PDF metadata dict)
        """
        try:
            doc = pymupdf.open(str(pdf_path))
        except Exception:
            return [], {}

        try:
            pdf_metadata = self._get_pdf_metadata(doc)
            total_pages = doc.page_count

            if total_pages == 0:
                return [], pdf_metadata

            ext = f'.{output_format}'
            pil_format = 'jpeg' if output_format == 'jpg' else 'png'
            stem = pdf_path.stem
            zoom = dpi / 72.0
            matrix = pymupdf.Matrix(zoom, zoom)

            extracted_files: list[str] = []

            for i in range(total_pages):
                try:
                    page = doc[i]
                    pix = page.get_pixmap(matrix=matrix)

                    page_filename = f'{stem}_{i:04d}{ext}'
                    page_path = output_dir / page_filename

                    if pil_format == 'png':
                        pix.save(str(page_path))
                    else:
                        pix.pil_save(str(page_path), format='JPEG')

                    extracted_files.append(str(page_path))

                    if (i + 1) % 50 == 0:
                        progress = ((i + 1) / total_pages) * 100
                        context.log(
                            'pdf_image_extraction_progress',
                            {'file': pdf_path.name, 'pages': i + 1, 'progress': f'{progress:.1f}%'},
                        )

                except Exception:
                    continue

            context.log(
                'pdf_images_extracted',
                {'file': pdf_path.name, 'total_images': len(extracted_files)},
            )
            return extracted_files, pdf_metadata

        except Exception:
            return [], {}
        finally:
            doc.close()
