# تعدد المستأجرين — كما نفذ في المرحلة 2

## النموذج

```text
User (عالمي — جوال فريد)
  └── SchoolMembership  (UNIQUE(user, school)، status: ACTIVE/INVITED/SUSPENDED/LEFT)
        └── SchoolMembershipRole (UNIQUE(membership, role)، role: SCHOOL_MANAGER/VICE_PRINCIPAL/COUNSELOR/TEACHER)

School (المستأجر — status: ACTIVE/SUSPENDED/ARCHIVED)
```

- **ممنوع** `User.school_id` و`User.role` — الانتماء والأدوار عبر العضوية حصرًا.
- تعدد المدارس: نفس User/جوال/كلمة مرور بعضويات متعددة. تعدد الأدوار: صفوف أدوار متعددة للعضوية.
- `PLATFORM_ADMIN` = `User.is_superuser` (خاصية `is_platform_admin`) — لا عضوية مدرسة وهمية، ولا bypass ضمني في APIs المدرسية.

## المدرسة النشطة (Session Context)

- `active_school_id` يعيش في **الجلسة** فقط — ليس حقيقة دائمة في قاعدة البيانات.
- **قيمة الجلسة ليست مصدر ثقة:** `TenantContextMiddleware` يعيد التحقق كل طلب:

```text
session.active_school_id موجود؟
  ├─ لا عضوية للمستخدم فيها      → INVALID_SCHOOL_MEMBERSHIP + إزالة المفتاح
  ├─ العضوية SUSPENDED/LEFT      → MEMBERSHIP_SUSPENDED / INVALID + إزالة المفتاح
  ├─ المدرسة SUSPENDED           → SCHOOL_SUSPENDED (المفتاح يبقى — عودتها تعيد السياق)
  ├─ المدرسة ARCHIVED            → INVALID + إزالة المفتاح
  └─ كل شيء سليم                → request.school / request.membership / request.school_roles
```

## التبديل — `POST /api/v1/session/active-school/`

الاستثناء الوحيد الذي يقبل `school_id` من العميل، ويتحقق: مصادقة → عضوية موجودة → ACTIVE → مدرسة ACTIVE، ثم يحدّث الجلسة + `cycle_key()` + Audit `SWITCH_SCHOOL`. مدرسة غير موجودة ومدرسة ليست له تعيدان نفس الرد (لا كشف وجود).

بعد الدخول: عضوية فعالة واحدة (بمدرسة نشطة) → اختيار تلقائي؛ أكثر → شاشة «اختر المدرسة».

## طبقة الصلاحيات (`memberships/permissions.py`)

- `has_school_role / has_any_school_role / require_school_role` — مركزية، ممنوع `if role ==` متناثرة.
- `ActiveSchoolRequired` — أساس endpoints المدرسية: يرفع الرمز الدقيق (`ACTIVE_SCHOOL_REQUIRED` أو سبب السياق الفاسد).
- `school_role_required("TEACHER", ...)` — مصنع Permission للأدوار.
- الدور مقيد بعضويته: `school_roles` تُشتق حصرًا من عضوية المدرسة النشطة — دور A لا يعمل في B (مغطى باختبار).

## نمط الخدمات المستقبلية (إلزامي من المرحلة 3+)

```python
def get_students(*, school, actor):  # school و actor صريحان دائمًا
    ...
```

العزل طبقات متراكبة — QuerySet Scoping ليس خط الدفاع الوحيد:
`Middleware context → Permissions → Explicit service scope → QuerySet scope → Isolation tests`

## الواجهة (Frontend)

- الحراسة عرضية فقط (RequireAuth / RequireActiveSchool) — الإنفاذ على الـ Backend.
- التبديل يفرغ كل cache غير `["me"]` (`removeQueries`) — لا Flash لبيانات مدرسة سابقة (مغطى باختبار يزرع بيانات مدرسية قديمة ويتأكد من زوالها).
- مفاتيح البيانات المدرسية المستقبلية: `["school", activeSchoolId, ...]` عبر `schoolScopedKey()`.

## الدعوات (المرحلة 5)

إضافة مستخدم موجود لمدرسة جديدة لا تتم بصمت: عضوية `INVITED` يقبلها/يرفضها صاحبها
(انظر INVITATIONS.md). الرفض `DECLINED` لا يحذف، وإعادة الدعوة إجراء صريح.
دليل الموظفين لا يكشف مدارس المستخدم الأخرى أو أدواره فيها (STAFF.md).

## Security Invariants (ثوابت ملزمة لكل المراحل)

1. **A user cannot access a school without an ACTIVE membership.**
2. **A role is scoped to one membership/school.**
3. **Changing active school never grants new permissions.**
4. **`school_id` supplied by the client is never trusted as authorization** (الاستثناء الوحيد: switch، وبتحقق كامل).
5. **Frontend isolation is UX only; backend isolation is authoritative.**

## PostgreSQL RLS

مفعّل ومفروض كـ Defense-in-Depth، وليس بديلًا عن Django scoping — انظر ملحق
ADR-002. تحمي السياسات جذر المدرسة والجداول المباشرة والتابعة، وتفشل إلى
الإغلاق عند غياب `app.current_school_id`. كما تمنع constraint triggers أي FK
يربط صفين من مدرستين مختلفتين.
