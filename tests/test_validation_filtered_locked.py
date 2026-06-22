"""Tests that filtered (locked) PDFs are surfaced at the validation step."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from synapse_sdk.plugins.log_messages import LogMessageCode, resolve_log_message

from plugin.log_messages import PdfLogMessageCode
from plugin.steps import ExtractPdfImagesStep, ValidateExtractedFilesStep


class RecordingContext:
    """Minimal context stub that records logged events and keeps its own params."""

    pathlib_cwd = None

    def __init__(self) -> None:
        self.params: dict = {}
        self.logs: list[tuple[str, dict]] = []
        self.messages: list[tuple] = []

    def log(self, event: str, data: dict, file: str | None = None) -> None:
        self.logs.append((event, data))

    def log_message(self, message, context: str = 'info', **kwargs) -> None:
        self.messages.append((message, context, kwargs))


class StrictRuntimeContext(RecordingContext):
    """Faithfully mimics the production runtime's log_message contract.

    In production, a LogMessageCode is resolved and its level is mapped to a
    LogLevel enum (safe), while a plain-string level reaches the logger as a
    raw string and raises 'TypeError: level must be a LogLevel enum, got str'.
    Sending the joblog message via a LogMessageCode must therefore not crash.
    """

    def log_message(self, message, context: str = 'info', **kwargs) -> None:
        if isinstance(message, LogMessageCode):
            resolved, level = resolve_log_message(message, **kwargs)
            self.messages.append((resolved, level, kwargs))
            return
        raise TypeError('level must be a LogLevel enum, got str')


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


def test_extraction_records_filtered_locked_pdf(tmp_path: Path) -> None:
    """Skipping a locked PDF should record its name for the validation step."""
    pdf_path = tmp_path / 'locked.pdf'
    _make_locked_pdf(pdf_path)
    output_dir = tmp_path / 'out'
    output_dir.mkdir()

    step = ExtractPdfImagesStep()
    context = RecordingContext()

    step._extract_images(pdf_path, output_dir, 'png', 200, context)

    assert context.params.get('filtered_locked_pdfs') == ['locked.pdf']


def test_validation_logs_filtered_locked_pdf() -> None:
    """Validation should log each locked PDF that extraction filtered out."""
    step = ValidateExtractedFilesStep()
    context = RecordingContext()
    context.params['filtered_locked_pdfs'] = ['locked.pdf']

    step._log_filtered_locked_pdfs(context)

    locked_logs = [data for event, data in context.logs if event == 'pdf_locked_filtered']
    assert len(locked_logs) == 1
    assert locked_logs[0]['file'] == 'locked.pdf'


def test_locked_pdf_message_template_is_korean() -> None:
    """The joblog message code resolves to Korean text mentioning the count."""
    message, level = resolve_log_message(
        PdfLogMessageCode.PDF_LOCKED_FILTERED, count=3
    )
    assert '3' in message
    assert '제외' in message  # Korean: "excluded"
    assert level == 'warning'


def test_validation_sends_single_aggregate_joblog_message() -> None:
    """Validation sends ONE event=message with the count, plus per-file detail logs."""
    step = ValidateExtractedFilesStep()
    context = RecordingContext()
    context.params['filtered_locked_pdfs'] = ['a.pdf', 'b.pdf']

    step._log_filtered_locked_pdfs(context)

    # One aggregate joblog message carrying the total count.
    sent = [
        kwargs
        for message, _, kwargs in context.messages
        if message is PdfLogMessageCode.PDF_LOCKED_FILTERED
    ]
    assert len(sent) == 1
    assert sent[0].get('count') == 2

    # Per-file detail is still emitted for the log export.
    detail = [data for event, data in context.logs if event == 'pdf_locked_filtered']
    assert [d['file'] for d in detail] == ['a.pdf', 'b.pdf']


def test_validation_logging_survives_strict_logger() -> None:
    """The joblog message must use a LogMessageCode so the runtime never crashes."""
    step = ValidateExtractedFilesStep()
    context = StrictRuntimeContext()
    context.params['filtered_locked_pdfs'] = ['locked.pdf']

    # Must not raise: a plain-string level would raise in production, an enum won't.
    step._log_filtered_locked_pdfs(context)

    assert any(event == 'pdf_locked_filtered' for event, _ in context.logs)
    # The resolved Korean message reached the (strict) joblog logger.
    assert any('제외' in resolved for resolved, _, _ in context.messages)


def test_validation_logs_nothing_when_no_filtered_pdfs() -> None:
    """With no filtered PDFs recorded, validation emits no locked-filter log."""
    step = ValidateExtractedFilesStep()
    context = RecordingContext()

    step._log_filtered_locked_pdfs(context)

    assert not any(event == 'pdf_locked_filtered' for event, _ in context.logs)


def test_action_wires_validation_step_after_extraction() -> None:
    """UploadAction should replace the default validation with the locked-aware one."""
    from synapse_sdk.plugins.steps import StepRegistry

    from plugin.upload import UploadAction

    registry: StepRegistry = StepRegistry()
    # Bypass the action constructor (needs runtime params/ctx); setup_steps
    # only touches the registry.
    action = UploadAction.__new__(UploadAction)
    action.setup_steps(registry)

    steps = registry.get_steps()
    names = [s.name for s in steps]

    validate_steps = [s for s in steps if s.name == 'validate_files']
    assert len(validate_steps) == 1
    assert isinstance(validate_steps[0], ValidateExtractedFilesStep)
    # Validation runs immediately after the PDF extraction step.
    assert names.index('validate_files') == names.index('extract_pdf_images') + 1
