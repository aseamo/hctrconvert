"""
HctrConvert — Custom Exceptions
───────────────────────────────
Define application-specific exceptions with HTTP status codes.

SOFTWARE ENGINEERING PRINCIPLE: "Explicit error taxonomy"
- Each failure mode gets its own exception class
- The error handler maps them to proper HTTP responses
- Business logic never imports FastAPI's HTTPException directly
"""
from __future__ import annotations


class HctrConvertError(Exception):
    """Base exception for all HctrConvert errors."""
    status_code: int = 500
    detail: str = "An internal error occurred."

    def __init__(self, detail: str | None = None, status_code: int | None = None):
        self.detail = detail or self.__class__.detail
        if status_code:
            self.status_code = status_code
        super().__init__(self.detail)


class FileTooLargeError(HctrConvertError):
    status_code = 413
    detail = "File exceeds the maximum allowed size."


class UnsupportedFormatError(HctrConvertError):
    status_code = 415
    detail = "The uploaded file format is not supported."


class InvalidTargetFormatError(HctrConvertError):
    status_code = 422
    detail = "The requested target format is invalid."


class ConversionError(HctrConvertError):
    status_code = 500
    detail = "File conversion failed."


class DependencyMissingError(HctrConvertError):
    status_code = 501
    detail = "A required system dependency is not installed."
