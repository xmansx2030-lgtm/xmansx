"""تخزين خاص للمستندات المولدة (البنود 55-57).

**خارج MEDIA_ROOT عمدًا**: إعدادات التطوير تخدم `MEDIA_URL` عبر `static()`،
فأي ملف داخلها يصبح قابلًا للتنزيل بلا مصادقة. مخزن المستندات بلا `base_url`
إطلاقًا — استدعاء `.url` يرفع استثناءً، فلا رابط عام دائم حتى بالخطأ. التنزيل
الوحيد الممكن عبر endpoint مصادق ومحدود بالمستأجر والدور.
"""

from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage, storages
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDocumentStorage(Storage):
    """Proxy to the configured private-document storage.

    Development uses a filesystem outside ``MEDIA_ROOT`` while production uses
    the private R2 bucket. The local backend is built at use time so
    ``override_settings(GENERATED_DOCUMENTS_ROOT=...)`` remains effective.
    """

    @property
    def backend(self):
        if settings.R2_ENABLED:
            return storages["private_documents"]
        return FileSystemStorage(location=settings.GENERATED_DOCUMENTS_ROOT, base_url=None)

    def _open(self, name, mode="rb"):
        return self.backend.open(name, mode)

    def _save(self, name, content):
        return self.backend.save(name, content)

    def delete(self, name):
        return self.backend.delete(name)

    def exists(self, name):
        return self.backend.exists(name)

    def listdir(self, path):
        return self.backend.listdir(path)

    def size(self, name):
        return self.backend.size(name)

    def path(self, name):
        return self.backend.path(name)

    def get_accessed_time(self, name):
        return self.backend.get_accessed_time(name)

    def get_created_time(self, name):
        return self.backend.get_created_time(name)

    def get_modified_time(self, name):
        return self.backend.get_modified_time(name)

    def url(self, name):
        """لا رابط عام إطلاقًا.

        الرفض الصريح يمنع كشف رابط دائم سواء كان المخزن محليًا أو R2.
        """
        raise ValueError(
            "المستندات المولدة لا تملك رابطاً عاماً — التنزيل عبر endpoint مصرح فقط."
        )

    def __eq__(self, other):  # deconstruct مستقر بين الهجرات
        return isinstance(other, PrivateDocumentStorage)

    def __hash__(self):
        return hash(self.__class__)


def generated_document_path(instance, filename: str) -> str:
    """مفتاح تخزين عشوائي: لا اسم طالب ولا نوع مستند في المسار (البند 56)."""
    return f"school_{instance.school_id}/{uuid4().hex}.pdf"
