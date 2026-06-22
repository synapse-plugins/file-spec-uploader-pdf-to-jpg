"""Tests for locked (password-protected) PDF handling during image extraction."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from plugin.steps import ExtractPdfImagesStep


class RecordingContext:
    """Minimal context stub that records logged events."""

    pathlib_cwd = None
    params: dict = {}

    def __init__(self) -> None:
        self.logs: list[tuple[str, dict]] = []

    def log(self, event: str, data: dict, file: str | None = None) -> None:
        self.logs.append((event, data))


def _make_locked_pdf(path: Path) -> None:
    """Create a password-protected (user-password) PDF at the given path."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'secret content')
    doc.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw='owner-secret',
        user_pw='user-secret',
    )
    doc.close()


def _make_plain_pdf(path: Path) -> None:
    """Create a normal, unencrypted single-page PDF at the given path."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'open content')
    doc.save(str(path))
    doc.close()


def test_locked_pdf_is_skipped_with_clear_log(tmp_path: Path) -> None:
    """A locked PDF should yield no images and emit an explicit 'pdf_locked' log."""
    pdf_path = tmp_path / 'locked.pdf'
    _make_locked_pdf(pdf_path)
    output_dir = tmp_path / 'out'
    output_dir.mkdir()

    step = ExtractPdfImagesStep()
    context = RecordingContext()

    images, metadata = step._extract_images(pdf_path, output_dir, 'png', 200, context)

    assert images == []
    logged_events = [event for event, _ in context.logs]
    assert 'pdf_locked' in logged_events


def test_plain_pdf_is_extracted_without_locked_log(tmp_path: Path) -> None:
    """A normal PDF should still extract images and never emit 'pdf_locked'."""
    pdf_path = tmp_path / 'plain.pdf'
    _make_plain_pdf(pdf_path)
    output_dir = tmp_path / 'out'
    output_dir.mkdir()

    step = ExtractPdfImagesStep()
    context = RecordingContext()

    images, metadata = step._extract_images(pdf_path, output_dir, 'png', 200, context)

    assert len(images) == 1
    logged_events = [event for event, _ in context.logs]
    assert 'pdf_locked' not in logged_events
