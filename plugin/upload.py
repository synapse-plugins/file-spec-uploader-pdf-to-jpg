"""Upload action for pdf-to-image-uploader."""

from __future__ import annotations

from plugin.steps import ExtractPdfImagesStep
from synapse_sdk.plugins.actions.upload import (
    DefaultUploadAction,
    UploadContext,
    UploadParams,
)
from synapse_sdk.plugins.steps import StepRegistry


class UploadAction(DefaultUploadAction[UploadParams]):
    """Upload action that extracts images from PDF files before upload.

    Extends the standard 8-step workflow by inserting an ExtractPdfImagesStep
    after organize_files. The custom step renders each PDF page as an individual
    image file (PNG/JPG) using PyMuPDF and replaces organized_files with image entries.

    Extra params (via config.yaml ui_schema):
        - output_format: Output image format (png / jpg)
        - dpi: Rendering resolution in DPI (default: 200)
        - group_name: Group name to assign to all data units
    """

    action_name = 'upload'
    params_model = UploadParams

    def setup_steps(self, registry: StepRegistry[UploadContext]) -> None:
        super().setup_steps(registry)
        registry.insert_after('organize_files', ExtractPdfImagesStep())
