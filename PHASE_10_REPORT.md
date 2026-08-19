# PHASE 10 — أعذار الغياب والتصنيف بعذر/بدون عذر

**التاريخ:** 2026-08-19 · **الفرع:** `feature/phase-10-absence-excuses`
**الحالة:** ✅ مكتملة — كل معايير القبول محققة ومثبتة بتشغيل فعلي.

> **ملاحظة تشغيلية:** وكيل آخر يعمل على المرحلة 11 (`student_warnings`) في نفس
> الشجرة بالتوازي. هذا التقرير يغطي المرحلة 10 فقط؛ نتائج البوابات أدناه تشمل
> اختباراته حيث تعذر الفصل (مذكور صراحة عند كل رقم).

---

## 1. Status

| البوابة | النتيجة |
|---|---|
| Backend pytest (كل الحزمة) | ✅ **432/432** (منها **50** اختبار م10، والباقي بلا انحدار) |
| ruff (نطاق م10) | ✅ نظيف |
| Django check | ✅ 0 issues |
| `makemigrations --check` | ✅ لا تغييرات معلقة |
| Fresh migrate (قاعدة PostgreSQL جديدة) | ✅ |
| Frontend typecheck + eslint | ✅ |
| Vitest | ✅ **99/99** (14 ملفًا؛ منها 12 اختبار أعذار + 3 لملف الطالب) |
| Frontend build | ✅ |
| Playwright — م10 | ✅ **5/5** (السيناريوهات الأربعة الإلزامية + العزل) |
| Playwright — الحزمة الكاملة | 🔸 **35/36** — الفشل الوحيد `device-roster-sync` (م8.6) لسبب بيئي موثق في §24 |
| Docker (backend/frontend/postgres/redis/worker/beat) | ✅ Healthy |
| Benchmarks | ✅ نفذت وسجلت (§19) |

---

## 2. Domain model — الفكرة الأساسية

طبقتان منفصلتان تمامًا:

```
الحقيقة التشغيلية:  AttendanceMark.status = ABSENT      ← لا تُمس أبدًا
التصنيف الإداري:    EXCUSED / UNEXCUSED                 ← مشتق من التغطية
```

اعتماد العذر لا يعدل أي `AttendanceMark`، ولا يوجد `AttendanceMarkStatus.EXCUSED`،
ولا عمود `excuse_status`. الطالب الذي غاب يبقى غائبًا في السجل إلى الأبد؛ ما يتغير
هو تصنيف ذلك الغياب — وهذا ما يجعل الإلغاء عملية تصنيف بحتة بلا إعادة بناء للتاريخ.

## 3. Raw absence policy

- `ABSENT` تبقى `ABSENT` بعد الاعتماد — **اختبار إلزامي**
  (`test_raw_attendance_marks_unchanged_after_approval`) يتحقق أن مجموعة الحالات
  بعد الاعتماد = `{ABSENT}` حصرًا.
- `PRESENT` و`LATE` و`NOT_RECORDED` لا تُغطى إطلاقًا.
- الجلسة `IN_PROGRESS` ليست غيابًا رسميًا — لا تغطية لها.

## 4. Excused/unexcused classification

`get_effective_absence_classification(student, attendance_session)` تعيد
`EXCUSED` عند وجود تغطية `ACTIVE` لعذر `APPROVED`، و`UNEXCUSED` افتراضيًا لأي
`ABSENT`، و`None` لغير الغياب. لا تخزين مزدوج للتصنيف على مستوى العلامة.

## 5. Models

`backend/excuses/models.py` — أربعة نماذج، هجرة واحدة (`excuses/0001_initial`):

- **`AbsenceExcuse`**: `PENDING/APPROVED/REJECTED/CANCELLED` + خمسة أنواع أعذار +
  `notes` اختيارية + حقول من فعل ماذا ومتى ولماذا لكل انتقال.
- **`AbsenceExcuseTarget`**: النطاق المُعلن، `period_sequence NULL` = يوم كامل.
- **`AbsenceExcuseCoverage`**: التغطية الفعلية، `ACTIVE/VOIDED`.
- **`AbsenceExcuseAttachment`**: مرفق بمفتاح تخزين عشوائي + checksum.

## 6. Targets

يدعم: يوم كامل، عدة أيام، حصة واحدة، عدة حصص في يوم، حصص عبر عدة أيام.
التحقق يرفض: التواريخ المستقبلية (`EXCUSE_FUTURE_DATE_NOT_ALLOWED`)، الأهداف
المكررة، الجمع بين يوم كامل وحصص لنفس التاريخ، والحصص غير الموجودة في جدول اليوم.
قيد `uniq_excuse_target` بـ`nulls_distinct=False` يمنع تكرار هدف اليوم الكامل.

## 7. Coverage

قيد DB جزئي **`uniq_active_coverage_per_absence`** على
`(attendance_session, student) WHERE status='ACTIVE'` هو حجر الأساس: يمنع تغطية
غياب واحد بعذرين معتمدين، ويجعل الاعتماد المزدوج والمتزامن آمنين على مستوى قاعدة
البيانات لا على مستوى الواجهة.

التغطية مرتبطة بالجلسة لا بالعلامة — لأن `edit_session` يحذف العلامات ويعيد
إنشاءها فمعرفاتها غير مستقرة، بينما `(الجلسة، الطالب)` ثابتان.

## 8. Preview

`POST /excuses/{id}/preview/` يعيد لكل يوم: حصص النطاق، المعتمدة، الناقصة، الغياب،
الحضور، التأخر، وهل اليوم مكتمل — مع `preview_hash`.

## 9. Approval

`approve_excuse()` داخل `transaction.atomic()` + `select_for_update()`:
تحقق الحالة → حل الأهداف → مقارنة الـhash → رفض التداخل → إنشاء التغطيات →
`APPROVED` → Audit → إعادة حساب الملخصات بعد الـcommit.

- **Idempotency:** الاعتماد الثاني يرد `EXCUSE_ALREADY_APPROVED` بلا تغطيات مكررة.
- **Concurrency:** القيد الجزئي يضمن اعتمادًا واحدًا (اختبار يثبت `IntegrityError`).
- **Overlap:** `ABSENCE_ALREADY_EXCUSED` مع قائمة التواريخ الآمنة.

## 10. Rejection / Cancellation

- الرفض: `PENDING → REJECTED` بسبب إلزامي؛ لا أثر على أي عداد.
- الإلغاء: `APPROVED → CANCELLED` بسبب إلزامي؛ التغطيات `VOIDED` والعدادات تعود
  `UNEXCUSED` — لا Hard Delete لعذر معتمد إطلاقًا.

## 11. Attendance edit reconciliation

`reconcile_excuse_coverage_for_date()` تُستدعى من `submit_session` و`edit_session`
(قبل إعادة حساب الملخصات، بعد الـcommit):

| ما حدث | النتيجة |
|---|---|
| `ABSENT → PRESENT` / `→ LATE` | التغطية `VOIDED` بسبب `ATTENDANCE_CHANGED` |
| `PRESENT → ABSENT` ضمن عذر معتمد | تغطية جديدة **تلقائيًا** |
| جلسة ناقصة تُعتمد لاحقًا والطالب غائب | تغطية جديدة **تلقائيًا** |

**النتيجة: ترتيب الإجراءات لا يهم.** الأداء محصور بالطلاب ذوي الأهداف/التغطيات في
ذلك التاريخ فقط (اختبار `test_reconcile_scoped_to_affected_students` يثبت أن طالبًا
بلا عذر لا يُمس).

**إصلاح مكتشف أثناء E2E:** أمر `seed_attendance_sessions` كان يتخطى المواءمة،
فتخالف حالة البذر سلوك الإنتاج. أضيف الاستدعاء بنفس ترتيب `submit_session`.

## 12. DailyAttendanceSummary

عمودان جديدان فقط (لا هدم): `excused_absent_periods` و`unexcused_absent_periods`،
بثابت `excused + unexcused = absent_periods` (اختبار يفحصه على كل الصفوف).
Data migration `0006` عالجت البيانات السابقة (`unexcused = absent_periods`).

- FULL + `unexcused=0` + `excused>0` → **كامل بعذر**
- FULL + `excused=0` + `unexcused>0` → **كامل بدون عذر**
- FULL + كلاهما > 0 → **مختلط**، لا يُحسب في أي منهما
- `UNDETERMINED` يبقى كذلك — **العذر لا يكمل التحضير الناقص**

## 13. Student profile integration

الإجماليات باقية كما هي وفوقها أربع بطاقات تصنيف (غياب كامل بعذر/بدون عذر، حصص
غياب بعذر/بدون عذر) + تنبيه للأيام المختلطة. تبويب «الأعذار» يعرض القائمة الكاملة
ويفتح بطاقة التفاصيل. تفاصيل اليوم تعلّم كل حصة غياب بعذر/بدون عذر مع أزرار إضافة
عذر سريعة (لليوم أو للحصة غير المعذورة) للمدير/الوكيل فقط.

## 14. Attachments & storage security

PDF/JPG/PNG فقط، 10MB، 5 مرفقات كحد أقصى. التحقق من **المحتوى الفعلي**: Pillow
للصور مع مطابقة الصيغة للامتداد، وتوقيع `%PDF-` + `%%EOF` للـPDF بلا تنفيذ أي
محتوى تفاعلي. الـMIME مشتق من المحتوى لا من العميل. مفاتيح تخزين عشوائية
(`uuid4`) — الاسم الأصلي بيانات وصفية فقط. التنزيل عبر endpoint مصرح
(`FileResponse` + `Content-Disposition: attachment`) بعد فحص المصادقة والمستأجر
والدور؛ لا رابط media عام ولا `storage_key` مكشوف.

**الوضع الحالي:** تخزين محلي خاص (`MEDIA_ROOT`). الانتقال إلى S3-compatible بضبط
`STORAGES` دون تغيير الكود لأن الوصول لا يمر عبر رابط مباشر أصلًا — موثق في
`docs/ABSENCE_EXCUSES.md`.

## 15. Permissions & tenant isolation

| الدور | عرض | إنشاء | اعتماد/رفض/إلغاء | مرفقات (رفع/تنزيل) |
|---|---|---|---|---|
| SCHOOL_MANAGER | ✅ | ✅ | ✅ | ✅ |
| VICE_PRINCIPAL | ✅ | ✅ | ✅ | ✅ |
| COUNSELOR | ✅ metadata | ❌ | ❌ | ❌ |
| TEACHER | ❌ | ❌ | ❌ | ❌ |

العزل: كل إجراء على عذر مدرسة أخرى يرد **404** (لا 403 — لا تسريب وجود)، وإنشاء
عذر لطالب من مدرسة أخرى يرد 404، والتغطيات لا تعبر حدود المدرسة أبدًا. اختبار
متعدد المدارس يثبت أن نفس المستخدم (وكيل في A، معلم في B) يُمنع بعد التبديل إلى B.

## 16. Audit

سبعة أحداث: `EXCUSE_CREATED/UPDATED/APPROVED/REJECTED/CANCELLED` +
`EXCUSE_ATTACHMENT_UPLOADED/REMOVED`. الـmetadata أعداد ومعرفات فقط
(`coverage_count`, `targets`, `size_bytes`) — بلا أرقام هوية أو محتوى طبي.

## 17. Purge

`excuses/purge_integration.py` يسجل أربع خطوات بترتيب التبعية (التغطيات ← الأهداف
← المرفقات ← الأعذار) **وأول collector فعلي في `PURGE_STORAGE_COLLECTORS`** — الحذف
النهائي يزيل ملفات المرفقات من التخزين فعليًا (اختبار يثبت `storage_ok=1`,
`storage_failed=0` واختفاء الملف). فشل حذف ملف يبقي المهمة `PARTIALLY_FAILED`.

## 18. Phase 11 readiness (بيانات فقط)

`count_unexcused_full_absence_days`, `count_excused_full_absence_days`,
`count_unexcused_absent_periods`, `count_mixed_full_absence_days`.
**اليوم المختلط لا يُصنَّف تلقائيًا** كيوم كامل بدون عذر — القرار للمرحلة 11.
لا `WarningRule` ولا `StudentWarning` ولا أي تنبيه في هذه المرحلة.

## 19. Performance

`python manage.py benchmark_excuses` (بيئة Docker المحلية):

| العملية | الزمن | الاستعلامات |
|---|---|---|
| معاينة 7 حصص | 27.6ms | 6 |
| اعتماد 7 حصص | 104.5ms | 23 |
| معاينة 35 حصة | 74.0ms | 18 |
| اعتماد 35 حصة | 217.4ms | 75 |
| معاينة 105 حصة | 152.4ms | 48 |
| اعتماد 105 حصة | 683.8ms | 201 |
| قائمة 25 من أصل **100** | 68.3ms | **4** |
| قائمة 25 من أصل **1000** | 61.2ms | **4** |
| تفاصيل عذر بـ105 تغطية | 33.8ms | **7** |

**لا N+1:** استعلامات القائمة والتفاصيل ثابتة العدد بغض النظر عن الحجم. استعلامات
الاعتماد تنمو خطيًا مع **عدد الأيام المتأثرة** لا عدد الطلاب (كل يوم يعيد حساب
ملخصه مرة) — سلوك مقصود وموثق.

## 20. API endpoints

11 نقطة تحت `/api/v1/excuses/` (قائمة، KPIs، تفاصيل، تعديل، معاينة، اعتماد، رفض،
إلغاء، رفع/تنزيل/حذف مرفق). لا `school_id` من العميل إطلاقًا، ولا Mass Assignment
(`PATCH` لا يقبل `status`/`school`/`approved_by`؛ إجراءات الحالة endpoints منفصلة).

## 21. Frontend

- صفحة `/excuses` مستقلة: KPIs + فلاتر (الحالة، النوع، التاريخ) + جدول + إنشاء.
- `ExcuseCreateCard` مشترك بين الصفحة وملف الطالب (إنشاء سريع بطالب/تاريخ/حصة
  مثبتة).
- `ExcuseDetailCard`: النطاق، التغطيات النشطة والملغاة مع سببها، المرفقات،
  المعاينة، وإجراءات دورة الحياة.
- رابط «الأعذار» في التنقل للمدير/الوكيل/المرشد فقط.

## 22. Tests

| النوع | العدد | التغطية |
|---|---|---|
| Backend — النطاق (`test_excuses.py`) | 31 | التصنيف، الأهداف، التغطية، المواءمة، الملخصات، Selectors م11، Purge، وأربعة اختبارات انحدار للعيوب المصححة في §23 |
| Backend — API (`test_excuses_api.py`) | 19 | سير العمل، الفلاتر، الصلاحيات، العزل/IDOR، المرفقات، Mass assignment، تواريخ غير صالحة، توقيع PDF |
| Vitest (`excuses.test.tsx`) | 12 | القائمة، الفلاتر، الإنشاء (يوم/أيام/حصص)، المعاينة، الاعتماد، Stale، الرفض، الإلغاء، الرفع، الصلاحيات |
| Vitest (`profile.test.tsx`) | +3 | بطاقات التصنيف، تبويب الأعذار، تعليم الحصص |
| Playwright (`excuses.spec.ts`) | 5 | السيناريوهات الإلزامية الأربعة + عزل المعلم |

**السيناريوهات الإلزامية (البنود 179–182) — كلها خضراء:**

1. غياب يوم كامل → معاينة → اعتماد → `AttendanceMark` يبقى `ABSENT`، والملف يعرض
   1 غياب كامل / 1 بعذر / 0 بدون عذر.
2. غياب 3 حصص، اعتماد حصتين → 3 إجمالي، 2 بعذر، 1 بدون عذر.
3. اعتماد ثم تصحيح `ABSENT → PRESENT` → التغطية `VOIDED`، العدادات تتحدث، وسجل
   العذر يبقى ظاهرًا مع سبب الإلغاء.
4. يوم ناقص → اعتماد يوم كامل → اعتماد الحصة المفقودة لاحقًا → التغطية تتوسع
   تلقائيًا والملخص يصبح غيابًا كاملًا بعذر.

## 23. مراجعة تدقيقية مستقلة — عيوب اكتُشفت وصُححت

بعد اكتمال البوابات شُغّلت مراجعة تدقيقية مستقلة على كامل كود المرحلة. النتائج
أدناه **صُححت كلها** وأضيفت لها اختبارات انحدار (لا شيء منها معلق):

| # | العيب | الأثر | الإصلاح |
|---|---|---|---|
| 1 | `cancel_excuse` لا يعيد المواءمة | إلغاء عذر مع وجود عذر معتمد آخر يغطي نفس الغياب يترك التصنيف «بدون عذر» حتى يقلبه تعديل حضور عابر — أي أن النتيجة تعتمد على ترتيب الإجراءات | استدعاء المواءمة داخل الإلغاء لتواريخ التغطيات الملغاة |
| 2 | المواءمة تقرأ خارج الـ transaction بلا قفل | إلغاء متزامن بين القراءة والكتابة يُنشئ تغطية **نشطة لعذر ملغى** لا يزيلها شيء لاحقًا | نقل كل القراءات داخل `atomic` + `select_for_update` على الأعذار المرشحة |
| 3 | `excused = min(covered, absent)` | تغطية بقيت لجلسة لم يعد الطالب غائبًا فيها تُنسب لغياب آخر: الثابت الحسابي يصمد لكن التصنيف يكون خاطئًا صامتًا | المطابقة على مستوى (الطالب، الجلسة) لا بالعدّ |
| 3ب | `rebuild_daily_attendance_summaries` لا يوائم | أداة الإصلاح تعيد خبز التغطية القديمة بدل تصحيحها | مواءمة قبل إعادة الحساب لكل يوم |
| 4 | `preview_hash` غير مربوط بالعذر ولا بأهدافه | معاينة حصة واحدة ثم تبديل الأهداف إلى ثلاثين يومًا واعتمادها بنفس البصمة؛ وبصمة النطاق الفارغ ثابت عالمي يصلح لاعتماد أي عذر بلا معاينة | إدخال معرف العذر وقائمة الأهداف في البصمة |
| 5 | فلاتر التاريخ تمرر خامًا للـORM | `?from_date=abc` يرد **500** بدل 400 | تحقق صريح برسالة عربية |
| 6 | حد المرفقات بلا قفل، وحذف الملف قبل الصف | تجاوز الحد عند الرفع المتزامن؛ وصف يشير لملف مفقود يكسر التنزيل بـ500 | `select_for_update` على العذر؛ حذف الصف ثم الملف بعد الـcommit |
| 7 | توقيع PDF يُبحث عنه في أول 1KB لا في بدايته | ملف HTML يحوي `%PDF-` عرضًا يُقبل ويُخزَّن بـMIME كاذب | `startswith` |
| 8 | اختيار القيد في المعاينة بلا ترتيب | طالب بقيدين ساريين (نقل منتصف اليوم) يعطي أعداد معاينة متذبذبة حسب ترتيب قاعدة البيانات | ترتيب صريح `-enrolled_at, -id` |

المراجعة أكدت أيضًا سلامة: عدم المساس بـ`AttendanceMark` مطلقًا، حصر التغطية في
`ABSENT` على جلسات `SUBMITTED`، استحالة تجاوز حدود المدرسة، صحة القيد الجزئي ضد
الاعتماد المزدوج والمتزامن، وسلامة صلاحيات كل نقاط النهاية وتسجيل الـPurge.

## 24. Files changed

**جديد:** `backend/excuses/` (models, validators, selectors, services/{coverage,
excuses}, api/{serializers,views}, urls, admin, apps, purge_integration,
migrations/0001, management/commands/benchmark_excuses) ·
`backend/attendance/migrations/{0005,0006}` · `backend/tests/{test_excuses.py,
test_excuses_api.py}` · `frontend/src/features/excuses/{api.ts, ExcusesPage.tsx,
ExcuseCreateCard.tsx, ExcuseDetailCard.tsx, excuses.test.tsx}` ·
`frontend/e2e/excuses.spec.ts` · `docs/ABSENCE_EXCUSES.md` · `PHASE_10_REPORT.md`

**معدّل:** `attendance/{models, services/daily_summary, services/sessions,
selectors/analytics, management/commands/seed_attendance_sessions}` ·
`audit/models` · `config/{settings/base, urls}` · `students/{api/views,
api/profile_serializers, services/attendance_profile}` ·
`tests/test_student_attendance_profile.py` · `scripts/generate_e2e_fixtures.py` ·
`frontend/src/{app/AppShell.tsx, routes/index.tsx, features/students/{api.ts,
StudentAttendanceProfilePage.tsx, profile.test.tsx}}` · `docs/{ARCHITECTURE,
DAILY_ATTENDANCE, DATA_PURGE, ERD, PERMISSIONS, SECURITY,
STUDENT_ATTENDANCE_PROFILE}.md` · `.gitignore`

## 25. Known limitations & technical debt

1. **التخزين محلي خاص** لا Object Storage — الانتقال بضبط `STORAGES` فقط، موثق.
2. **لا فصل بين المسجل والمعتمد** (كلاهما مدير/وكيل) — قرار MVP صريح، النماذج تتسع
   للفصل دون هجرة هدمية.
3. **لا أعذار مستقبلية** (إجازة مسبقة) — مؤجل كميزة منفصلة.
4. **تعديل العذر مقصور على `PENDING`** — المعتمد يُلغى ويُعاد تسجيله بدل التعديل
   الصامت.
5. **التحقق من PDF بالتوقيع لا بالتحليل الكامل** — كافٍ للغرض وأكثر أمانًا من
   parsing محتوى غير موثوق؛ إضافة فحص أعمق ممكنة لاحقًا دون تغيير العقد.
6. **استعلامات الاعتماد تنمو مع عدد الأيام** (إعادة حساب ملخص لكل يوم) — مقبول
   ضمن الأحجام الواقعية ومقاس.
7. **`device-roster-sync` E2E يفشل بيئيًا** (خارج نطاق المرحلة 10): مدرسة الاختبار
   راكمت **447 طالبًا نشطًا** من تشغيلات E2E المتكررة، فمزامنة الأجهزة تتجاوز مهلة
   الاختبار البالغة 60 ثانية حتى مع تمديدها. لا علاقة له بالأعذار — لا سطر واحد من
   تغييرات هذه المرحلة يمس `devices/` أو `bridge/`، وقد نجح الاختبار قبل تراكم
   البيانات. العلاج المقترح (لمرحلة صيانة): تنظيف قاعدة E2E دوريًا أو جعل
   الاختبار يعمل على فصل خاص به بدل كل طلاب المدرسة.
8. **معاينة طالب بقيدين ساريين في نفس اليوم** (نقل منتصف اليوم): اختيار الفصل صار
   حتميًا، لكن عدادات المعاينة قد تخلط جلسات الفصلين. حالة نادرة وموثقة؛ التغطية
   الفعلية والملخصات صحيحة لأنها تعمل على العلامات مباشرة.

## 26. Ready for Phase 11?

**نعم.** البيانات المطلوبة للإنذارات متاحة عبر Selectors نظيفة، والتمييز بين اليوم
الكامل بعذر/بدون عذر/المختلط محسوم على مستوى البيانات مع ترك **قرار الاحتساب**
للمرحلة 11 كما نص التكليف. لم يُنفذ أي جزء من المرحلة 11 في هذا العمل.
