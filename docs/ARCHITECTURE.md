# المعمارية — منصة المواظبة والمتابعة الطلابية

> وثيقة المعمارية المرجعية. أي قرار تنفيذي في المراحل 1–20 يجب أن يتوافق معها،
> وأي تغيير جوهري عليها يتطلب ADR جديدًا في `docs/adr/`.

---

## 1. نظرة عامة

منصة SaaS متعددة المدارس (Multi-Tenant) تغطي رحلة الطالب كاملة:

```text
تسجيل الحضور → الغياب/التأخر → تحليل المواظبة → التنبيه → الإنذار
→ الإجراء → الإحالة للمرشد → خطة المتابعة → إغلاق الحالة
```

- **النمط المعماري:** Modular Monolith (قرار إلزامي — انظر ADR-001).
- **اللغة والاتجاه:** Arabic First / RTL First.
- **الويب:** SPA + PWA قابلة للتثبيت، Online-First (بدون Offline Attendance في MVP).

## 2. التقنيات المعتمدة

| الطبقة | التقنية |
|---|---|
| Backend | Python 3.13, Django 5.2 LTS, DRF 3.16 |
| Database | PostgreSQL 18 |
| Cache / Broker | Redis |
| Async | Celery 5.6 + Celery Beat |
| Frontend | React 19, TypeScript, Vite 8, TanStack Query, Tailwind CSS 4 |
| PWA | vite-plugin-pwa, Workbox, Web App Manifest |
| Testing | pytest + pytest-django, Vitest + React Testing Library, Playwright |
| Infra | Docker, Docker Compose, HTTPS, S3-compatible Storage, GitHub Actions, Sentry-ready logging |

## 3. Modular Monolith — بنية الـ Backend

مشروع Django واحد، قاعدة بيانات واحدة، تطبيقات (Apps) معزولة بحدود واضحة:

```text
backend/
├── config/          # settings, urls, wsgi/asgi, celery app
├── accounts/        # User العالمي، تسجيل الدخول بالجوال، الجلسات
├── schools/         # School, SchoolSettings, BellSchedule, SchoolDay, Period
├── memberships/     # SchoolMembership, MembershipRole, تبديل المدرسة
├── academics/       # AcademicYear, Semester, Grade, Section
├── students/        # Student, StudentEnrollment, استيراد نور
├── staff/           # استيراد المعلمين وربطهم بالعضويات
├── attendance/      # ✅ م6-8: Session/Mark/Change/QR + DayContext/DailySummary + selectors (monitoring/analytics)
├── excuses/         # ✅ م10: AbsenceExcuse/Target/Coverage/Attachment — تصنيف إداري
│                   #     (EXCUSED/UNEXCUSED) فوق سجل حضور خام لا يُمس + reconcile
├── student_warnings/ # ✅ م11: WarningRule + StudentWarning (Snapshots) + eligibility
│                   #     الاسم student_warnings لا warnings: حزمة عليا بهذا الاسم
│                   #     تُظلّل وحدة بايثون القياسية التي يستوردها Django
├── student_actions/ # ✅ م12: StudentAction — سجل ما فُعل (تواصل/مقابلة/تعهد/تسليم)
│                   #     منفصل عن «ما استحقه» (م11) وعن «ما صدر وطُبع» (documents)
├── documents/       # ✅ م12: GeneratedDocument + سجل قوالب مُصدَّر + WeasyPrint
│                   #     (HTML+CSS → PDF عربي RTL) وتخزين خاص خارج MEDIA_ROOT
├── referrals/       # ✅ م13: StudentReferral + Contribution + Event — طلب متابعة
│                   #     (لا تشخيص ولا إنذار)، ولقطة وقت الإحالة مجمدة. الإحالة
│                   #     الإدارية تترك أثرًا في student_actions داخل نفس المعاملة
├── counseling/      # CounselorAction, FollowUpPlan, متابعة المعلم
├── notifications/   # إشعارات داخل النظام (وقنوات مستقبلية)
├── reports/         # تقارير مجمعة و KPIs
├── subscriptions/   # Plan, SchoolSubscription
└── audit/           # AuditLog + خدمة تسجيل الأحداث
```

### قواعد الحدود بين الوحدات (Module Boundaries)

1. كل وحدة تصدّر واجهتها عبر `services/` و `selectors/` — **ممنوع** استيراد Models وحدة أخرى مباشرة داخل Views/Serializers لوحدة مختلفة؛ الاستيراد المسموح: خدمات الوحدة الأخرى أو Models عبر علاقات FK معلنة.
2. منطق الأعمال في **Service Layer** (`<app>/services/`)، والقراءات المعقدة في `selectors/`. الـ Views/Serializers طبقة رقيقة.
3. الأحداث بين الوحدات (مثل: اعتماد تحضير → تحديث الملخص اليومي) تمر عبر استدعاء خدمة صريح أو مهمة Celery — لا Django signals ضمنية للمنطق الجوهري (الـ signals مسموحة فقط للأمور العرضية مثل تسجيل Audit).
4. `audit/` و `notifications/` وحدتان أفقيتان يجوز لأي وحدة استدعاؤهما.

## 4. بنية الـ Frontend — Feature-Based

```text
frontend/src/
├── app/          # bootstrap, providers (Query, Router, Auth, Direction), layout
├── routes/       # تعريف المسارات + حراسة الأدوار (Route Guards عرضية فقط)
├── features/     # ميزة لكل مجلد: attendance/, students/, excuses/, referrals/ ...
│   └── <feature>/{components, hooks, api, types}
├── components/   # مكونات UI مشتركة (Button, Table, Card, EmptyState, ...)
├── api/          # عميل HTTP موحد + أنواع مولدة من OpenAPI
├── hooks/        # hooks عامة
├── stores/       # حالة عامة خفيفة (active school, session)
├── types/        # أنواع مشتركة
└── utils/        # أدوات (تطبيع الجوال، تواريخ، أرقام عربية...)
```

- **الصلاحيات في الواجهة عرضية فقط** (إخفاء أزرار) — الإنفاذ الحقيقي على الـ Backend حصراً.
- جلب البيانات عبر TanStack Query مع Polling للوحات (ADR-008).

## 5. Multi-Tenancy (ADR-002)

- **الاستراتيجية:** قاعدة بيانات واحدة + عمود `school_id` في كل جدول مرتبط ببيانات مدرسة (Shared DB, Shared Schema, Row-Level Isolation).
- **الإنفاذ بطبقات متراكبة:**
  1. **Middleware** يحدد `request.school` من `active_school_id` المخزن في الجلسة، ويتحقق أن للمستخدم `SchoolMembership` فعالة فيها. لا يُقبل `school_id` من المستخدم أبدًا دون هذا التحقق.
  2. **Custom Manager** (`SchoolScopedManager`) لكل Model مدرسي: الوصول القياسي يكون عبر `Model.objects.for_school(school)`; الوصول غير المحدود متاح فقط عبر manager صريح باسم مميز (`all_schools`) لاستخدامات المنصة والمهام الخلفية.
  3. **Base ViewSet/Permission** يفرض التقاطع: `queryset = queryset.filter(school=request.school)` في مكان واحد.
  4. **اختبارات عزل إلزامية** لكل Endpoint جديد (مدرسة A لا ترى بيانات B).
- **مدير المنصة** لا يملك Membership في المدارس ولا يرى بيانات الطلاب في التشغيل الاعتيادي؛ نطاقه وحدة `subscriptions/` وبيانات المدارس التعريفية فقط.

## 6. نموذج الهوية والعضوية (ADR-003)

```text
User (عالمي، فريد برقم الجوال المطبّع +9665XXXXXXXX)
  └── SchoolMembership (User × School، unique together, is_active)
        └── MembershipRole (SCHOOL_MANAGER | VICE_PRINCIPAL | COUNSELOR | TEACHER)
```

- المستخدم واحد عبر المنصة؛ يمكن أن يحمل أدوارًا مختلفة في مدارس مختلفة، وأكثر من دور في نفس المدرسة.
- `PLATFORM_ADMIN` سمة على مستوى User (ليست Membership) لأنها خارج نطاق المدارس.
- استيراد معلم برقم جوال موجود = إعادة استخدام الـ User وإنشاء Membership فقط.

## 7. المصادقة وتدفق الدخول (ADR-004)

```text
تسجيل الدخول: جوال مطبّع + كلمة مرور (Argon2id)
        ↓
Session Cookie: HttpOnly + Secure + SameSite=Lax، مع CSRF Token
        ↓
membership واحدة فعالة؟ → دخول مباشر وتعيين active_school
membership متعددة؟     → شاشة «اختر المدرسة» → POST يتحقق من العضوية → active_school في الجلسة
        ↓
تبديل المدرسة لاحقًا من أعلى النظام → نفس التحقق + حدث Audit: SWITCH_SCHOOL
```

- تطبيع الجوال السعودي إلى `+9665XXXXXXXX` (يقبل: `05x…`, `9665x…`, `+9665x…`, `5x…`).
- Rate limiting على تسجيل الدخول (بالجوال وبالـ IP) عبر Redis + قفل مؤقت تصاعدي ضد Brute Force.
- لا JWT في LocalStorage إطلاقًا.

## 8. قرارات نطاق الحضور الجوهرية

- **لا جدول حصص للمعلمين في MVP** (ADR-005): الحصة الحالية تُستنتج من وقت الخادم مقابل `BellSchedule` النشط، والمعلم يختار الفصل بنفسه (مع دعم QR بالـ Token لاحقًا).
- **التحضير بالاستثناء** (ADR-006): `AttendanceSession` معتمدة تعني أن كل طالب بلا `AttendanceMark` حاضر. نخزن فقط `ABSENT` و `LATE` (مع `arrival_time` → `late_minutes` محسوبة).
- **غياب السجل ≠ حضور:** لا استنتاج لأي حالة طالب ما لم تكن الجلسة `SUBMITTED`. الفصول غير المحضرة حالتها `INCOMPLETE` في كل التحليلات، ويوم الطالب لا يصنف `FULL_DAY_ABSENCE` إن وُجدت حصة غير محضرة.
- **منع التكرار بقيود قاعدة البيانات:** Unique على `(school, section, date, period)` + `transaction.atomic` + معالجة `IntegrityError` برسالة عربية (`ATTENDANCE_ALREADY_SUBMITTED`).
- **نافذة تعديل المعلم:** `attendance_edit_window_minutes` من إعدادات المدرسة؛ بعدها التعديل للوكيل فقط، وكل تعديل حدث Audit.

## 9. API

- كل الواجهات تحت `/api/v1/` مع OpenAPI Schema (drf-spectacular) وتوليد Types للـ Frontend.
- تنسيق الخطأ الموحد:

```json
{ "code": "ATTENDANCE_ALREADY_SUBMITTED", "message": "تم اعتماد حضور هذا الفصل مسبقاً.", "details": {} }
```

- الـ Endpoints المدرسية لا تستقبل `school_id` في الجسم/المسار — المدرسة تُستمد من الجلسة (`active_school`) بعد التحقق من العضوية.
- حدود الواجهات تتبع الوحدات: `/api/v1/attendance/…`, `/api/v1/students/…`, `/api/v1/referrals/…` إلخ.

## 10. المهام غير المتزامنة

| الآلية | الاستخدام |
|---|---|
| Celery | معالجة Excel، توليد PDF، إصدار الإنذارات، الإشعارات، الملخصات اليومية |
| Celery Beat | فحص الفصول غير المحضرة (`unprepared_period_alert_minutes`)، تحديث `DailyAttendanceSummary`، فحص الاشتراكات |
| Redis | Cache، Celery broker، Rate limiting، حالة مؤقتة (مثل معاينة الاستيراد) — ليس مصدر بيانات أساسيًا |

كل مهمة Celery تكون **Idempotent** (إعادة التشغيل لا تكرر إنذارًا أو ملخصًا).

## 11. التحديث الحي للوحات (ADR-008)

Polling عبر TanStack Query (`refetchInterval` 30–60 ثانية للوحة الوكيل). لا WebSockets في MVP.

## 12. PWA (ADR-007)

Manifest عربي RTL + icons فعلية + Workbox generateSW. يخزن Service Worker ملفات
build ذات hash فقط، ويعامل `/api/**` كـ`NetworkOnly`. **لا Offline Attendance** ولا
background sync للعمليات الحساسة. update prompt بقرار المستخدم، وحدود login/logout/
school switch تمسح TanStack Query وأي cache حساس قديم. التفاصيل في [PWA.md](PWA.md).

## 13. طوبولوجيا التشغيل

```text
backend (Django/gunicorn) ── postgres
        │                └── redis
        ├── worker (Celery)
        ├── beat (Celery Beat)
        └── frontend (Vite dev / build → static)
```

الإنتاج المحلي المماثل يستخدم `docker-compose.production.yml`: gunicorn + nginx
production build + PostgreSQL + Redis + worker + beat، مع volumes خاصة مشتركة
للملفات. nginx يطبق SPA fallback وCSP ورؤوس cache منفصلة للـHTML/SW/assets/API.
إعداد النشر الفعلي يضيف TLS أمام nginx؛ انظر [PRODUCTION_HARDENING.md](PRODUCTION_HARDENING.md).

## 14. فهرس ADRs

| ADR | القرار |
|---|---|
| [ADR-001](adr/ADR-001-modular-monolith.md) | Modular Monolith بدل Microservices |
| [ADR-002](adr/ADR-002-multi-tenancy.md) | عزل الصفوف بـ school_id في قاعدة واحدة |
| [ADR-003](adr/ADR-003-global-user-memberships.md) | مستخدم عالمي + عضويات مدرسية |
| [ADR-004](adr/ADR-004-session-auth.md) | Session Cookies + Argon2 بدل JWT |
| [ADR-005](adr/ADR-005-no-teacher-timetable.md) | لا جدول معلمين في MVP |
| [ADR-006](adr/ADR-006-attendance-by-exception.md) | تسجيل الحضور بالاستثناء |
| [ADR-007](adr/ADR-007-pwa-online-first.md) | PWA Online-First بدون Offline Attendance |
| [ADR-008](adr/ADR-008-polling-not-websockets.md) | Polling بدل WebSockets |
| [ADR-009](adr/ADR-009-national-id-protection.md) | تشفير رقم الهوية + HMAC lookup hash |
| [ADR-010](adr/ADR-010-immutable-history.md) | التاريخ غير قابل للحذف (Snapshots + سجل تغيير) |

## 15. الوثائق المرافقة

- [ERD.md](ERD.md) — الكيانات والعلاقات والقيود والفهارس.
- [PERMISSIONS.md](PERMISSIONS.md) — مصفوفة الصلاحيات.
- [SECURITY.md](SECURITY.md) — النموذج الأمني.
- [SAAS_PLANS.md](SAAS_PLANS.md) — باقات SaaS والتسعير الوصفي.
- [SUBSCRIPTIONS.md](SUBSCRIPTIONS.md) — دورة حياة الاشتراك.
- [ENTITLEMENTS.md](ENTITLEMENTS.md) — حدود وميزات الباقات.
- [PLATFORM_ADMIN.md](PLATFORM_ADMIN.md) — لوحة إدارة المنصة وحدودها.
- [SUBSCRIPTION_ACCESS_POLICY.md](SUBSCRIPTION_ACCESS_POLICY.md) — سياسة الوصول حسب حالة الاشتراك.
- [PRODUCTION_HARDENING.md](PRODUCTION_HARDENING.md) — إعدادات وأسرار وHTTPS وجلسات الإنتاج.
- [PWA.md](PWA.md) — manifest وService Worker وسياسة cache والتحديث.
- [FRONTEND_SECURITY.md](FRONTEND_SECURITY.md) — CSP وحدود الجلسة والمستأجر في الواجهة.
- [UX_ACCESSIBILITY.md](UX_ACCESSIBILITY.md) — responsive وRTL وخط accessibility الأساسي.
- [AUTHENTICATION.md](AUTHENTICATION.md) — المصادقة كما نفذت (المرحلة 2).
- [MULTI_TENANCY.md](MULTI_TENANCY.md) — تعدد المستأجرين كما نفذ + الثوابت الأمنية (المرحلة 2).
- [PHASE_PLAN.md](PHASE_PLAN.md) — خطة المراحل 0–20 ومعايير الخروج.

> حالة التنفيذ: §6 (الهوية والعضوية) و§7 (المصادقة) نفذا في المرحلة 2 مع فارقين عن الخطة:
> Rate limiting عبر Django cache فوق Redis، وأخطاء السياق تحمل رموزًا دقيقة
> (MEMBERSHIP_SUSPENDED/SCHOOL_SUSPENDED/INVALID_SCHOOL_MEMBERSHIP) بدل رمز واحد عام.
>
> المرحلة 3: SchoolSettings + AcademicYear/Semester + BellSchedule/BellPeriod +
> SchoolWeekDay نفذت (انظر SCHOOL_SETTINGS.md / ACADEMIC_CALENDAR.md / BELL_SCHEDULES.md)
> مع أساس موحد للـ endpoints المدرسية: `memberships/api_base.SchoolScopedAPIView`.
> OpenAPI (drf-spectacular) مؤجل كدين تقني موثق — الواجهة تستخدم أنواعًا يدوية مطابقة.
>
> المرحلة 4: Students/Grades/Sections/Enrollments + استيراد نور عبر Celery نفذت
> (STUDENTS.md / STUDENT_IMPORT.md / IDENTIFIER_SECURITY.md).
>
> المرحلة 5: **دين OpenAPI سُدد** (OPENAPI.md — schema/docs/CI + قاعدة serializer-first
> للمراحل القادمة). StaffProfile + استيراد المعلمين + الدعوات + كلمة المرور المؤقتة
> نفذت (STAFF.md / STAFF_IMPORT.md / INVITATIONS.md).
>
> **قرار المرحلة 6 المسبق (هوية المعلم في الحضور):** AttendanceSession سيحفظ
> `submitted_by_membership` (FK إلى SchoolMembership) — لا User وحده، لأن المستخدم
> متعدد المدارس؛ العضوية تحدد هويته داخل المدرسة، ومنها StaffProfile.display_name
> عبر `get_current_staff_profile` الجاهز.
