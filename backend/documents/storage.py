"""تخزين خاص للمستندات المولدة (البنود 55-57).

**خارج MEDIA_ROOT عمدًا**: إعدادات التطوير تخدم `MEDIA_URL` عبر `static()`،
فأي ملف داخلها يصبح قابلًا للتنزيل بلا مصادقة. مخزن المستندات بلا `base_url`
إطلاقًا — استدعاء `.url` يرفع استثناءً، فلا رابط عام دائم حتى بالخطأ. التنزيل
الوحيد الممكن عبر endpoint مصادق ومحدود بالمستأجر والدور.
"""

import os
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateDocumentStorage(FileSystemStorage):
    """مسار الجذر يقرأ من الإعدادات **وقت الاستخدام** لا وقت الاستيراد.

    ‏FileSystemStorage يخزن الجذر في cached_property؛ استبدالها بخاصية عادية
    يجعل `override_settings` في الاختبارات فعالة بلا إعادة تحميل الوحدة.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(**kwargs)

    @property
    def base_location(self):
        return self._value_or_setting(self._location, settings.GENERATED_DOCUMENTS_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        """لا رابط عام إطلاقًا.

        ‏`FileSystemStorage.base_url` يرجع إلى `MEDIA_URL` عند تمرير None، فيولد
        رابطًا يوحي بإمكان التنزيل المباشر. الرفض الصريح يجعل أي محاولة ربط في
        الواجهة تفشل وقت التطوير لا وقت التسريب.
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
