# PHASE 0 REPORT — Discovery & Architecture

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — المرحلة وثائقية بالكامل؛ لا كود ولا Migrations ولا اختبارات قابلة للتشغيل بعد (بالتصميم).

## What was implemented

1. **فحص المستودع:** المجلد `xmansx` فارغ تمامًا وغير مهيأ كـ Git repo — مشروع جديد من الصفر، لا بنية سابقة تفرض قيودًا ولا خطر على بيانات موجودة.
2. **مراجعة المتطلبات** (72 بندًا + 21 مرحلة) وتحويلها إلى: معمارية، 10 قرارات ADR، نموذج بيانات، مصفوفة صلاحيات، نموذج أمني، خطة مراحل باعتماديات ومعايير خروج.
3. **تصميم الوحدات:** 18 تطبيق Django بحدود Service/Selector صارمة + بنية Frontend Feature-Based.
4. **تصميم ERD:** ~35 كيانًا عبر 15 وحدة، مع القيود الفريدة الحرجة (منع التحضير المزدوج، منع الإنذار المزدوج، عزل الهوية) والفهارس الأساسية.
5. **تحديد:** استراتيجية Multi-Tenant (أربع طبقات إنفاذ)، تدفق المصادقة وتبديل المدرسة، حدود API (`/api/v1/` + OpenAPI + نمط خطأ موحد)، والنموذج الأمني الكامل.

## Files changed (كلها جديدة)

```text
README.md
PHASE_0_REPORT.md
docs/ARCHITECTURE.md
docs/ERD.md
docs/PERMISSIONS.md
docs/SECURITY.md
docs/PHASE_PLAN.md
docs/adr/ADR-001-modular-monolith.md
docs/adr/ADR-002-multi-tenancy.md
docs/adr/ADR-003-global-user-memberships.md
docs/adr/ADR-004-session-auth.md
docs/adr/ADR-005-no-teacher-timetable.md
docs/adr/ADR-006-attendance-by-exception.md
docs/adr/ADR-007-pwa-online-first.md
docs/adr/ADR-008-polling-not-websockets.md
docs/adr/ADR-009-national-id-protection.md
docs/adr/ADR-010-immutable-history.md
```

## Database changes

لا شيء (تصميم فقط). الـ ERD يحدد مسبقًا القيود التي ستمنع فئات كاملة من الأخطاء:
- `UNIQUE(school, section, date, period)` على AttendanceSession — منع التحضير المزدوج على مستوى قاعدة البيانات.
- `UNIQUE(school, student, kind, level, academic_year)` على StudentWarning — منع الإنذار المزدوج.
- `UNIQUE(school, national_id_lookup_hash)` — كشف تكرار الطلاب دون كشف الهوية.
- Partial unique على القيد الدراسي النشط والجدول الزمني النشط.

## API changes

لا شيء بعد. تم تثبيت: `/api/v1/`، OpenAPI (drf-spectacular)، نمط الخطأ `{code, message, details}` برسائل عربية، وعدم قبول `school_id` من العميل.

## UI changes

لا شيء بعد. تم تثبيت: Arabic-First / RTL-First، Mobile-First للمعلم، لوحات Responsive للوكيل، الصلاحيات في الواجهة عرضية فقط.

## Security checks

مراجعة تصميمية (لا كود يُفحص): نموذج تهديد مختصر، عزل بأربع طبقات، Argon2id + جلسات Cookies آمنة + CSRF + Rate limiting، تشفير الهوية + HMAC hash، قواعد ملفات (امتداد/MIME/حجم + Signed URLs)، قواعد Logging بلا PII، Audit append-only، ومعالجة التزامن بقيود قاعدة البيانات.

## Tests executed / Tests results

لا اختبارات قابلة للتشغيل في مرحلة وثائقية — **لم يُشغّل شيء ولم يُدّعَ نجاح شيء**. قائمة الاختبارات الإلزامية (العزل، متعدد المدارس، منع التحضير المزدوج، INCOMPLETE، فلتر الحصص المتعددة، ثبات الإنذارات، حدود الأدوار) موزعة على المراحل في PHASE_PLAN.md كمعايير خروج.

## Known limitations

- الـ ERD تصميمي: أطوال الحقول والـ null-ability النهائية تُثبت في Migrations كل مرحلة.
- قوائم الـ enums (أسباب الإحالة، أنواع الإجراءات) قد تُوسّع أثناء التنفيذ دون تغيير البنية.
- سيناريو انتقال طالب بين مدرستين داخل المنصة خارج نطاق MVP (الطالب كيان مدرسي).
- وصول الدعم الفني الاستثنائي لبيانات مدرسة (break-glass) مؤجل تصميمه عمدًا.

## Remaining work

المراحل 1–20 كاملة حسب [docs/PHASE_PLAN.md](docs/PHASE_PLAN.md). التالي مباشرة: **المرحلة 1 — Foundation** (هياكل Django/React، Docker Compose، CI، health endpoints، logging، بنية الاختبارات — بلا أي Features).

## Risks

| الخطر | الأثر | التخفيف المقرر |
|---|---|---|
| استعلام غير محكوم بالمدرسة يفلت للإنتاج | تسرب بين مستأجرين | الطبقات الأربع + اختبار عزل إلزامي لكل endpoint |
| منطق INCOMPLETE يُختصر خطأً إلى «غائب» | تقارير ظالمة للطلاب | ADR-006 قاعدة صلبة + اختبارات المرحلة 8 |
| تضخم نطاق المراحل (features غير مطلوبة) | تأخير MVP | قائمة الممنوعات + خطة مراحل بمعايير خروج |
| فقدان مفاتيح التشفير | فقدان أرقام الهويات | توثيق التدوير والنسخ الاحتياطي للمفاتيح (المرحلة 20) |
| المشروع ليس Git repo بعد | لا تاريخ للتغييرات | تهيئة Git أول خطوات المرحلة 1 |
