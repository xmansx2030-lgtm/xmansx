# PHASE 6 REPORT — Teacher Attendance + Class QR

**التاريخ:** 2026-08-19

## Status

`COMPLETE` — كل معايير القبول (البند 84) تحققت بتشغيل فعلي موثق أدناه. لا بند NOT RUN.

## Attendance models

ثلاثة موديلات في وحدة `attendance` (migration واحدة `attendance.0001` + `students.0003` لحقل `qr_token`):
- **AttendanceSession**: فريدة DB على (school, section, attendance_date, period_sequence)؛ حالات IN_PROGRESS/SUBMITTED فقط (لا NOT_STARTED — عدم الوجود هو «لم يبدأ»)؛ الإسناد بالعضوية (`started_by_membership`/`submitted_by_membership` PROTECT) لا بالمستخدم؛ `bell_period` مرجع SET_NULL و`period_sequence` عمود مستقل يحمل القيد (لأن استبدال جدول الأجراس يحذف الحصص).
- **AttendanceMark**: استثناءات فقط، `student` **PROTECT** عمدًا (حارس تكامل الحذف النهائي)، Unique (session, student).
- **AttendanceChange**: سجل علائقي append-only، قراءة فقط في الإدارة.

## Current period detection

`services/periods.py`: الآن بمنطقة المدرسة الزمنية → يوم الأسبوع المحلي (الأحد=0) → جدول اليوم من `SchoolWeekDay` → حصة `start<=t<end` بشرط `is_attendance_period`. 8 اختبارات بتواريخ ثابتة تغطي: داخل حصة/قبل الأولى/بعد الأخيرة/الفسحة/يوم عطلة/جدول خميس مختلف/تبديل جدول رمضان/منطقتين زمنيتين لنفس اللحظة العالمية.

## BellPeriod snapshot

يجمّد (تسلسل/اسم/بداية/نهاية/جدول/تاريخ/منطقة زمنية) لحظة الفتح — اختبار يعدل الجدول بعد الإرسال ويثبت بقاء الـ snapshot ودقائق التأخر كما هي.

## Roster behavior

طلاب ACTIVE بقيد ACTIVE في العام النشط فقط (اختبار: TRANSFERRED يختفي). بصمة SHA-256 عند الفتح؛ تغير القائمة قبل الإرسال → `ATTENDANCE_ROSTER_CHANGED` (409) **وتحديث البصمة يلتزم قبل رفع الخطأ** (نمط الخطأ المؤجل من المرحلتين 4 و5) فالإرسال التالي ينجح (اختبار السلسلة كاملة). قراءة القائمة ≤12 استعلامًا عند 50 طالبًا (اختبار عداد).

## Exception-only storage

اختبار 30 طالبًا: غائبان + متأخر → 3 صفوف فقط. «لا جلسة ≠ حضور» ثابت موثق ومختبر (لا endpoint يستنتج حضورًا لفصل بلا جلسة SUBMITTED).

## Attendance submission

فتح متسابق يحسم بقيد DB (`IntegrityError` → قراءة الموجود): IN_PROGRESS تستأنف لأي معلم بالمدرسة (سياسة موثقة)، SUBMITTED **تعاد للعرض** (المرسل/الوقت/العلامات/can_edit) — قرار معدل أثناء E2E: الـ 409 مسؤولية `submit` وحده (double-submit مختبر بالتفاصيل)، إذ لولا إعادة الجلسة لما وصل المعلم لشاشة التعديل أصلًا. تحقق العلامات: مكرر/خارج القائمة/LATE بلا وقت وصول → رفض بأكواد عربية.

## Late calculation

خادميًا حصرًا من snapshot البداية — `MarkInputSerializer` **لا يملك حقل `late_minutes`** أصلًا، واختبار يرسل `late_minutes:1` ويثبت التجاهل والحساب الفعلي (17 دقيقة). وصول قبل البداية → `INVALID_ARRIVAL_TIME` (لا قيم سالبة).

## Edit window

من `attendance_edit_window_minutes` (إعدادات المرحلة 3): المعلم جلسته هو وداخل النافذة (خارجها `ATTENDANCE_EDIT_WINDOW_EXPIRED`، جلسة غيره `ATTENDANCE_PERMISSION_DENIED`)؛ الوكيل/المدير تصحيح إداري في أي وقت (اختبارات الأربع حالات).

## Change history

كل تعديل يسجل صفوفًا في `AttendanceChange` **شاملة PRESENT** (اختبار ABSENT→PRESENT وPRESENT→LATE بالدقائق والسبب والفاعل). لا حذف لسجل التعديلات.

## QR architecture

`Section.qr_token`: ‏`secrets.token_urlsafe(24)`، unique، nullable — يولد عند أول طلب مدير. الملصق يرمّز `{origin}/qr/{token}`؛ ‏`/qr/:token` (خلف حراس الدخول) تحل الرمز ثم تفتح شاشة التحضير.

## QR security

الرمز **لا يمنح صلاحية** (اختبارات: anonymous → `AUTHENTICATION_REQUIRED`، مرشد → رفض، الحل داخل `request.school` حصرًا). رمز مدرسة أخرى = رمز غير موجود: نفس `SECTION_QR_INVALID` (404) — لا استكشاف عبر المدارس (اختبار E2E أيضًا: رمز A من داخل B يفشل).

## QR rotation

`POST /sections/{id}/qr/` (مدير حصرًا): رمز جديد فورًا، القديم يبطل بلا فترة سماح (اختبار)، Audit ‏`SECTION_QR_ROTATED`، والواجهة تطلب تأكيدًا صريحًا يوضح إبطال الملصقات. **انحراف موثق:** لا تاريخ للرموز → رسالة واحدة «غير صالح أو تم تجديده».

## Manual fallback

إلزامي ومحقق: قائمة الفصول في رئيسية المعلم تصل لنفس الشاشة دائمًا؛ متصفح بلا `BarcodeDetector` يرى رسالة توجيه واضحة (المسح بكاميرا الجهاز أو الاختيار اليدوي).

## Multi-school behavior

معلم بمدرستين: الجلسة تنسب لعضوية المدرسة الصحيحة (اختبار attribution). تبديل المدرسة يفرغ كل cache غير `me` (نمط المرحلة 2) — E2E: التبديل إلى B لا يظهر فصول A ولا أسماء طلابها. جلسة IN_PROGRESS تبقى في الخادم وتستأنف عند العودة (لا فقد بيانات — UX موثق).

## Tenant isolation

جلسة/فصل/QR مدرسة أخرى → 404 (اختبارات get/patch/submit/qr) وقائمة الفصول مقتصرة على مدرسة الجلسة. مرشد بلا دور معلم لا يحضّر — يرفض بالكود المركزي `PERMISSION_DENIED` (انحراف موثق متسق مع قرار المرحلة 3).

## Purge integration

`attendance/purge_integration.py` يسجل «علامات الحضور» و«تعديلات الحضور» في `PURGE_STEPS` عند الإقلاع. اختباران: (1) الحذف النهائي يحذف علامات وتعديلات الطالب ويبقي الجلسة؛ (2) **النسيان يفشل**: تجريد الخطوات → `ProtectedError` صاخب (حقول الطالب PROTECT عمدًا).

## API endpoints

`/attendance/current-period/`، `/attendance/sections/`، `/attendance/sessions/start/`، `/attendance/sessions/{id}/` (GET/PATCH)، `/attendance/sessions/{id}/submit/`، `/attendance/qr/resolve/`، `/sections/{id}/qr/` (GET/POST) — كلها بأكواد ورسائل عربية.

## OpenAPI

serializer-first منذ البداية (قاعدة المرحلة 5): كل views الحضور بـ `@extend_schema` وserializers معلنة (إدخال وإخراج). `spectacular --validate`: **صفر أخطاء/تحذيرات متعلقة بالحضور**؛ الـ 56 تحذير legacy الموثقة كما هي.

## Frontend

`features/attendance/`: ‏`api.ts` (مفاتيح `schoolScopedKey` دائمًا)، `TeacherHome` (بطاقة الحصة الحالية بتحديث دقيق + الفصول + الماسح)، `QrScanner` (BarcodeDetector مع بديل)، `AttendanceSessionPage` (الافتراضي حاضر، أزرار غائب/متأخر بوقت وصول معبأ، ملخص حي، إرسال الاستثناءات فقط، عرض الجلسة المرسلة بالمرسل والوقت، تعديل بسبب عند can_edit، معالجة ROSTER_CHANGED بتحديث القائمة مع إبقاء العلامات الصالحة)، `QrScanPage` (‏/qr/:token)، `SectionQrPage` (مدير: عرض/طباعة/تجديد — مكتبة `qrcode` محليًا). التكامل: رئيسية المعلم في HomePage لدور TEACHER، ورابط «رموز QR» للمدير.

## Tests

- **Backend: ‏259/259 PASS** (222 regression + 37 جديدة: 8 حصص + 22 تدفق + 7 QR) + ruff نظيف + `manage.py check` نظيف.
- **Frontend: ‏52/52 PASS** (43 regression + 9 جديدة للحضور) + lint + typecheck + build كلها 0 أخطاء.

## E2E (19/19 PASS ضد Docker الحقيقي)

15 regression + 4 جديدة: (1) المدير يستورد فصلي الحضور ويولد QR (الرمز مبهم ≥20 محرفًا)؛ (2) الرحلة اليدوية: علامات → ملخص حي → إرسال → **إعادة تحميل تعرض الجلسة المرسلة** → تعديل داخل النافذة (غائب→حاضر بسبب)؛ (3) رحلة QR: رمز غير صالح يرفض ثم الرمز الصحيح يفتح قائمة الفصل ويرسل؛ (4) العزل: التبديل لمدرسة B — لا فصول ولا أسماء من A، ورمز A لا يعمل من B. حتمية التشغيل: أكواد فصول وأسماء فريدة لكل تشغيل (`noor-4.xlsx`) + جدول أجراس تطويري يغطي 24 ساعة في `seed_dev`.

## Performance

`manage.py benchmark_attendance` (تطوير فقط، يؤكد اكتمال العدد قبل القياس، ينظف بعده):

| roster | start | roster GET | submit | edit |
|---|---|---|---|---|
| 20 | 28ms | 3ms | 23ms | 21ms |
| 40 | 19ms | 4ms | 20ms | 19ms |
| 60 | 22ms | 5ms | 24ms | 21ms |
| 100 | 23ms | 5ms | 21ms | 22ms |

ثابت مع الحجم (bulk_create + استعلامات محدودة) — لا مشكلة أداء حتى 100 طالب.

## Fresh migration

قاعدة جديدة `xmansx_fresh7` → `migrate` كامل PASS ثم حذفت. `makemigrations --check`: ‏No changes detected.

## Docker

الخدمات الست Up (‏backend/worker healthy، postgres/redis healthy، beat/frontend Up) بعد إعادة تشغيل backend/worker/frontend لالتقاط الكود (bind mounts بلا inotify على Windows — سلوك موثق منذ المرحلة 3). ملاحظة: `npm install` نفذ داخل حاوية frontend لإضافة `qrcode` (node_modules الحاوية منفصلة)؛ إعادة بناء الصورة تلتقطها من package.json تلقائيًا.

## Security review

- لا ثقة بأي مدخل عميل: `late_minutes` لا حقل له، `school_id` من الجلسة فقط، القوائم والجلسات داخل `request.school`.
- QR لا يمنح صلاحية + مبهم + لا تسريب عبر المدارس + تجديد فوري مسجل.
- Audit بالأعداد فقط — لا أسماء ولا هويات في metadata (والقوائم تعرض الهوية مقنعة `******1234`).
- سجل التعديلات لا يحذف؛ الإنفاذ خادمي والواجهة UX فقط.

## Known limitations

- المدير/الوكيل بلا دور معلم لا يحضّر (يصحح إداريًا فقط) — مطابق للمصفوفة بعد توضيحها.
- استئناف IN_PROGRESS متاح لأي معلم بالمدرسة (لا قفل لكل معلم) — سياسة موثقة تناسب تبديل الحصص الواقعي.
- علامات جلسة لم ترسل تعيش في المتصفح فقط حتى الإرسال (الاستئناف يعيد قائمة فارغة العلامات).
- الماسح داخل التطبيق يتطلب `BarcodeDetector` (Chrome/Edge/أندرويد) — البديل موثق وإلزامي.

## Technical debt

- 56 تحذير OpenAPI legacy كما هي (خطة docs/OPENAPI.md).
- `import time` في `AttendanceSessionPage` لوقت الوصول يستخدم ساعة جهاز المعلم لا ساعة المدرسة — انحراف طفيف مقبول (الخادم يتحقق من عدم السلبية).

## Risks

- انحياز ساعة جهاز المعلم قد يرفض وصولًا صحيحًا قرب بداية الحصة (`INVALID_ARRIVAL_TIME` برسالة واضحة — قابل للتعديل اليدوي).
- جلسات فتحت قرب نهاية الحصة تبقى IN_PROGRESS إن لم ترسل — لوحة «فصول غير محضرة» (المرحلة 7) هي المعالجة المصممة.

## Files changed

Backend: وحدة `attendance/` كاملة (models/admin/apps/urls/purge_integration/services×3/api×2/migration/benchmark) + `students.0003` (qr_token) + `audit` (4 أحداث) + `seed_dev` (جدول 24h) + اختبارات (3 ملفات + helpers). Frontend: ‏`features/attendance/` (7 ملفات) + routes/HomePage/AppShell + package.json (‏qrcode). E2E: ‏`attendance.spec.ts` + ‏`generate_e2e_fixtures.py` (noor-4). Docs: ‏ATTENDANCE.md وATTENDANCE_QR.md جديدتان + تحديث ERD/PERMISSIONS/SECURITY/DATA_PURGE/ARCHITECTURE.

## Commit

`feat: add teacher attendance and secure class QR` — بلا Push (لا Remote مصرح به).

## Ready for Phase 7?

نعم — الجلسات والعلامات وسجل التعديلات والفهارس (school+date+period / school+section+date) جاهزة لبناء لوحة المتابعة والفصول غير المحضرة، وثابت «لا جلسة ≠ حضور» موثق لتتكئ عليه التحليلات. **متوقف بانتظار الاعتماد.**
