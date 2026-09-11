# جداول الحصص — كما نفذت في المرحلة 3

## BellSchedule

- name (العادي / رمضان / الاختبارات / مؤقت)، status (ACTIVE / INACTIVE / ARCHIVED)، valid_from/valid_to (لصلاحية زمنية مستقبلية — الاختيار MVP هو «جدول لكل يوم أسبوع»).
- الأرشفة (لا حذف) تفك ارتباط الجدول من أيام الأسبوع ذريًا وتخفيه من القوائم.

## BellPeriod

- sequence، name، start_time، end_time، `is_attendance_period` — **الفسحة/الاصطفاف = false** (لا تدخل التحضير لكنها تخضع لمنع التداخل).
- `school` denormalized يرثه من الجدول (الخادم يحدده — حتى في Django Admin عبر save_formset).
- **قيود DB:** `UNIQUE(bell_schedule, sequence)` + Check `end_time > start_time`.
- **منع التداخل:** في الـ Service (`_validate_periods`) على كل فترات الجدول — مغطى باختبارات فعلية (تداخل، نهاية قبل بداية، ترتيب مكرر). ExclusionConstraint (btree_gist) خيار تحصين لاحق موثق وغير معتمد الآن.

## تعديل الحصص — `PUT /bell-schedules/{id}/periods/`

`replace_schedule_periods` (transaction.atomic): validation كامل ثم استبدال ذري. **سياسة مستقبلية موثقة في docstring الخدمة:** عند وجود AttendanceSessions (المرحلة 6+) يجب أن ترفض الخدمة حذف حصص مستخدمة تاريخيًا؛ التاريخ نفسه محمي لأن الحضور سيأخذ snapshot.

## ربط الأيام — SchoolWeekDay

- صف لكل (school, weekday) — `UNIQUE(school, weekday)` — يجمع: `is_school_day` + `bell_schedule` (nullable FK).
- **إعادة استخدام لا نسخ:** نفس BellSchedule يخدم عدة أيام (الأحد–الخميس → «العادي»، الخميس → جدول آخر عند الحاجة). UX «استخدام هذا الجدول في: ☑ …» ينفذ الربط لا نسخ السجلات.
- كل الأيام السبعة مدعومة (SUNDAY=0 … SATURDAY=6) — لا افتراض hard-coded للأحد–الخميس؛ هي فقط الافتراض الأولي عند التهيئة.
- **cross-school حماية:** ربط جدول مدرسة أخرى (أو مؤرشف/غير موجود) يرفض بنفس الرد — مغطى باختبار.
- عدد الحصص لليوم يستنتج من حصص الجدول المرتبط — لا رقم منفصل يتعارض.

## سلوك الحضور المستقبلي (Snapshot — المرحلة 6)

`AttendanceSession` سيأخذ `bell_period_snapshot` وقت التحضير يتضمن:
`period_id, sequence, name, start_time, end_time, schedule_id, schedule_name` —
كل هذه الحقول موجودة في BellPeriod الحالي. **قاعدة ملزمة (ADR-010):** بيانات الحضور
القديمة لا يعاد بناؤها أبدًا من أسماء/أوقات الحصص الحالية؛ تغيير الجدول (رمضان مثلًا)
لا يغير جلسات التحضير التاريخية.

## APIs

```text
GET/POST  /api/v1/school/bell-schedules/
PATCH     /api/v1/school/bell-schedules/{id}/
POST      /api/v1/school/bell-schedules/{id}/archive/
PUT       /api/v1/school/bell-schedules/{id}/periods/
GET/PUT   /api/v1/school/week-days/
```

رموز الأخطاء: `BELL_PERIOD_OVERLAP`, `INVALID_BELL_PERIOD_TIME`, `DUPLICATE_PERIOD_SEQUENCE` برسائل عربية تسمي الحصص المتعارضة. Audit: `BELL_SCHEDULE_CREATED/UPDATED/ARCHIVED`, `SCHOOL_DAY_SCHEDULE_CHANGED`.
