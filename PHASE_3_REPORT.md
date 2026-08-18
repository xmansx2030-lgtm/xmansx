# PHASE 3 REPORT — School Settings + Academic Calendar + Bell Schedules

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 86) تحققت بتشغيل فعلي موثق أدناه.

## Models implemented

| Model | الأبرز |
|---|---|
| `schools.SchoolSettings` | OneToOne؛ الرقم الوزاري، المرحلة (enum)، المدينة، اسم المدير الرسمي (طباعة فقط)، الشعار، timezone، دقائق التنبيه والمهلة |
| `academics.AcademicYear` | status (UPCOMING/ACTIVE/CLOSED/ARCHIVED) |
| `academics.Semester` | sequence مرن (لا افتراض لعدد الفصول)، school denormalized من الخادم |
| `academics.BellSchedule` | ACTIVE/INACTIVE/ARCHIVED + valid_from/to |
| `academics.BellPeriod` | sequence/name/start/end/is_attendance_period — كل حقول snapshot المرحلة 6 |
| `academics.SchoolWeekDay` | يدمج أيام الدراسة + ربط الجدول (نفس الجدول لعدة أيام بلا نسخ) |

## Database constraints (كلها في قاعدة البيانات فعليًا)

- `OneToOne(school)` للإعدادات + Check على نطاقي الدقائق.
- `UNIQUE(school) WHERE status='ACTIVE'` للعام وللفصل الدراسي — **مثبتة باختبارات IntegrityError مباشرة** (إدراج/تحديث يتجاوز الخدمات).
- `UNIQUE(academic_year, sequence)`، Check `start<end` للعام و`start<=end` للفصل.
- `UNIQUE(bell_schedule, sequence)` + Check `end_time>start_time`.
- `UNIQUE(school, weekday)`.

## SchoolSettings / AcademicYear / Semester / Weekdays / Bell schedules / Mappings

التفاصيل الكاملة في الوثائق الجديدة:
[docs/SCHOOL_SETTINGS.md](docs/SCHOOL_SETTINGS.md) · [docs/ACADEMIC_CALENDAR.md](docs/ACADEMIC_CALENDAR.md) · [docs/BELL_SCHEDULES.md](docs/BELL_SCHEDULES.md)

أبرز القرارات: اسم المدرسة يبقى في School.name؛ الطاقم (مدير/وكلاء/مرشدون) يعرض قراءةً من العضويات لا كنصوص؛ التفعيل الذري يغلق النشط السابق (select_for_update + قيد DB)؛ استبدال الحصص Transactional مع سياسة حماية مستقبلية موثقة في docstring؛ الفسحة `is_attendance_period=false` وتخضع لمنع التداخل.

## Permissions

`SchoolScopedAPIView` (أساس موحد جديد في `memberships/api_base.py`): قراءة = MANAGER/VICE/COUNSELOR، كتابة = MANAGER فقط، TEACHER محجوب كليًا، مدير المنصة بلا مسار للإعدادات التشغيلية. ملاحظة موثقة: رمز الرفض هو `PERMISSION_DENIED` المركزي (بدل `SCHOOL_SETTINGS_PERMISSION_DENIED` المذكور كمثال) حفاظًا على مصنع الصلاحيات الموحد.

## Tenant isolation (اختبارات اختراق فعلية)

- معرفات **عام/جدول/فصل مدرسة أخرى**: PATCH/activate/periods/archive/semesters كلها **404** (7 حالات).
- جدول مدرسة B لا يربط بيوم مدرسة A (نفس رد الجدول غير الموجود — لا تسريب).
- Mass assignment: إرسال `school/school_id/status/slug` في PATCH يتجاهل تمامًا (اختبار يتحقق من DB بعدها).
- مدير A/معلم B: كتابة تعمل في A، و403 في B مع تحقق أن بيانات B لم تمس — Backend وE2E معًا.

## Audit events

`SCHOOL_SETTINGS_UPDATED`, `SCHOOL_NAME_UPDATED`, `ACADEMIC_YEAR_CREATED/UPDATED/ACTIVATED/CLOSED/ARCHIVED`, `SEMESTER_CREATED/UPDATED/ACTIVATED`, `BELL_SCHEDULE_CREATED/UPDATED/ARCHIVED`, `SCHOOL_DAY_SCHEDULE_CHANGED` — بالحقول المتغيرة فقط، بلا محتوى ملفات (مغطى باختبار للحقول المتغيرة).

## Frontend implementation

صفحة «إعدادات المدرسة» بخمسة تبويبات (بلا تبويب إنذارات — مؤجل للمرحلة 11): بيانات المدرسة (+ شعار + طاقم قراءة فقط)، العام الدراسي (إنشاء/تفعيل/إغلاق + فصول)، أيام الدراسة (7 أيام + ربط جدول لكل يوم)، أوقات الحصص (Builder بجدول قابل للتمرير أفقيًا على الجوال: إضافة/حذف/تحقق فوري مطابق للخادم + «استخدام هذا الجدول في أيام»)، إعدادات التحضير. الكتابة تظهر للمدير فقط والحقول disabled لغيره؛ رابط الإعدادات يخفى عن المعلم. مفاتيح cache كلها `schoolScopedKey(activeSchoolId, ...)`.

## API endpoints

`/api/v1/school/settings/` (GET/PATCH) + `/settings/logo/` (POST/DELETE) + `/academic-years/` (+`{id}`, `{id}/activate|close|archive`, `{id}/semesters/`) + `/semesters/{id}/` (+activate) + `/bell-schedules/` (+`{id}`, archive, periods PUT) + `/week-days/` (GET/PUT).

## Validation rules

Serializer (أنواع وحدود) + Service (منطق الأعمال) + DB (قيود نهائية). رموز مضافة: `INVALID_ACADEMIC_YEAR_RANGE`, `ACADEMIC_YEAR_ALREADY_ACTIVE` (409), `SEMESTER_ALREADY_ACTIVE` (409), `INVALID_SEMESTER_RANGE`, `BELL_PERIOD_OVERLAP`, `INVALID_BELL_PERIOD_TIME`, `DUPLICATE_PERIOD_SEQUENCE`, `INVALID_ALERT_MINUTES` — برسائل عربية تسمي الحصص المتعارضة.

## Security review

IDOR (404 للمعرفات الأجنبية) ✓ · tenant leakage (نفس الرد للموجود الأجنبي وغير الموجود) ✓ · role escalation (مصفوفة القراءة/الكتابة + multi-school scope) ✓ · cache leakage (مفاتيح tenant-aware + تفريغ عند التبديل — من المرحلة 2) ✓ · file upload (تحقق رباعي: حجم/امتداد/محتوى Pillow/سلامة، اسم مخزن مولد) ✓ · mass assignment (school/status/slug/created_by ليست writable) ✓ · cross-school FK (جدول أجنبي في weekday يرفض؛ Admin يرث school من الجدول) ✓.

## Tests executed / Results

- **Backend: 178 passed** (127 regression للمراحل 1–2 + 51 جديدة): إعدادات (13 منها 10 قيم حدية 0/1/25/120/121/سالب)، تقويم (14)، جداول وأيام (10)، شعار (8)، عزل/mass-assignment/متعدد المدارس، query count للإعدادات ≤ 8.
- **Frontend: 27 passed** (19 regression + 8 جديدة): render للمدير، قراءة فقط للوكيل، حجب المعلم + إخفاء الرابط، تحقق الدقائق، وvalidatePeriods (4 حالات مطابقة للخادم).
- lint (ruff + eslint) PASS، typecheck PASS، build PASS.

## E2E results

**Playwright: 5/5 PASS** ضد Docker الحقيقي: 2 regression (auth/isolation) + smoke +
(1) رحلة المدير الكاملة: تعديل البيانات → عام دراسي → فصل → جدول بـ **7 حصص** → ربط الأحد–الخميس → تنبيه 25/مهلة 15 → **إعادة تحميل والتحقق من ثبات كل القيم**؛
(2) مدير A/معلم B: الرابط يختفي في B وPATCH مباشر عبر fetch → **403**.

## Fresh DB migration

قاعدة جديدة كليًا (`xmansx_fresh3`): `migrate` من الصفر → **PASS (exit 0)** ثم حذفت. `makemigrations --check` → "No changes detected". `manage.py check` نظيف. **`check --deploy`** ببيئة إنتاج اختبارية آمنة → exit 0 مع تحذير وحيد W021 (HSTS preload) — مقصود وموثق في production.py («يفعل يدويًا بعد التأكد»).

## Docker results

الخدمات الست بعد إعادة البناء وmigrations: backend **healthy**، worker **healthy**، postgres/redis **healthy**، beat/frontend Up — وseed_dev محدث (خالد: مدير A + معلم B) نفذ داخل الحاوية.

## Query/performance notes

GET settings: استعلامات محدودة (session/user/membership/settings/staff+roles) محروسة باختبار ≤ 8. القوائم prefetch للفصول والحصص (لا N+1). قرار موثق: لا cache الآن (البيانات صف واحد)، وعند إضافته: مفاتيح `school:{id}:...` مع invalidation.

## Known limitations

- **OpenAPI schema غير مولد بعد** (drf-spectacular) — الواجهة بأنواع يدوية مطابقة؛ مسجل كدين تقني للمرحلة القادمة المناسبة.
- الشعار على Local media للتطوير فقط (موثق) — Object Storage في مرحلته.
- منع تداخل الحصص Service-level (+قيود DB للأساسيات)؛ ExclusionConstraint خيار تحصين لاحق موثق.
- «الجدول النشط» يحدد بربط الأيام (حل MVP الموثق) — valid_from/to محفوظان دون اختيار تلقائي معقد.

## Technical debt

- drf-spectacular + توليد Types للواجهة.
- إعادة استخدام حصص محذوفة: الخدمة تحذف وتعيد الإنشاء (آمن الآن) — يجب إضافة حماية المراجع قبل المرحلة 6 (موثق في docstring وBELL_SCHEDULES.md).

## Risks

| الخطر | التخفيف |
|---|---|
| نسيان حماية المراجع عند بناء الحضور | موثق في 3 مواضع + snapshot إلزامي في تصميم المرحلة 6 |
| تضخم صفحة الإعدادات مستقبلًا | تبويبات معزولة بمكونات مستقلة لكل تبويب |

## Files changed

- **Backend:** academics app كامل (models/services×4/api/urls/admin/migration)، schools (settings_models/services/api/urls/admin/migration)، common/validators، memberships/api_base، audit (12 حدثًا جديدًا)، config (urls/settings)، seed محدث، 5 ملفات اختبار جديدة + conftest (role_client + عزل cache).
- **Frontend:** features/settings (api/hooks/SettingsPage/5 تبويبات/اختبارات)، AppShell (رابط الإعدادات)، routes، e2e/settings.spec، tsconfig.node (DOM lib).
- **Docs:** SCHOOL_SETTINGS/ACADEMIC_CALENDAR/BELL_SCHEDULES جديدة + تحديثات ERD/PERMISSIONS/ARCHITECTURE.

## Commits

Commit واحد: `feat: add school settings and academic schedules` (انظر git log). لا push.

## Ready for Phase 4?

**نعم.** الإعدادات والتقويم والجداول جاهزة، والأساس المدرسي الموحد (`SchoolScopedAPIView`) سيحمل endpoints الطلاب مباشرة. المرحلة 4 (Student Import) تحتاج: Grade/Section (على نفس النمط)، Student بالهوية المشفرة + HMAC (ADR-009 جاهز)، وworkflow الاستيراد عبر Celery — كلها فوق بنية قائمة.
