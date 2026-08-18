# المصادقة — كما نفذت في المرحلة 2

## تطبيع رقم الجوال

المصدر الوحيد: `accounts/mobile.py` — ممنوع تكرار المنطق في Serializers.

| الإدخال | الناتج |
|---|---|
| `0551234567` / `551234567` / `966551234567` / `+966551234567` / `00966551234567` | `+966551234567` |
| أرقام عربية `٠٥٥...`، فواصل/شرطات | تُحوّل ثم تُطبّع |
| أي صيغة أخرى (دولة أخرى، طول خاطئ، ليس 5xx) | `ValidationError` برسالة عربية |

- `normalize_mobile(raw)` — للتطبيع عند الدخول/الإنشاء.
- `validate_mobile(value)` — validator للنموذج: يقبل الصيغة الموحدة فقط (التخزين مطبّع دائمًا).
- `mask_mobile(value)` — `+9665****4567` للسجلات (لا رقم كامل في Logs/Audit).
- `User.mobile` فريد **عالميًا** (unique) — الحساب عالمي وليس لكل مدرسة.

## كلمات المرور

- **Argon2id** أول `PASSWORD_HASHERS` (`argon2-cffi`) — تحقق فعلي: hash يبدأ بـ `argon2$argon2id$`.
- Django password framework حصرًا — لا تخزين ولا مقارنة يدوية.
- كلمة المرور لا تظهر أبدًا في: API responses، Logs، Audit metadata (حارس `_SENSITIVE_KEYS` في `audit/services.py`)، رسائل الأخطاء.

## تدفق الدخول

```text
GET  /api/v1/auth/csrf/        ← CSRF bootstrap للـ SPA (ensure_csrf_cookie، لا أسرار)
POST /api/v1/auth/login/       ← {mobile, password} + X-CSRFToken
      تطبيع الجوال → rate limit precheck → authenticate → login()
      login() يدوّر مفتاح الجلسة (session fixation protection)
      عضوية فعالة واحدة بمدرسة نشطة → active_school تلقائيًا
      الاستجابة = payload /me الكامل
POST /api/v1/auth/logout/      ← flush كامل للجلسة
GET  /api/v1/auth/me/          ← المستخدم + المدرسة النشطة + العضويات + الأدوار
GET  /api/v1/auth/schools/     ← عضويات المستخدم الحالي حصرًا (لا user_id من العميل)
POST /api/v1/session/active-school/ ← switch (انظر MULTI_TENANCY.md)
```

## الجلسات والـ Cookies

- Django Sessions (DB-backed) عبر Cookies: `HttpOnly`, `SameSite=Lax`، و`Secure` في الإنتاج.
- CSRF مفروض على **كل** العمليات المعدلة بما فيها login (`csrf_protect` صراحة).
- لا JWT ولا LocalStorage — نهائيًا (ADR-004).
- تدوير المفتاح: عند الدخول (`login()`) وعند تبديل المدرسة (`cycle_key()`).

## Rate Limiting (`accounts/rate_limit.py` عبر Redis cache)

| المفتاح | الحد الافتراضي | السلوك |
|---|---|---|
| `login:ip:<ip>` | 20 محاولة / 5 دقائق | كل المحاولات (نجاح أو فشل) |
| `login:mobile:<sha256>` | 5 محاولات فاشلة / 5 دقائق | يصفر عند النجاح — لا lockout دائم |

التجاوز → `429 LOGIN_RATE_LIMITED` برسالة عربية عامة. الجوال يخزن كـ sha256 في مفاتيح Redis.

## منع User Enumeration

رد واحد حرفيًا (`401 INVALID_CREDENTIALS` — «رقم الجوال أو كلمة المرور غير صحيحة.») للحالات الثلاث: رقم غير موجود، كلمة مرور خاطئة، حساب معطل. مغطى باختبار يقارن الردود بالبايت.

## Audit

`LOGIN_SUCCESS`, `LOGIN_FAILED` (بجوال مقنّع فقط), `LOGOUT`, `SWITCH_SCHOOL` — في `AuditLog` append-only (Admin قراءة فقط).

## createsuperuser

يعمل بالجوال (أمر مخصص في `accounts/management/commands/` يطبّع الإدخال). مجرب فعليًا:
`manage.py createsuperuser --noinput --mobile 05XXXXXXXX` مع `DJANGO_SUPERUSER_PASSWORD`.

## كلمة المرور المؤقتة (المرحلة 5)

- الحسابات الجديدة من استيراد المعلمين: كلمة مؤقتة (`secrets`) + `User.must_change_password=True`.
- البوابة: `must_change_password` يمنع كل الـ APIs المدرسية والتبديل (رمز `INITIAL_PASSWORD_CHANGE_REQUIRED`) حتى `POST /api/v1/auth/change-initial-password/` (كلمة حالية + جديدة + تأكيد؛ سياسة: ≥8، ليست أرقامًا فقط، ليست الجوال؛ رسائل عربية) ثم `update_session_auth_hash` + تدوير الجلسة + Audit.
- التغيير **عالمي** (يخص User لا مدرسة) — مدير المدرسة لا يعيد تعيين كلمات مرور مستخدمين موجودين (تمس مدارسهم الأخرى).

## خارج نطاق المرحلة (بقرار)

لا Password Reset عام ولا OTP/SMS ولا Self-Registration — الحسابات من Admin أو `seed_dev` أو استيراد المعلمين. إعادة إصدار كلمة مؤقتة/استرجاع الحساب: ميزة مستقبلية موثقة.
