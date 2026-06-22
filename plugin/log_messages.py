"""User-facing log message codes for the pdf-to-image upload plugin.

These codes are sent as event='message' so they show up in the joblog (backend
UI), unlike context.log events which only appear in the ray job console. Each
code carries its UI level; templates are registered at import time.
"""

from __future__ import annotations

from synapse_sdk.plugins.log_messages import LogMessageCode, register_log_messages


class PdfLogMessageCode(LogMessageCode):
    """Log message codes for PDF preprocessing."""

    PDF_LOCKED_FILTERED = ('PDF_LOCKED_FILTERED', 'warning')


register_log_messages({
    PdfLogMessageCode.PDF_LOCKED_FILTERED: (
        '잠긴(암호로 보호된) PDF "{file}" 은(는) 처리할 수 없어 업로드에서 제외되었습니다.'
    ),
})


__all__ = ['PdfLogMessageCode']
