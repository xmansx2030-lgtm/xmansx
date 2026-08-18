# النموذج الأمني

> مرجع الأمان الملزم لكل المراحل. المرحلة 18 (Hardening) تراجع الالتزام ببنوده بندًا بندًا.

## 1. نموذج التهديد المختصر

| التهديد | السطح | الدفاع الأساسي |
|---|---|---|
| تسرب بيانات بين مدارس (أخطر تهديد) | أي استعلام غير محكوم | طبقات العزل الأربع (§2) + اختبارات عزل لكل endpoint |
| IDOR | معرفات رقمية في المسارات | فلترة `school` مركزية + Object-level checks |
| Brute force على الدخول | endpoint الدخول | Rate limiting (جوال+IP) + قفل تصاعدي + Argon2 |
| XSS | إدخالات نصية (أسماء، ملاحظات) | React escaping الافتراضي + CSP + عدم استخدام `dangerouslySetInnerHTML` |
| CSRF | Cookies-based auth | Django CSRF + SameSite=Lax |
| رفع ملفات خبيثة | مرفقات الأعذار وملفات Excel والشعارات | تحقق ثلاثي (§6) + تخزين خاص + Signed URLs |
| تسرب PII في السجلات | Logs / Audit / أخطاء | قواعد Logging (§8) + تقنيع الهوية |
| تصعيد صلاحيات | تعديل الأدوار | RBAC خادمي + Audit على ROLE_CHANGED |
| تزوير التاريخ | إنذارات ومستندات | Snapshots + append-only Audit (ADR-010) |

## 2. عزل المستأجرين (Tenant Isolation)

أربع طبقات متراكبة — سقوط واحدة لا يسقط العزل:

1. **Middleware:** يقرأ `active_school_id` من الجلسة (ليس من العميل)، يتحقق من `SchoolMembership` فعالة، ويثبت `request.school`. طلب مدرسي بلا مدرسة فعالة → 403 برمز `NO_ACTIVE_SCHOOL`.
2. **Managers:** `SchoolScopedManager.for_school(school)` هو المسار القياسي؛ `Model.all_schools` الصريح فقط للمنصة والمهام الخلفية (وكل استخدام له يوثق سببه).
3. **Base ViewSet:** فلترة `school=request.school` في مكان واحد موروث؛ الـ `perform_create` يحقن `school` من الطلب لا من البيانات.
4. **اختبارات:** لكل endpoint اختبار «مدرسة A لا ترى B» — إلزامي في تعريف Done لكل مرحلة.

قاعدة صلبة: **ممنوع** `Student.objects.all()` وأمثالها داخل مسارات المدارس، و**ممنوع** قبول `school_id` من العميل.

## 3. المصادقة والجلسات

- كلمات المرور: **Argon2id** (`argon2-cffi`) + سياسة حد أدنى للطول (8+) وفحص الشيوع؛ لا تخزين نصي أبدًا ولا في Logs.
- الجلسات: Cookies `HttpOnly`, `Secure`, `SameSite=Lax`؛ تدوير معرف الجلسة عند الدخول؛ انتهاء بالخمول؛ Logout يبطل الجلسة خادميًا.
- CSRF: قياسي من Django على كل عملية كتابية.
- Rate limiting دخول: حدود لكل جوال ولكل IP عبر Redis، مع تأخير تصاعدي، ورسالة موحدة لا تكشف وجود الحساب.
- لا JWT في LocalStorage؛ لا أسرار في bundle الواجهة.
- تبديل المدرسة: POST + CSRF + تحقق عضوية + حدث Audit `SWITCH_SCHOOL`.

## 4. حماية رقم الهوية (ADR-009) — ✅ نفذ في المرحلة 4 (التفصيل: IDENTIFIER_SECURITY.md)

- تخزين: `national_id_encrypted` (Fernet/AES، مفتاح بيئة قابل للتدوير عبر MultiFernet) + `national_id_lookup_hash` (HMAC-SHA256 بمفتاح ثانٍ منفصل) للبحث الدقيق والتكرارات.
- عرض: مفكوك فقط للأدوار المصرح لها؛ يظهر مقنعًا (`****3456`) في القوائم والسجلات.
- ممنوع: الرقم الكامل في Logs أو رسائل الخطأ أو الـ Audit metadata أو الـ URLs.
- تدوير المفاتيح: إضافة المفتاح الجديد أول قائمة MultiFernet → مهمة إعادة تشفير خلفية → إزالة القديم. مفتاح HMAC لا يُدوّر إلا بإعادة حساب كل الـ hashes (عملية موثقة ومجدولة).

## 5. صلاحيات وRBAC

انظر [PERMISSIONS.md](PERMISSIONS.md). الإنفاذ خادمي بالكامل: Permission Classes للدور + فحوص Object-level في الـ Services (جلسة المعلم، إحالة المنشئ، طلب المتابعة الموجه). الواجهة تخفي فقط.

## 6. الملفات المرفوعة

- التحقق: الحجم الأقصى (مثل 5MB للمرفق، 10MB للـ Excel) + قائمة امتدادات بيضاء (PDF/JPG/PNG؛ XLSX للاستيراد) + فحص MIME الفعلي (python-magic أو مكافئ) + تعقيم اسم الملف (يُستبدل باسم مولد UUID، الاسم الأصلي حقل بيانات).
- التخزين: Object Storage **خاص** (لا Public ACL)؛ الوصول عبر **Signed URLs** قصيرة العمر بعد فحص الصلاحية.
- ملفات Excel تُعالج في Celery داخل sandbox منطقي (قراءة فقط، حدود صفوف، مهلة زمنية) ولا تدخل قاعدة البيانات إلا بعد المعاينة والموافقة.

## 7. حماية النقل والرؤوس

- HTTPS فقط + إعادة توجيه + **HSTS**.
- **CSP** صارمة: `default-src 'self'`؛ لا سكربتات خارجية؛ الصور من self + Signed URLs.
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`.
- SQL Injection: ORM حصرًا؛ أي Raw SQL (تقارير) بمعاملات مربوطة فقط.

## 8. السجلات (Logging)

- Structured JSON logs: `request_id`, `user_id`, `school_id`, `action`, `duration`, `status`.
- **ممنوع في السجلات:** كلمات المرور، رقم الهوية الكامل، محتوى الملاحظات الإرشادية، محتوى المرفقات، الـ tokens.
- Production: لا Stack Traces للمستخدم؛ الأخطاء الداخلية → رمز عام + `request_id` للدعم، والتفاصيل إلى Sentry.
- Audit Log (وحدة audit) منفصل عن سجلات التشغيل: append-only، لا حذف ولا تعديل، ولا صلاحية حذف لأي دور.

## 9. أخطاء الـ API

نمط موحد:

```json
{ "code": "ATTENDANCE_ALREADY_SUBMITTED", "message": "تم اعتماد حضور هذا الفصل مسبقاً.", "details": {} }
```

- الرسائل عربية واضحة؛ الرموز إنجليزية ثابتة للواجهة.
- رسائل المصادقة لا تفرق بين «جوال غير موجود» و«كلمة مرور خاطئة».

## 10. التزامن (Concurrency)

- التحضير المزدوج: قيد Unique في قاعدة البيانات هو الحكم النهائي؛ التعارض يُلتقط ويُترجم لرسالة عربية.
- إصدار إنذار مرتين: قيد Unique `(school, student, kind, level, academic_year)` + `select_for_update` عند الفحص.
- اعتماد العذر مرتين: انتقال حالة ذري (`PENDING→APPROVED`) بشرط الحالة الحالية داخل `transaction.atomic` — Idempotent.
- مهام Celery كلها Idempotent (upsert / get_or_create بقيود فريدة).

## 11. الأسرار والبيئة

- كل الأسرار في متغيرات بيئة؛ `.env.example` بلا قيم حقيقية؛ لا أسرار في Git أبدًا.
- مفاتيح منفصلة: `SECRET_KEY`, `FIELD_ENCRYPTION_KEYS`, `NATIONAL_ID_HMAC_KEY`, بيانات DB/Redis/S3.
- CI يتضمن فحص أسرار (gitleaks أو مكافئ) وفحص التبعيات (`pip-audit`, `npm audit`).

## 12. الاشتراكات كضابط وصول

مدرسة `SUSPENDED`/`EXPIRED`: قراءة فقط (أو حجب كامل حسب الحالة) عبر Middleware — لا حذف بيانات أبدًا عند الإيقاف.
