# PHASE 5 REPORT — Staff Directory + Teacher Import + Membership Invitations

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 124) تحققت بتشغيل فعلي موثق أدناه.

## OpenAPI implementation (سداد الدين — نفذ أولًا)

drf-spectacular 0.30 (متوافق مع Django 5.2/DRF 3.16 بالتشغيل الفعلي): `GET /api/v1/schema/` + `/api/v1/docs/` محميتان بـ IsAdminUser افتراضيًا (مفتوحتان في التطوير) عبر wrappers تقرأ الإعداد وقت الطلب. التغطية: **48 مسارًا** كلها في الـ schema (اختبار يتحقق من العشرة الأساسية). CI: خطوة `spectacular --validate`. **قرار Types موثق** في [docs/OPENAPI.md](docs/OPENAPI.md): الأنواع اليدوية تبقى الآن + قاعدة serializer-first ملزمة من المرحلة 6 مع توليد تدريجي. حدود صادقة: 48 تحذير «unable to guess serializer» للـ views اليدوية القائمة — غير حرجة وموثقة.

## StaffProfile / Global User behavior

OneToOne مع SchoolMembership: display_name/employee_number (فريد جزئيًا)/job_title/source — **لا role فيه، ولا يعدل اسم User العالمي بصمت** (اختبار يثبت بقاء `first_name` العالمي بعد استيراد مدرسة ثانية باسم مختلف). نفس User = ملفات مختلفة لكل مدرسة (اختبار). Selector جاهز للمرحلة 6: `get_current_staff_profile(user, school)`.

## Teacher import architecture

نفس نمط المرحلة 4 مع **إعادة استخدام حقيقية**: `common/excel_security.py` مستخرج (students يفوض إليه — شيم توافق)، وتطبيع الجوال بـ `normalize_mobile` من المرحلة 2 حرفيًا. الدور الافتراضي **TEACHER فقط** — الملف لا يمنح أدوارًا إدارية (قرار أمني ضد التصعيد).

## New user flow / Temporary password strategy

جوال جديد → User (`secrets.token_urlsafe` كلمة مؤقتة، `must_change_password=True`) + عضوية ACTIVE + TEACHER + StaffProfile. الكلمة تعاد **مرة واحدة** في استجابة الاعتماد (بجوال مقنع) مع تحذير «ستظهر مرة واحدة فقط» — **اختبار مسح شامل** يثبت غيابها من: job.summary، staging (محذوف)، Audit metadata، وحقل password (hash فقط). لا Export ملفات (قرار موثق). Audit لا يحوي جوالًا كاملًا (masked).

## Existing user flow / Privacy

جوال موجود → **إعادة استخدام User** (اختبار: count=1، hash كلمة المرور **لم يتغير بالبايت**) + عضوية INVITED + TEACHER + Profile. **لا تسريب عبر المدارس:** المعاينة لا تذكر اسم مدرسة المستخدم الأخرى (اختبار نصي)، لا Global User Search، والمطابقة فقط داخل workflow الاستيراد المراقب (قرار موثق في STAFF_IMPORT.md).

## Multi-school flow / Membership invitations

سيناريو البند 51 كامل بـ E2E: معلم فعال في A تستورده B → دخوله يظهر A + دعوة B → قبول → Switcher يحوي A وB بأدوار صحيحة. الحالات: INVITED→ACTIVE (قبول) / DECLINED (رفض بلا حذف — migration للحالة الجديدة) / Reinvite صريح فقط (الاستيراد يصنف DECLINED «يتطلب إجراء» ولا يعيد الدعوة بصمت — اختبار). دعوة قائمة لا تتكرر. دعوات الآخرين 404 (اختبار IDOR). التفصيل: [docs/INVITATIONS.md](docs/INVITATIONS.md).

## Initial password change

`POST /auth/change-initial-password/` عالمي (ليس school-scoped — المدير لا يعيد تعيين كلمات مرور عالمية): كلمة حالية + جديدة + تأكيد، سياسة عربية (≥8/ليست أرقامًا/ليست الجوال)، ثم `update_session_auth_hash` + تدوير جلسة + Audit. **البوابة:** ‏`must_change_password` يمنع كل الـ APIs المدرسية والتبديل (`INITIAL_PASSWORD_CHANGE_REQUIRED`). اختبار التدفق الكامل: الكلمة المؤقتة تعمل → البوابة تمنع → التغيير → الجلسة باقية → القديمة توقفت والجديدة تعمل.

## Role management / Staff suspension

add/remove مع `ROLE_ALREADY_ASSIGNED`/`ROLE_NOT_ASSIGNED` + حمايتان: **آخر مدير** (إزالة/إيقاف → `LAST_SCHOOL_MANAGER_REQUIRED` — اختباران) و**آخر دور** (الإيقاف الصريح بديل الإزالة — سياسة موثقة). الإيقاف لا يمس عضويات المدارس الأخرى ولا User العالمي (اختبار) — counselor يكسب TEACHER ولا يفقد COUNSELOR (اختبار + E2E).

## Tenant isolation / Excel security / Celery

معرفات B كلها 404 لمدير A (get/patch/roles/suspend/commit — اختبارات) + E2E (خالد معلمًا في B: UI مخفية وAPI 403). أمان Excel مشترك معاد الاستخدام. Celery: tenant من `job.school`، idempotent، **مثبت عبر Worker حقيقي في Docker بالـ E2E**.

## Frontend

دليل الموظفين (بحث/فلتر دور/ترقيم/جوال مقنع/شارات أدوار/لوحة إدارة للمدير: أدوار checkboxes + إيقاف/تفعيل/إعادة دعوة) + Wizard استيراد بخطواته مع **نتيجة الحسابات الجديدة لمرة واحدة** + قسم «دعوات مدارس» في شاشة الاختيار + شاشة تغيير كلمة المرور الإجبارية (حراسة في RequireAuth/Login/SelectSchool).

## API endpoints

`/staff/` (+detail/roles/suspend/activate/reinvite) + `/staff-imports/` (+process/preview/commit/cancel) + `/auth/invitations/` (+accept/decline) + `/auth/change-initial-password/` + schema/docs — بكل رموز البند 107 برسائل عربية.

## Tests

- **Backend: 205/205 PASS** (174 regression + 31 جديدة): OpenAPI (3)، الاستيراد (13: السلسلة الكاملة/عدم تخزين الكلمة/إعادة الاستخدام/idempotent/إضافة دور/دعوة قائمة/رافض/تكرارات/stale/سباق/صلاحيات/عزل)، الإدارة والدعوات وكلمة المرور (15).
- **Frontend: 39/39 PASS** (32 regression + 7 جديدة) + lint + typecheck + build.

## E2E (12/12 PASS ضد Docker الحقيقي)

8 regression + 4 جديدة: (1) معلم جديد: استيراد → كلمة مؤقتة من الواجهة → دخول بها → تغيير إجباري → Shell بدور معلم؛ (2) متعدد المدارس: B تستورد نفس الجوال → دعوة → قبول → المدرستان والتبديل؛ (3) مرشد يستورد كمعلم → دوراه معًا؛ (4) العزل. الـ fixtures بجوالات فريدة لكل تشغيل.

## Performance (تطوير — created=N مثبت في كل قياس)

| rows | parse+preview | commit | peak mem |
|---|---|---|---|
| 50 | 0.22s | 5.38s | 1.2MB |
| 200 | 0.29s | 21.35s | 1.1MB |
| 500 | 0.57s | 54.23s | 1.8MB |
| 1000 | 1.16s | 137.26s | 3.5MB |

الاعتماد يهيمن عليه Argon2 عمدًا (~0.11s/حساب). **ملاحظة منهجية:** القياس الأول كان يقيس صفوف أخطاء بصمت (جوالات 9 خانات) — أضيف تحقق `created==size` يفشل القياس الزائف؛ الأرقام أعلاه بعد الإصلاح.

## Fresh migration / Docker

Migrations (must_change_password + DECLINED + staff app) طبقت؛ قاعدة جديدة كليًا → migrate من الصفر PASS؛ `makemigrations --check` نظيف؛ الخدمات الست تعمل (backend/worker healthy) والاستيراد عبر Worker فعلي.

## Security review

تصعيد الأدوار من الملف ممنوع ✓ enumeration (لا بحث حر بالجوال، رد الدخول موحد) ✓ تسريب عبر المدارس (اختبار نصي + E2E) ✓ الكلمة المؤقتة (secrets + عدم تخزين مثبت) ✓ جلسة ما بعد التغيير (update_session_auth_hash مجرب) ✓ IDOR/mass assignment ✓ stale/double commit ✓ آخر مدير ✓ سباق UNIQUE(mobile) ✓.

## Known limitations / Technical debt

- إعادة إصدار كلمة مؤقتة/Password Reset عام: مؤجل موثقًا (البند 24).
- commit الاستيراد متزامن — ملفات ضخمة كلها حسابات جديدة بطيئة بحكم Argon2 (مرشح async مستقبلًا).
- ترقية الـ views القائمة إلى response serializers: دين تدريجي موثق في OPENAPI.md (الجديد serializer-first إلزاميًا).
- توليد TypeScript من الـ schema مؤجل حتى وجود response serializers (قرار موثق).

## Risks

| الخطر | التخفيف |
|---|---|
| نسيان serializer-first في المرحلة 6 | قاعدة ملزمة في OPENAPI.md + ARCHITECTURE.md |
| بوابة كلمة المرور تفوت endpoint جديدًا | مطبقة في الأساس المشترك (ActiveSchoolRequired) الذي يرثه كل endpoint مدرسي |

## Files changed

Backend: staff app كامل (models/migration/services×5/tasks/api/urls/admin/benchmark)، common/excel_security، accounts (must_change_password + invitations + change-password + me موسع)، memberships (DECLINED + selector + بوابة)، audit (16 حدثًا)، spectacular (settings/urls/wrappers)، seed (منى)، 3 ملفات اختبار جديدة. Frontend: features/staff (api/StaffPage/Wizard/tests)، ChangeInitialPasswordPage، دعوات SelectSchool، حراس محدثة، routes/nav، types/auth. E2E: staff-import.spec + مولد fixtures موسع. Docs: 4 جديدة + 6 محدثة. CI: خطوة OpenAPI.

## Commits

Commit واحد: `feat: add staff management and teacher import workflow`. لا push.

## Ready for Phase 6?

**نعم — وكل متطلبات التوافق المسبق جاهزة (البند 115-117):** ‏`request.school/membership/school_roles` قائمة، فحص TEACHER عبر `school_role_required("TEACHER")`، ‏`get_current_staff_profile` بلا استعلامات مربكة، وقرار هوية المعلم في الحضور موثق مسبقًا: `AttendanceSession.submitted_by_membership` (لا User وحده). OpenAPI جاهز قبل APIs الحضور كما اشترط.
