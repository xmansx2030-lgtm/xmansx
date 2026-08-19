# PHASE 8 REPORT — Attendance Analytics + Multi-Period Absence

**التاريخ:** 2026-08-19

## Status

`COMPLETE` — كل معايير القبول (البند 151) تحققت بتشغيل فعلي موثق أدناه. لا بند NOT RUN.

## Attendance analytics architecture

قراءة مشتقة فوق Exception-Only دون أي تغيير فيه (لا `AttendanceMark(PRESENT)`):
‏`selectors/analytics.py` (الحصة/المتعدد/اليومي) + `services/day_context.py`
(تجميد جدول اليوم) + `services/daily_summary.py` (إعادة الحساب) + 3 endpoints.
دلالة الحصة للطالب: ‏ABSENT/LATE من العلامة، ‏PRESENT بلا علامة داخل جلسة SUBMITTED،
‏NOT_RECORDED بلا جلسة معتمدة — **ولا جلسة ≠ حضور أبدًا** (البنود 3-5).

## AttendanceDayContext

‏UNIQUE(school, attendance_date)، ينشأ lazy عند أول نشاط حضور (بدء تحضير — داخل
`start_session` — ولوحة المراقبة والتحليلات، كلها عبر
`get_or_create_attendance_day_context()` الواحدة) ثم **Immutable**؛ snapshot يحمل
الجدول كاملًا والمنطقة الزمنية. لا صفوف لأيام بلا نشاط. التزامن بقيد UNIQUE +
التقاط IntegrityError.

## Historical schedule strategy

تحليل الماضي من سياق اليوم المجمد حصرًا — تقليص الجدول من 7 إلى 6 حصص بعد أسبوع
يبقي `expected_periods = 7` ليوم مضى (اختبار 120). ‏Migration ‏0004 كوّنت سياقات
للأيام ذات جلسات قائمة من جدول اليوم الحالي — افتراض dev-only موثق في الملف
والوثيقة (لا snapshot يوم كامل موجود قبل م8).

## Period sequence snapshot

**قرار موثق:** `AttendanceSession.period_sequence` القائم هو الـ snapshot — يملأ من
snapshot الحصة عند الفتح، يحمل قيد UNIQUE، ولا يتغير أبدًا؛ حقل `_snapshot` مكرر
كان زيادة بلا قيمة. اختبار regression: تغيير `BellPeriod.sequence` بعد الجلسة لا
يمس المخزن (البنود 14-15، 121).

## Specific-period analytics

`GET /attendance/analytics/period/` — يفوض داخليًا للتقرير المتعدد بحصة واحدة
(منطق واحد). غائبو الحصة من جلسات SUBMITTED فقط؛ المتأخر ليس غائبًا (اختبار).

## Multi-period analytics

`POST /attendance/analytics/multi-period/` (‏POST لأن المصفوفة، بلا `school_id`).
تحقق الحصص: غير فارغة، ≤20، موجودة في سياق اليوم، تطبيع unique+sorted
(‏[2,1,1]≡[1,2]) — وإلا `INVALID_PERIOD_SELECTION` مع `unknown_sequences` (البند 71).

## ALL_ABSENT

الأساسي: غائب في **جميع** الحصص المحددة (`Count(distinct period) == n`). اختبارات
البند 112 الثلاثة: (A,A) يظهر، (A,P) لا، (A,L) لا — والحاضر/المتأخر لا يعد غائبًا
(البنود 24-25).

## ANY_ABSENT

غائب في حصة محددة واحدة على الأقل — ضمن الفصول المكتملة للاختيار فقط (نفس قاعدة
الاستبعاد، موثقة). الافتراضي في UX هو ALL (البند 28).

## Incomplete sections behavior

الفصل مكتمل للاختيار فقط إذا كانت كل الحصص المحددة SUBMITTED له؛ غير المكتمل يستبعد
طلابه **كليًا** ويعلن بسبب لكل حصة ناقصة («لم يتم التحضير» / «بدأ التحضير ولم يعتمد»
— البند 74). مسودات IN_PROGRESS ليست بيانات (اختبار). **اختبار صريح ضد «لا جلسة →
غياب جماعي»** (البند 27).

## Morning absence workflow

زر «غائبو بداية اليوم» في تبويب عدة الحصص = preset يحدد [1,2] **قابلة للتعديل**
(إضافة الثالثة تغير الطلب فعليًا — اختبار Vitest يثبت الحمولة [1,2,3])؛ لا منطق
hard-coded في الخادم.

## DailyAttendanceSummary

الاسم المعتمد والملتزم به. صف لكل (مدرسة، طالب، يوم) — UNIQUE قيد DB؛ الحقول
والفهرس `(school, attendance_date, absence_status)` في ERD.md؛ ‏student **PROTECT**
+ خطوة Purge مسجلة. جاهزة لأعمدة الأعذار لاحقًا بلا هدم (البند 147).

## Daily completeness / Full-day / Partial / Undetermined

- ‏COMPLETE = ‏submitted ≥ expected (>0)؛ وإلا INCOMPLETE و**absence_status =
  UNDETERMINED دائمًا** — يوم 6/7 وغائب الستة ليس FULL (اختبار 118) مع عرض
  الغيابات المعروفة، واعتماد السابعة يقلبه FULL تلقائيًا (اختبار 119).
- ‏FULL = مكتمل وكل الحصص غياب (7/7 — اختبار 115)؛ PARTIAL بين ذلك (اختبار 116)؛
  NONE = صفر غياب حتى مع تأخر (اختبار 117).
- المعادلة `present + absent + late = submitted` مثبتة باختبار.

## Late counts / Late minutes

`late_periods` عدّ و`total_late_minutes` جمع دقائق (12+18+7=37 — اختبار) — Integer
في DB بلا تحويل (البند 58). اللوحة اليومية: طلاب متأخرون / مرات / دقائق.

## Historical enrollments

`enrollments_on_date` (خدمة جديدة فوق `enrolled_at`/`ended_at` القائمين — النقل
أصلًا إنهاء+قيد جديد): المنضم لاحقًا لا يظهر في يوم سابق (108)، والمنقول يبقى
بفصله القديم في تقارير ما قبل النقل حتى بعد إعادة البناء (109-110). أسماء
الفصل/الصف تعرض الحالية — snapshot أسماء مؤجل عمدًا وموثق (البند 67).

## Recalculation behavior

متزامنة بعد الاعتماد والتعديل (البند 61 — لا انتظار Worker) + أمر
`rebuild_daily_attendance_summaries` (‏school/date/range). ‏Idempotent (10 تشغيلات =
نفس الناتج — اختبار)؛ upsert بعمليات bulk واستعلامات ثابتة (~8 بعد أن كانت 2×طلاب)
مع `select_for_update` و`ignore_conflicts` + تصحيح الصفوف المتسابقة (البند 102).

## Attendance edit integration

‏A→L→P عبر `edit_session` الحقيقي تنقل العدادات فورًا (‏absent−1/late+1/الدقائق —
اختبارات 103-105)، وE2E: تصحيح إداري PATCH حوّل «غياب يوم كامل» إلى جزئي وأفرغ
تقرير [1,2] بعد إعادة العرض (البند 134).

## Tenant isolation / Roles

مدير/وكيل ✅، معلم/مرشد ❌ (‏PERMISSION_DENIED المركزي — النمط الموثق)، معلم+وكيل ✅
(‏parametrized). مدرسة أخرى: لا فصول ولا جلسات ولا أسماء تتسرب (اختبار + E2E تبديل
حقيقي مع 403 على endpoints). لا `school_id` مقبول، ولا قوائم معرفات طلاب عشوائية.

## PII minimization

استجابات التحليلات بلا `national_id` (ولا المقنع) وبلا `guardian` — اختبار نصي على
JSON كامل (البنود 33-35، 125).

## Purge integration

«ملخصات الحضور اليومية» أضيفت لـ `PURGE_STEPS`؛ الحذف يزيل Marks/Changes/Summaries
ويبقي Sessions/DayContext، والتحليلات لا تعيد إظهار المحذوف ولا تنكسر (لا عدادات
مخبأة — البنود 89-92)؛ تجريد الخطوة → `ProtectedError` صاخب (اختبار).

## API endpoints / OpenAPI

الثلاثة موثقة serializer-first بـ `@extend_schema`؛ ‏`spectacular --validate` PASS
(‏exit 0) — صفر تحذيرات متعلقة بالتحليلات (القديمة الموثقة كما هي؛ لا Generated
Types artifact في المشروع).

## Frontend

صفحة «الغياب والحضور» (‏`/attendance/analytics`، رابط للوكيل/المدير): تبويبات
حسب الحصة / عدة حصص / ملخص اليوم؛ التاريخ (اليوم أو سابق)؛ محددات الحصص من سياق
اليوم؛ preset صباحي + وضعا المطابقة؛ فلتر صف؛ تحذير الفصول الناقصة بأسبابها؛ بطاقات
حالة الحصص المطلوبة فقط للطالب (البند 80)؛ ترقيم؛ KPIs يومية + قائمة بفلتر حالة؛
‏Polling ‏20 ثانية **لليوم الحالي فقط**؛ يوم غير دراسي = رسالة واضحة. RTL/إتاحة
(نص لا لون فقط) كسابقاتها. تبديل المدرسة يفرغ الـ cache (نمط قائم).

## Tests

- **Backend: ‏311/311 PASS** (285 regression مراحل 1→7 + **26 جديدة** للتحليلات:
  الحصة/الناقص/IN_PROGRESS/ALL/ANY/التحقق/الترتيب والترقيم/اليوم الكامل بحالاته
  الأربع/القلب التلقائي/idempotency/التاريخية ×3/التعديل المتزامن/القيد التاريخي
  ×2/الأدوار/العزل/PII/Purge ×2/عدّاد الاستعلامات) + ruff + check نظيفة.
- **Frontend: ‏72/72 PASS** (62 regression + **10 جديدة**) + lint + typecheck + build.

## E2E (25/25 PASS ضد Docker الحقيقي)

21 regression + **4 جديدة**: (1) استيراد صف تحليلات فريد + بذر جلسات كل حصص اليوم
عبر أمر DEBUG-only ثم: حصة محددة (4 غائبين، المتأخر مستبعد)، [1,2] ALL (محمد وحده +
إعلان الفصل الناقص)، إضافة الثالثة تغير النتيجة، ANY (3)؛ (2) ملخص اليوم: يوم كامل/
جزئي (التأخر بدقائقه)/غير مكتمل — الغائب في كل المسجل مع حصص ناقصة **ليس** يوم
كامل؛ (3) تعديل PATCH حقيقي يحدّث التقريرين؛ (4) عزل B (رابط/صفحة/API). إصلاح
بنيوي للحتمية: ‏global-setup يعيد `seed_dev` قبل كل تشغيل (settings.spec كان يترك
جدولًا قصيرًا يفقد «الحصة الحالية» بعد الظهر — علة كامنة منذ م7 ظهرت وأصلحت).

## Performance (قياس `benchmark_attendance_analytics` — أرقام فعلية)

| طلاب | حصة p50 | حصتان ALL | ثلاث ALL | سبع ALL | يومي | rebuild فصل | rebuild يوم كامل |
|---|---|---|---|---|---|---|---|
| 500 | 24ms | 26ms | 29ms | 17ms | 10ms | 106ms | 1.7s (17 فصلًا) |
| 1000 | 41ms | 76ms | 92ms | 35ms | 12ms | — | 5.2s |
| 3000 | 102ms | 170ms | 202ms | 72ms | 16ms | — | 16.4s |
| 5000 | 161ms | 242ms | 350ms | 84ms | 13ms | 177ms | 31s (167 فصلًا) |

الأهداف محققة: حصة <250ms، متعدد <400ms (p50)، يومي <400ms. ملاحظة صادقة: أقصى
قياس منفرد للثلاث حصص عند 5000 طالب لامس 440ms قبل تحسين bulk و400ms بعده —
والتوزيع المقيس (20% غياب) أقسى من الواقع.

## Query counts

التحليلات ~7 استعلامات ثابتة (اختبار عدّاد عند 30 غائبًا مطابقًا + قياس)؛ إعادة
الحساب ~8 بعد التحويل لـ bulk (كانت 126 لفصل 30 — خفضت قبل اعتماد الأرقام).

## Fresh migration / Docker

قاعدة جديدة `xmansx_fresh9` → migrate كامل PASS ثم حذفت؛ `makemigrations --check`
بلا تغييرات؛ `check` نظيف و`check --deploy` (بيئة production كاملة) exit 0.
الخدمات الست سليمة — لا خدمة جديدة، وCelery خارج مسار التحليلات (البند 138).

## Security review

عزل المستأجر والأدوار مختبران؛ لا PII؛ لا استنتاج من الجلسات الغائبة؛ التاريخ محمي
بالـ snapshots من تعديل الجداول؛ حدود page_size/الحصص/تاريخ واحد ضد الإساءة؛ أمر
البذر DEBUG-only وليس HTTP — لا backdoor إنتاجي.

## Known limitations

- تقرير تاريخ واحد فقط — المدى الزمني في مرحلة التقارير (البند 145).
- «المتوقع من الفصول» للتواريخ الماضية يعتمد الفصول النشطة حاليًا (تكوين الفصول
  نفسه غير مؤرشف) — دين موثق لمرحلة التقارير.
- نقل منتصف اليوم: فصل نهاية اليوم يملك صف الملخص (حالة حدية موثقة).
- أسماء الصف/الفصل الحالية في العرض (snapshot أسماء مؤجل عمدًا — البند 67).

## Technical debt

- ‏snapshot تكوين الفصول التاريخي إن لزمت تقارير فترات دقيقة (موثق).
- الـ 56 تحذير OpenAPI القديمة كما هي (خطة OPENAPI.md).
- ‏backfill سياقات الأيام في migration ‏0004 من الجدول الحالي (dev-only موثق).

## Risks

- إعادة الحساب المتزامنة تضيف ~100-180ms للاعتماد — مقبولة الآن؛ لو تضخمت الفصول
  جدًا يمكن نقلها لـ Celery مع إبقاء التحديث الفوري للفصل المعني.
- تقارير اليوم الجاري تتغير مع كل اعتماد (بطبيعتها) — Polling الواجهة يوضح ذلك.

## Files changed

Backend: ‏models (نموذجان) + migrations ‏0003/0004 + ‏services (day_context/
daily_summary + ربط sessions) + ‏selectors/analytics + ‏serializers/views/urls +
‏purge_integration + أوامر (rebuild/seed_attendance_sessions/benchmark) + admin +
‏students/services/enrollments (‏enrollments_on_date) + اختبارات (26) + helpers.
Frontend: ‏AnalyticsPage + api + routes/AppShell + ‏analytics.test.tsx (10).
E2E: ‏analytics.spec.ts + global-setup (إعادة البذر) + fixtures (noor-6).
Docs: ‏ATTENDANCE_ANALYTICS.md وDAILY_ATTENDANCE.md جديدتان + تحديث
ERD/PERMISSIONS/SECURITY/ARCHITECTURE/ATTENDANCE/ATTENDANCE_MONITORING/DATA_PURGE.

## Commit

`feat: add attendance analytics and daily absence summaries` — بلا Push (لا Remote
مصرح به).

## Ready for Phase 9?

نعم — سؤال البند 155 يجاب كاملًا من الواجهة (التاريخ ← الحصص ← «غائب في جميع
الحصص المحددة» ← عرض، مع استبعاد الفصول الناقصة وتغيّر النتيجة بدقة عند تعديل
الاختيار)، وملف الطالب (المرحلة 9) سيبنى فوق `DailyAttendanceSummary`
و`enrollments_on_date` والعلامات الموجودة. **متوقف بانتظار الاعتماد.**
