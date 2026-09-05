"""قواعد بيانات الدخول الأولية لموظفي المدرسة.

الحساب الجديد يبدأ برقم الجوال المحلي نفسه (05XXXXXXXX) ثم يُجبر على تغييره
قبل الوصول لأي وظيفة تشغيلية. لا تستخدم هذه القاعدة لإعادة ضبط حساب قائم.
"""

from accounts.mobile import normalize_mobile


def initial_password_from_mobile(mobile: str) -> str:
    """يعيد الصيغة المحلية الموحدة 05XXXXXXXX لاستخدامها مرة واحدة أوليًا."""
    normalized = normalize_mobile(mobile)
    return f"0{normalized.removeprefix('+966')}"
