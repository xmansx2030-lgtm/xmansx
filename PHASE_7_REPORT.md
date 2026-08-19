# PHASE 7 REPORT — Attendance Monitoring Dashboard

**التاريخ:** 2026-08-19

## Status

`COMPLETE` — كل معايير القبول (البند 120) تحققت بتشغيل فعلي موثق أدناه. لا بند NOT RUN.

## Monitoring architecture

قراءة صرفة مشتقة بالكامل: `attendance/selectors/monitoring.py` (الاشتقاق) +
`attendance/services/timing.py` (سياسة الحدود والتقريب — مصدر وحيد) +
`GET /api/v1/attendance/monitoring/current/` (طبقة رقيقة). لا Model جديد — حقل snapshot
واحد فقط. لا Celery (الحالة مشتقة؛ يدخل مع الإشعارات الخارجية لاحقًا)، لا Redis cache
(اللوحة متغيرة باستمرار وinvalidation يعقد بلا حاجة يثبتها قياس — قرار موثق)،
لا WebSockets (‏Polling يكفي MVP). **Computed, not stored**: لا صفوف تنبيه ولا Audit
لكل Poll (ضجيج ممنوع — البندان 103-104).

## Expected section logic

فعال + طالب ACTIVE واحد على الأقل بقيد ACTIVE في العام النشط. **السياسة الموثقة:**
الفصل الفارغ خارج الإجمالي (اختبار) — ومنه فصل حذف طلابه نهائيًا (تكامل Purge، البند 69).
غير الفعال مستبعد (اختبار). لا عام نشط → `ACTIVE_ACADEMIC_YEAR_REQUIRED` ‏409 (اختبار)
بدل لوحة مضللة.

## NOT_STARTED derivation

طرح: المتوقع − جلسات (المدرسة، التاريخ، تسلسل الحصة) — **اختبار يثبت أن عدد
AttendanceSession لا يتغير** بعد استدعاء اللوحة (لا جلسات فارغة تنشأ).

## IN_PROGRESS behavior

من الجلسة الفعلية؛ التأخر يقاس بالوقت الحالي ضد alert_at من snapshots الجلسة —
«بدأ ولم يعتمد — متأخر X» لا يخلط مع «لم يبدأ» (اختبارات قبل/بعد الحد).

## SUBMITTED behavior

**الاعتماد هو المعيار لا البدء** (البند 13): `submitted_at` ضد alert_at من snapshots.
المعتمد في الوقت يبقى في الوقت مهما تأخر عرض اللوحة (اختبار «لا يقاس بالوقت الحالي»).

## Alert threshold

`SchoolSettings.unprepared_period_alert_minutes` (‏1–120، إعداد المرحلة 3 مفعل الآن):
`alert_at = بداية الحصة + المهلة`. الحصة من `get_current_attendance_period()` المعاد
استخدامها حرفيًا — لا إعادة كتابة (منطقة زمنية/أيام الأسبوع/الجدول البديل/الفسحة).

## Boundary policy

`at >= alert_at` = OVERDUE. اختبارات الحدود الثلاثة: ‏08:54:59 في الوقت، **08:55:00
متأخر (0 دقيقة)**، 08:55:59 متأخر (0 — floor)، والاعتماد نفسه على الحد (البند 79).

## Threshold snapshot

`unprepared_alert_minutes_snapshot` على الجلسة، يلتقط عند الفتح. Migration ‏
`attendance.0002` (يدوية: nullable → تعبئة من إعدادات كل مدرسة → non-null) — بيانات
dev/test فقط والافتراض موثق في الملف. اختبارات: جلسة بمهلة 25 اعتمدت الدقيقة 20 تبقى
في الوقت بعد خفض الإعداد إلى 15 (البند 74)؛ NOT_STARTED يتبع الإعداد الحالي فورًا؛
والجلسة الجديدة بعد التغيير تلتقط القيمة الجديدة (البند 75).

## Overdue calculation

خادميًا حصرًا في `timing.py`: ‏floor لإجمالي الدقائق بعد alert_at (‏08:55→09:02 = 7).
الواجهة تعرض القيم كما تصلها — **لا حساب حالة في Frontend** (البند 41)، و`school_time`
في الاستجابة مرجع الوقت (البند 40). ‏Selector التقارير المستقبلية:
`session_submission_delay_minutes(session)` (البند 62).

## Late submission behavior

«تم التحضير متأخرًا X دقيقة» من `submitted_at` الثابت. **ثبات الأوقات مختبر regression**
(البنود 70-72، 80-81): التعديل لا يغير `submitted_at` (كان سليمًا في المرحلة 6 —
`edit_session` يحدث `updated_at` وسجل `AttendanceChange` فقط)، والاستئناف لا يغير
`started_at`؛ اعتماد متأخر 7 ثم تعديل يبقى 7، واعتماد في الوقت ثم تعديل متأخر يبقى
في الوقت.

## Dashboard summary

`total = submitted + in_progress + not_started` و«متأخر» تقاطع مفكك
(`overdue_submitted/in_progress/not_started`) — لا أرقام متناقضة (البند 18). الترتيب:
المتأخرون أولًا (لم يبدأ ← قيد ← معتمد) ثم في الوقت (قيد ← لم يبدأ ← معتمد) — مختبر.

## Filters

الحالة (الكل/تم/قيد/لم يبدأ/**المتأخرون فقط**/**تم التحضير متأخرًا**) + الصف + بحث
بالاسم. **KPIs تتبع الفلاتر** (قرار MVP موثق — عدّ حالات الخادم على القائمة المفلترة،
لا إعادة اشتقاق) + زر «مسح الفلاتر» (اختبارات Vitest).

## Roles

مدير ✅، وكيل ✅، معلم ❌، مرشد ❌، معلم+وكيل ✅، معلم+مرشد ❌ — كلها parametrized
(البنود 87-88). الرفض بالكود المركزي `PERMISSION_DENIED` (انحراف موثق عن
`ATTENDANCE_MONITORING_PERMISSION_DENIED` — نمط المرحلة 3 الثابت). لا لوحة إدارة عليا
(المرحلة 15).

## Tenant isolation

لا `school_id` في URL — ‏`request.school` حصرًا. وكيل A معلم B: تعمل في A و403 في B
(اختبار + E2E بالتبديل الفعلي). فصول وجلسات مدرسة أخرى لا تظهر ولا تنضم حتى بتطابق
التاريخ والتسلسل (اختبار البند 50). لا أسماء طلاب/هويات في الاستجابة (البند 119).

## Polling

‏TanStack ‏`refetchInterval=20s` (مبرر موثق: حداثة كافية + ~10 طلبات/ثانية لسيناريو
100 مدرسة × 2 مراقبين — البند 59)، يتوقف والصفحة بالخلفية (افتراضي TanStack)،
تحديث فوري عند focus، زر «تحديث» + «آخر تحديث HH:MM:SS». ‏E2E أثبت الاستطلاع الحقيقي:
اعتماد متأخر من سياق معلم منفصل ظهر على لوحة الوكيل المفتوحة خلال ≤30 ثانية بلا reload.

## School switching

`useSwitchSchool` يزيل كل الاستعلامات غير `me` (نمط المرحلة 2) ومفاتيح المراقبة
school-scoped — لا وميض بيانات A في B (‏E2E: الرابط يختفي والصفحة ترفض وAPI ‏403).

## Query counts

**6 استعلامات ثابتة** لكل الأحجام (لا 1+N) — مثبتة بـ `CaptureQueriesContext` في
القياس وباختبار `django_assert_max_num_queries(10)` عند 33 فصلًا.

## Performance (`benchmark_attendance_monitoring`)

7 تشغيلات لكل حجم، مع تأكيد اكتمال العدد وتنظيف لاحق:

| sections | p50 | max | queries |
|---|---|---|---|
| 10 | 40.6ms | 66.2ms | 6 |
| 20 | 39.2ms | 45.2ms | 6 |
| 40 | 44.0ms | 44.7ms | 6 |
| 80 | 52.3ms | 59.1ms | 6 |
| 100 | 58.2ms | 63.9ms | 6 |

الهدف <200ms محقق بهامش ~3×.

## OpenAPI

‏serializer-first: ‏`MonitoringResponseSerializer` وبناتها معلنة و`@extend_schema` على
الواجهة. ‏`spectacular --validate` PASS — **صفر تحذيرات متعلقة بالمراقبة** (الـ 56
القديمة الموثقة كما هي، لا Generated Types artifact في المشروع).

## Frontend

`MonitoringPage` (‏KPIs بطاقات + فلاتر + قائمة صفوف متجاوبة flex-wrap تعمل جوالًا،
بادجات أيقونة+نص لا لون فقط، RTL كاملًا) + `MonitoringSummaryCard` في رئيسية
الوكيل/المدير (نفس مفتاح الاستعلام — لا ازدواج طلبات) + رابط «متابعة التحضير» في
الترويسة للدورين + `monitoringShared.ts` (ثابت الاستطلاع وعرض الحالات).

## Backend tests

**285/285 PASS** (259 regression مراحل 1→6 + **26 جديدة**): الحدود والتقريب،
الاشتقاق بلا إنشاء، الفارغ/غير الفعال، لا عام نشط، لا حصة (جمعة/قبل/بعد/فسحة)،
الخميس والجدول البديل، snapshot المهلة (3)، ثبات الأوقات، اسم المعلم الموقوف،
الأدوار (6 معاملات)، multi-school، العزل بجلسة أجنبية، عدّاد الاستعلامات.
‏ruff نظيف، `manage.py check` نظيف.

## E2E (21/21 PASS ضد Docker الحقيقي)

19 regression + **2 جديدان**: (1) دورة حياة اللوحة كاملة — استيراد صف متابعة فريد
للتشغيل، قبل المهلة (0 متأخر)، خفض المهلة إلى دقيقة → «بدأ ولم يعتمد — متأخر» و«لم
يتم التحضير — متأخر» و«المعتمد يبقى في الوقت» (snapshot)، ثم اعتماد متأخر يظهر على
لوحة الوكيل المفتوحة عبر **الاستطلاع الحقيقي** بلا mock؛ (2) العزل: التبديل لمدرسة B
بدور معلم يخفي الرابط ويرفض الصفحة وAPI ‏403. التحكم الزمني بلا backdoor: جدول
التطوير أصبح **24 حصة × ساعة** + ضبط المهلة عبر إعدادات المدير حول وقت الخادم،
وحارس بداية يتخطى نهايات الحصص (موثق في الـ spec).

## Docker

الخدمات الست سليمة (backend/worker/postgres/redis healthy، beat/frontend Up) — لا
خدمة جديدة. إعادة تشغيل الحاويات بعد التعديلات (bind mounts بلا inotify — سلوك موثق).

## Fresh migration

قاعدة جديدة `xmansx_fresh8` → ‏`migrate` كامل PASS ثم حذفت. ‏`makemigrations --check`:
‏No changes detected. ‏`check --deploy` بإعدادات production (متغيرات بيئة كاملة):
**exit 0** — 63 تحذيرًا غير مانع (أغلبها تحذيرات spectacular الموثقة منذ المرحلة 5).

## Security review

- لا ثقة بالعميل: الحالة/الدقائق/المهلة/الوقت كلها خادمية؛ لا school_id من العميل.
- لا تسريب: فصول/جلسات B غائبة عن لوحة A حتى بمعرفات متطابقة؛ التبديل يفرغ الـ cache.
- ‏Data minimization: مستوى الفصل فقط — لا PII طلاب.
- لا Rate limit خاص يضرب الاستطلاع المشروع — الحمل محسوب (10 req/s للسيناريو المرجعي)
  والحماية العامة قائمة.
- لا Audit spam ولا صفوف تنبيه لكل Poll؛ ولا أي backdoor زمني في الإنتاج.

## Known limitations

- «لم يبدأ» بلا اسم معلم (لا جدول معلمين — قرار مشروع ثابت، البند 22).
- ‏NOT_STARTED يقاس بالإعداد الحالي (لا snapshot ممكن بلا جلسة — موثق).
- ‏`display_name` يعرض بقيمته الحالية للجلسات القديمة (snapshot اسم مؤجل عمدًا —
  البند 54).
- اللوحة حالية فقط — لا حصص سابقة ولا تقرير يوم (المرحلة 8).

## Technical debt

- استنتاج «لم تحضّر إطلاقًا» التاريخي (Phase 8) قد يحتاج snapshot تكوين الفصول —
  موثق في ATTENDANCE_MONITORING.md ولم تنشأ صفوف الآن (البند 37).
- الـ 56 تحذير OpenAPI القديمة كما هي (خطة OPENAPI.md).

## Risks

- تغيير المهلة أثناء الحصة يقلب حالة NOT_STARTED فورًا (سلوك مقصود وموثق) — قد يفاجئ
  الوكيل؛ رسالة alert_at الظاهرة في الترويسة تخفف الالتباس.
- الاستطلاع 20 ثانية يعني تأخر عرض حتى 20 ثانية — مقبول لطبيعة القرار، وزر التحديث
  اليدوي متاح.

## Files changed

Backend: ‏`attendance/models.py` (+snapshot) + migration ‏0002 + ‏`services/timing.py` +
‏`selectors/monitoring.py` + ‏`api/serializers.py`/`views.py`/`urls.py` (+endpoint) +
‏`services/sessions.py` (التقاط snapshot) + ‏benchmark جديد + ‏`seed_dev` (جدول 24 حصة)
+ ‏`tests/test_attendance_monitoring.py` (26). Frontend: ‏`MonitoringPage` +
‏`MonitoringSummaryCard` + ‏`monitoringShared` + ‏api/routes/HomePage/AppShell +
‏`monitoring.test.tsx` (10). E2E: ‏`monitoring.spec.ts` + ‏`generate_e2e_fixtures.py`
(noor-5). Docs: ‏ATTENDANCE_MONITORING.md جديد + تحديث
ATTENDANCE/ERD/PERMISSIONS/SECURITY/ARCHITECTURE.

## Commit

`feat: add attendance monitoring dashboard` — بلا Push (لا Remote مصرح به).

## Ready for Phase 8?

نعم — ‏`session_submission_delay_minutes` وثبات `submitted_at` وsnapshot المهلة تؤسس
تقارير الالتزام، وثابت «لا جلسة ≠ حضور» واستراتيجية الاستنتاج التاريخي موثقان
لتحليلات الغياب. **متوقف بانتظار الاعتماد.**
