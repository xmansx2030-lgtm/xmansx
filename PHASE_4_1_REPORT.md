# PHASE 4.1 REPORT — Student Lifecycle & Permanent Purge

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 68) تحققت بتشغيل فعلي موثق أدناه.

## Student lifecycle implementation / Graduation / Transfer / Withdrawal

الحالات الست بعربيتها + حقول `status_changed_at/by`, `exit_date`, `exit_reason`. التصنيف يغلق القيد الفعال بالحالة الصحيحة (GRADUATED→COMPLETED، TRANSFERRED→TRANSFERRED، WITHDRAWN→WITHDRAWN) مع `ended_at` — اختبارات معلمية للثلاثة + Audit. الجماعي: `bulk-status` (تخريج دفعة من صفحة النشطين — طلاب الصفوف الأخرى لا يتأثرون باختبار)، وتعيين منتقلين من فلتر المفقودين.

## Noor missing students

**لا حذف تلقائيًا** — فلتر «غير الموجودين في آخر ملف نور» (من missing_names لآخر استيراد مكتمل، حتى 500) → تصنيف → حذف اختياري. اختبار Backend كامل (ملفان متتاليان، المفقود يظهر ولا يحذف) + E2E.

## Inactive students UI

صفحة مستقلة: بحث بالاسم + فلاتر (الكل/خريجون/منتقلون/منسحبون/غير نشطين/مفقودو آخر ملف) + آخر صف/فصل (prefetch لآخر قيد بأي حالة — القيود مغلقة) + تحديد فردي/الكل + إجراءات المدير فقط (غير المدير: لا checkboxes ولا أزرار — اختبار + E2E). صفحة النشطين صارت تفلتر ACTIVE فعليًا (خلل اكتشفه E2E وأصلح).

## Individual / Bulk purge / PurgeJob / Celery

- فردي: `POST /students/{id}/purge/` — ‏ACTIVE مرفوض (`STUDENT_ACTIVE_CANNOT_PURGE`)، حذف DB ذري + Audit بلا PII (بلا target_id).
- جماعي: Preview بملخص خادمي (طلاب/قيود/ملفات/إجمالي سجلات) + token أحادي الاستخدام (Redis 10 دقائق) + كتابة «حذف N طالبًا» في الواجهة → `StudentPurgeJob` → Celery بدفعات 50 مع تقدم حي (`128/186`) → COMPLETED / **PARTIALLY_FAILED** عند بقايا تخزين / FAILED.
- إجراءات سريعة: «حذف جميع الخريجين/المنتقلين المعروضين» (فلتر + بحث) — E2E للاثنين.

## Object storage cleanup

سجل `PURGE_STORAGE_COLLECTORS` (الوحدات القادمة ملزمة بالتسجيل — كما `PURGE_STEPS` للـ DB) — الحذف بعد commit الـ DB، والفشل يحاسب: اختبار fake storage يثبت أن ملفًا فاشلًا واحدًا → `PARTIALLY_FAILED` مع عدّي نجاح/فشل صحيحين (لا ادعاء COMPLETED). لا ملفات طلاب فعلية في الوحدات الحالية — موثق بصدق في DATA_PURGE.md.

## Audit strategy (الخصوصية)

بعد الاكتمال تمسح `student_ids` من الـ Job؛ الأحداث (`STUDENT_PERMANENTLY_PURGED`, `STUDENT_BULK_PURGE_STARTED/COMPLETED`) تحمل school/actor/أعداد/سبب فقط — اختبارات نصية تثبت غياب الاسم والهوية.

## Tenant isolation / Permissions / Idempotency / Stale

- معرف أجنبي: فردي 404، وفي أي تحديد جماعي (status أو purge) → **رفض العملية كلها** بلا تغييرات جزئية (اختباران) + المهمة تحذف من `job.school` حصرًا.
- المصفوفة: MANAGER فقط للحذف والتصنيف (VICE/COUNSELOR/TEACHER 403 — اختبار + E2E API مباشر).
- Idempotency: token مرة واحدة، قيد «Purge جارٍ واحد لكل مدرسة» (`PURGE_ALREADY_RUNNING`)، حالة المهمة gate في Celery، وحذف المحذوف 404 مضبوط.
- Stale: بصمة (id+status) — تغيير حالة طالب بعد المعاينة → `PURGE_PREVIEW_STALE` بلا حذف (اختبار).

## Performance (deleted=N مثبت في كل قياس)

| rows | purge | معدل | peak mem |
|---|---|---|---|
| 10 | 1.48s | 6.8/s | 0.8MB |
| 100 | 7.20s | 13.9/s | 0.3MB |
| 500 | 20.23s | 24.7/s | 0.9MB |
| 1000 | 30.49s | 32.8/s | 1.7MB |

Batch size = 50 اختير من القياس (تحديث تقدم كل ~2s عند أكبر الأحجام، ذاكرة شبه ثابتة).

## Tests / E2E / Docker / Fresh migration

- **Backend: 222/222 PASS** (205 regression + 17 جديدة تغطي بنود 47–58).
- **Frontend: 43/43 PASS** (+4 جديدة: تدفق الحذف الكامل بواجهة التأكيد والتقدم، حجب الوكيل، فلتر المفقودين بأزرار التصنيف، تخريج دفعة) + lint/typecheck/build.
- **E2E: 15/15 PASS** ضد Docker الحقيقي (12 regression + 3 جديدة: رحلة الخريجين كاملة حتى الاختفاء، رحلة المفقودين→منتقلون→حذف، وحجب الوكيل UI+API). أثناءها اكتشف وأصلح: صفحة النشطين بلا فلتر ACTIVE، وحاجة بحث لصفحة غير النشطين.
- Docker: الست خدمات تعمل والحذف نفذ عبر Worker فعلي. Fresh DB migrate من الصفر PASS + `makemigrations --check` نظيف.

## Security review

صلاحية حصرية للمدير ✓ لا Tenant bypass للمنصة ✓ mixed-tenant يرفض كليًا ✓ token أحادي + بصمة stale ✓ ACTIVE محمي ✓ لا PII بعد الحذف ✓ تنظيف تخزين محاسب ✓ لا DELETE عام — action صريح ✓.

## Known limitations / Technical debt

- سجل جامعي التخزين فارغ فعليًا حتى وجود ملفات طلاب (مرفقات الأعذار م10، المستندات م12) — **إلزام التسجيل موثق في DATA_PURGE.md وفي docstring الخدمة**، وكذلك تسجيل خطوات DB لكل موديول قادم.
- `PurgeCleanupTask` لإعادة محاولة ملفات PARTIALLY_FAILED آليًا: مؤجل — الحالة تظهر للمدير والأعداد محفوظة (يبنى مع أول ملفات فعلية).
- ضبطا استقرار بيئة موثقان: مهلة Playwright 60s + workers=1 (الملفات تتشارك مدارس الـ seed وقيود العمليات الجارية)، وVitest maxWorkers=4 + asyncUtilTimeout (الجهاز يشغل Docker أثناء الاختبارات).

## Risks

| الخطر | التخفيف |
|---|---|
| موديول قادم ينسى تسجيل خطوة حذف | PROTECT FKs تفشل الحذف صاخبًا + الإلزام موثق في 3 مواضع |
| Vite/Django داخل الحاويات لا يلتقطان تغييرات bind mount على Windows | موثق — إعادة تشغيل الحاوية بعد تعديل الكود (أو تشغيل dev محليًا) |

## Files changed

Backend: students (models+migration 0002، services/lifecycle+purge، tasks/run_purge_job، api/lifecycle_views، urls، benchmark_purge)، audit (3 أحداث)، comparison (سقف 500). Frontend: InactiveStudentsPage، StudentsPage (فلتر ACTIVE + تخريج دفعة)، api موسع، routes، lifecycle.test، mockApi (تمرير init)، إعدادات استقرار الاختبارات. E2E: lifecycle-purge.spec + مولد fixtures موسع (noor-3/3b). Docs: STUDENT_LIFECYCLE + DATA_PURGE جديدتان + 4 محدثة.

## Commit

`feat: add student lifecycle and permanent data purge`. لا push.

## Ready for Phase 5?

المرحلة 5 **نفذت واعتمدت مسبقًا** (المرحلة 4.1 أضيفت بأثر رجعي بطلبك). لا تعارض: الحالات الجديدة تكامل نظيف مع الاستيراد (المفقودون) والقيود، وسجلا الحذف جاهزان لإلزام مراحل 6+.
