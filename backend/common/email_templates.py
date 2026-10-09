"""Shared Arabic transactional mail presentation; no transport or tracking."""

from datetime import datetime
from html import escape
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

BRAND = "منصة المواظبة"
SUBSCRIPTION_TITLES = {
    "DETAILS": "تفاصيل اشتراك المدرسة",
    "REMINDER_7": "ينتهي اشتراك المدرسة خلال 7 أيام",
    "REMINDER_1": "ينتهي اشتراك المدرسة خلال يوم واحد",
    "GRACE_STARTED": "بدأت مهلة السماح لاشتراك المدرسة",
    "EXPIRED": "انتهى اشتراك المدرسة",
    "SUSPENDED": "تم إيقاف اشتراك المدرسة",
    "CANCELLED": "تم إلغاء اشتراك المدرسة",
}
_SUBSCRIPTION_COPY = {
    "DETAILS": ("اشتراك المدرسة", "إليك بيانات الاشتراك الحالية للمدرسة، "
                "لتكون تفاصيل الباقة والمدة واضحة وفي متناولك."),
    "REMINDER_7": ("تذكير بالاشتراك", "اقترب موعد نهاية اشتراك المدرسة. "
                   "راجع تاريخ الانتهاء والتفاصيل أدناه للتخطيط للتجديد في الوقت المناسب."),
    "REMINDER_1": ("تذكير بالاشتراك", "تبقّى يوم واحد أو أقل على نهاية اشتراك المدرسة. "
                   "راجع تفاصيل الاشتراك من حساب المدرسة."),
    "GRACE_STARTED": ("تحديث الاشتراك", "انتهت مدة الاشتراك وبدأت مهلة السماح. "
                      "راجع موعد نهاية المهلة أدناه وحالة الاشتراك في حساب المدرسة."),
    "EXPIRED": ("تحديث الاشتراك", "انتهى اشتراك المدرسة. يمكنك مراجعة الحالة "
                "والتفاصيل الحالية من صفحة الاشتراك في حساب المدرسة."),
    "SUSPENDED": ("تحديث الاشتراك", "تم إيقاف اشتراك المدرسة. "
                  "راجع صفحة الاشتراك في حساب المدرسة للاطلاع على الحالة الحالية."),
    "CANCELLED": ("تحديث الاشتراك", "تم إلغاء اشتراك المدرسة. "
                  "هذه الرسالة تعرض بيانات الاشتراك المرتبط بهذا التحديث."),
}
_FIELDS = (
    ("school_name", "المدرسة"), ("plan_name", "الباقة"), ("status_label", "الحالة"),
    ("starts_at", "بداية الاشتراك"), ("ends_at", "نهاية الاشتراك"),
    ("grace_ends_at", "نهاية مهلة السماح"), ("duration", "مدة الاشتراك"),
    ("price", "سعر الباقة"),
)


def _layout(*, subject, heading, category, introduction, details=(), action="", link="",
            notice="", guidance="", preheader=""):
    """Inline table layout remains readable without media queries or images."""
    e = escape
    rows = "".join(
        '<tr><td style="padding:12px 14px;border-bottom:1px solid #dce8e3;'
        'width:34%;vertical-align:top;color:#49615b;font-size:13px">'
        f'{e(label)}</td><td style="padding:12px 14px;border-bottom:1px solid #dce8e3;'
        'vertical-align:top;color:#16332e;font-weight:600;font-size:14px;'
        f'overflow-wrap:anywhere;word-break:break-word"><bdi>{e(str(value))}</bdi></td></tr>'
        for label, value in details
    )
    detail_html = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="width:100%;table-layout:fixed;border:1px solid #dce8e3;'
        f'background:#f4f8f6;border-radius:10px;margin:24px 0">{rows}</table>' if rows else ""
    )
    button = (
        '<table role="presentation" cellspacing="0" cellpadding="0" style="margin:24px 0">'
        '<tr><td bgcolor="#11786d" style="background:#11786d;border-radius:8px;text-align:center">'
        f'<a href="{e(link, quote=True)}" style="display:inline-block;padding:14px 24px;'
        'border:1px solid #11786d;border-radius:8px;color:#ffffff;font-weight:700;'
        f'font-size:16px;line-height:24px;text-decoration:none">{e(action)}</a></td></tr></table>'
        if action and link else ""
    )
    notice_html = (
        '<p style="padding:16px;background:#faf5eb;border-right:3px solid #a56a22;'
        f'border-radius:6px;color:#624417;font-size:14px;margin:24px 0">{e(notice)}</p>'
        if notice else ""
    )
    fallback = (
        '<p style="margin:24px 0 6px;color:#49615b;font-size:12px">'
        'إذا لم يعمل الزر، انسخ الرابط التالي وافتحه في المتصفح:</p>'
        f'<a href="{e(link, quote=True)}" dir="ltr" style="display:block;text-align:left;'
        'direction:ltr;overflow-wrap:anywhere;word-break:break-all;color:#11786d;'
        f'font-size:12px;line-height:20px">{e(link)}</a>' if link else ""
    )
    html = (
        '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{e(subject)}</title><style>@media screen and (max-width:480px)'
        '{.email-content{padding:24px 20px!important}.email-shell{padding:16px 8px!important}'
        '.email-heading{font-size:25px!important}}</style></head>'
        '<body dir="rtl" style="margin:0;padding:0;background:#f4f8f6;color:#16332e;'
        'font-family:Tahoma,Arial,sans-serif;line-height:1.8;text-align:right">'
        '<div aria-hidden="true" style="display:none;max-height:0;overflow:hidden;'
        f'opacity:0;color:transparent;mso-hide:all">{e(preheader or introduction)}</div>'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'bgcolor="#f4f8f6"><tr><td class="email-shell" align="center" style="padding:32px 16px">'
        '<!--[if mso]><table role="presentation" width="600" align="center"><tr><td><![endif]-->'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="width:100%;max-width:600px;table-layout:fixed;background:#fffefd;'
        'border:1px solid #dce8e3;border-radius:16px;overflow:hidden">'
        '<tr><td bgcolor="#183c37" style="padding:26px 32px;background:#183c37;'
        'border-top:4px solid #a56a22;color:#ffffff;text-align:right">'
        '<p style="margin:0;font-size:25px;line-height:1.5;font-weight:700;color:#ffffff">'
        f'{BRAND}</p><p style="margin:4px 0 0;font-size:13px;color:#d5e9e3">'
        'إدارة مدرسية أكثر وضوحًا</p></td></tr>'
        '<tr><td class="email-content" style="padding:32px;text-align:right;'
        'overflow-wrap:anywhere;word-break:break-word">'
        '<p style="margin:0 0 12px;font-size:12px;font-weight:700;color:#11786d">'
        f'{e(category)}</p><h1 class="email-heading" style="margin:0 0 16px;'
        f'font-size:28px;line-height:1.5;color:#16332e">{e(heading)}</h1>'
        f'<p style="margin:0;font-size:16px;color:#49615b">{e(introduction)}</p>'
        f'{detail_html}{button}{notice_html}'
        f'<p style="margin:20px 0 0;color:#49615b;font-size:14px">{e(guidance)}</p>'
        f'{fallback}</td></tr><tr><td style="padding:20px 32px;border-top:1px solid #dce8e3;'
        'text-align:center;background:#eaf6f2"><p style="margin:0;color:#183c37;'
        f'font-size:13px;font-weight:700">{BRAND}</p><p style="margin:4px 0 0;'
        'color:#49615b;font-size:12px">رسالة آلية من المنصة</p></td></tr></table>'
        '<!--[if mso]></td></tr></table><![endif]--></td></tr></table></body></html>'
    )
    text = "\n\n".join(part for part in (
        BRAND, heading, introduction,
        "\n".join(f"{label}: {value}" for label, value in details),
        f"{action}:\n{link}" if action and link else "", notice, guidance,
        "رسالة آلية من منصة المواظبة",
    ) if part)
    return subject, text, html


def render_account_email(*, purpose, link, expires_at: datetime, school_name=""):
    if purpose == "RECOVERY_EMAIL_VERIFICATION":
        subject = "توثيق بريد الاسترداد — منصة المواظبة"
        heading, action = "توثيق بريد الاسترداد", "توثيق البريد الإلكتروني"
        introduction = (
            "طلبت توثيق هذا البريد ليكون وسيلتك لاستعادة كلمة المرور. "
            "افتح الرابط ثم أكمل التحقق صراحةً داخل المنصة."
        )
        category = "أمان الحساب"
    elif purpose == "PASSWORD_RESET":
        subject = "استعادة كلمة المرور — منصة المواظبة"
        heading, action = "إنشاء كلمة مرور جديدة", "إعادة تعيين كلمة المرور"
        introduction = (
            "وصلنا طلب لاستعادة كلمة مرور حسابك في منصة المواظبة. "
            "استخدم الرابط أدناه لإنشاء كلمة مرور جديدة."
        )
        category = "أمان الحساب"
    elif purpose == "PARENT_ACCOUNT_ACTIVATION":
        subject = f"تفعيل بوابة ولي الأمر وتوثيق البريد — {school_name}"
        heading, action = "تفعيل الحساب وتوثيق البريد", "تفعيل حساب ولي الأمر"
        introduction = (
            "وافقت المدرسة على طلب الربط. أكمل تفعيل حسابك وتوثيق بريدك "
            "لتتمكن من متابعة أبنائك. إن كان لديك حساب، سجل الدخول إلى حسابك الحالي."
        )
        category = "بوابة ولي الأمر"
    else:
        raise ValueError("Unsupported account email purpose")
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("Email expiry must include a timezone")
    expiry = expires_at.astimezone(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d، الساعة %H:%M")
    details = [("ينتهي الرابط", f"{expiry} (بتوقيت الرياض)")]
    if purpose == "PARENT_ACCOUNT_ACTIVATION":
        details.insert(0, ("المدرسة", school_name))
    return _layout(
        subject=subject, heading=heading, category=category, introduction=introduction,
        details=details, action=action, link=link,
        notice="إذا لم تطلب هذه العملية، تجاهل الرسالة. لن تتغير بيانات حسابك بمجرد فتح الرابط.",
        guidance="هذا الرابط مخصص لك. لا تشاركه مع أي شخص، وأكمل الإجراء قبل انتهاء صلاحيته.",
        preheader=f"{heading} — أكمل الإجراء من خلال الرابط المرفق قبل انتهاء صلاحيته.",
    )


def _subscription_link(origin):
    """An optional navigation link; bad configuration never changes delivery."""
    try:
        origin = str(origin or "").rstrip("/")
        parsed = urlsplit(origin)
        if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.path not in {"", "/"}
                or any(char.isspace() for char in origin)
                or not (parsed.scheme == "https" or parsed.scheme == "http"
                        and parsed.hostname in {"localhost", "127.0.0.1"})):
            return ""
        # Also reject malformed ports, even though urlsplit accepts them.
        if parsed.port == 0:
            return ""
        return f"{origin}/subscription"
    except ValueError:
        return ""


def render_subscription_email(kind, snapshot, *, portal_origin=""):
    heading = SUBSCRIPTION_TITLES[kind]
    category, introduction = _SUBSCRIPTION_COPY[kind]
    details = [(label, snapshot[key]) for key, label in _FIELDS if snapshot.get(key)]
    has_dates = any(snapshot.get(key) for key in ("starts_at", "ends_at", "grace_ends_at"))
    guidance = (
        "يمكنك مراجعة التفاصيل من صفحة الاشتراك داخل حساب المدرسة. "
        "بعد تسجيل الدخول، تأكد من اختيار المدرسة المذكورة في الرسالة."
    )
    if has_dates:
        guidance += " المواعيد المعروضة بتوقيت الرياض."
    return _layout(
        subject=f"{heading} — {BRAND}", heading=heading, category=category,
        introduction=introduction, details=details, action="مراجعة الاشتراك",
        link=_subscription_link(portal_origin), guidance=guidance,
        preheader=f"{heading} — راجع تفاصيل اشتراك المدرسة داخل حسابك.",
    )
