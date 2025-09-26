import copy
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from pdf2image import convert_from_path

from . import BaseUploader


class Uploader(BaseUploader):
    """Plugin upload action interface for organizing files.

    This class provides a template for plugin developers to implement
    their own file organization logic by inheriting from BaseUploader.

    Example usage:
        Override process_files() to implement custom file processing logic.
        Override validate_file_types() to implement custom validation rules.
        Override setup_directories() to create custom directory structures.
    """

    def __init__(
        self, run, path: Path, file_specification: List = None, organized_files: List = None, extra_params: Dict = None
    ):
        """Initialize the uploader with required parameters.

        Args:
            run: Plugin run object with logging capabilities.
            path: Path object pointing to the upload target directory.
            file_specification: List of specifications that define the structure of files to be uploaded.
            organized_files: List of pre-organized files based on the default logic.
            extra_params: Additional parameters for customization.
        """
        super().__init__(run, path, file_specification, organized_files, extra_params)

    def process_files(self, organized_files: List) -> List:
        """Process and transform files during upload.

        Override this method to implement custom file processing logic.
        This is the main method where plugin-specific logic should be implemented.

        Args:
            organized_files: List of organized file dictionaries from the workflow.

        Returns:
            List: The processed list of files ready for upload.
        """
        # Default implementation: return files as-is
        # Plugin developers should override this method for custom logic
        return organized_files

    def validate_file_types(self, organized_files: List) -> List:
        """Validate file types against specifications.

        This example shows how to use the BaseUploader's comprehensive validation logic.
        You can override this method for custom validation or call super() to use the base implementation.

        Args:
            organized_files: List of organized file dictionaries to validate.

        Returns:
            List: Filtered list containing only valid files that match specifications.
        """
        return super().validate_file_types(organized_files)

    def before_process(self, organized_files: List) -> List:
        """Convert PDF files to images before processing.

        This method overrides the base class before_process to convert any PDF files
        to PNG images using the pdf2image library.

        Args:
            organized_files: List of organized file dictionaries

        Returns:
            List: The organized files with PDFs converted to images
        """
        converted_files = []

        for file_group in organized_files:
            files_dict = file_group.get('files', {})
            pdf_converted = False

            for spec_name, file_path in files_dict.items():
                if isinstance(file_path, list):
                    file_path = file_path[0] if file_path else None

                if file_path and hasattr(file_path, 'suffix') and file_path.suffix.lower() == '.pdf':
                    try:
                        # Convert PDF to images
                        images = convert_from_path(str(file_path), dpi=200)

                        # Create temporary directory for converted images
                        temp_dir = Path(tempfile.mkdtemp())
                        total_pages = len(images)
                        # Create separate file groups for each page
                        for i, image in enumerate(images):
                            page_num = i + 1
                            image_path = temp_dir / f'{file_path.stem}_page_{page_num}.png'
                            image.save(str(image_path), 'PNG')

                            # Create new file group for this page
                            page_group = {'files': {}}
                            # Deep copy all non-file attributes from original group
                            for key, value in file_group.items():
                                if key != 'files':
                                    page_group[key] = copy.deepcopy(value)

                            # Add metadata for PDF conversion
                            if 'meta' not in page_group:
                                page_group['meta'] = {}
                            
                            page_group['meta']['total_pages'] = total_pages
                            page_group['meta']['page_number'] = page_num
                            page_group['meta']['original_filename'] = file_path.name
                            page_group['meta']['extraction_library'] = 'pdf2image'

                            # Add the converted image
                            page_group['files'][spec_name] = image_path
                            converted_files.append(page_group)

                            self.run.log_message(f'Converted PDF page {page_num} to: {image_path}')

                        msg = f'Successfully converted PDF {file_path} to {len(images)} separate file groups'
                        self.run.log_message(msg)
                        pdf_converted = True
                        break  # Exit the inner loop since we've processed the PDF

                    except Exception as e:
                        self.run.log_message(f'Error converting PDF {file_path}: {str(e)}')
                        # Keep original file if conversion fails
                        break

            # Only add the original group if no PDF was converted
            if not pdf_converted:
                converted_group = {'files': {}}
                # Copy non-file attributes
                for key, value in file_group.items():
                    if key != 'files':
                        converted_group[key] = value

                # Copy all files as-is
                for spec_name, file_path in files_dict.items():
                    converted_group['files'][spec_name] = file_path

                converted_files.append(converted_group)

        return converted_files

    def handle_upload_files(self) -> List[Dict[str, Any]]:
        """Executes the upload task using the base class implementation.

        Returns:
            List: The final list of organized files ready for upload
        """
        return super().handle_upload_files()

    def organize_files(self, organized_files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform and organize files based on plugin logic.

        Override this method to implement custom file organization logic.

        Args:
            organized_files: List of organized files from the default logic

        Returns:
            List of transformed organized files
        """
        return organized_files

    def filter_files(self, organized_file: Dict[str, Any]) -> bool:
        """Filter files based on custom criteria.

        Override this method to implement custom filtering logic.

        Args:
            organized_file: Single organized file to filter

        Returns:
            bool: True to include the file, False to filter it out
        """
        return True
