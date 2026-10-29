"""Shared persisted citation-metadata bounds, checked before embedding dispatch."""

from app.core.errors import UploadValidationError

SOURCE_FILE_MAX_LENGTH = 200
SECTION_TITLE_MAX_LENGTH = 300


def validate_storage_metadata(source_file: str, section_title: str) -> None:
    # Reject rather than truncate: truncation changes citation identity and hashes.
    if len(source_file) > SOURCE_FILE_MAX_LENGTH:
        raise UploadValidationError("Tên tệp tài liệu không được vượt quá 200 ký tự.")
    if len(section_title) > SECTION_TITLE_MAX_LENGTH:
        raise UploadValidationError("Đường dẫn tiêu đề tài liệu không được vượt quá 300 ký tự.")
