"""قراءة ملف نور xlsx بأمان — المنطق المشترك في common/excel_security (المرحلة 5).

هذا الملف شيم توافق يحافظ على واجهة المرحلة 4 كما هي.
"""

from common.excel_security import (  # noqa: F401  (إعادة تصدير مقصودة)
    INVALID_FILE_MESSAGE,
    TOO_LARGE_MESSAGE,
    UNSUPPORTED_MESSAGE,
    read_headers,
    read_rows,
    validate_upload,
)
