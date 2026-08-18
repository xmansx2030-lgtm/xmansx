# إعدادات المدرسة — كما نفذت في المرحلة 3

## الحقول (`schools.SchoolSettings` — OneToOne مع School)

| الحقل | النوع/القيود | ملاحظات |
|---|---|---|
| ministry_school_number | نص اختياري | |
| education_stage | ELEMENTARY / MIDDLE / SECONDARY / MULTI_STAGE | العربية للعرض فقط |
| city | نص اختياري | |
| official_principal_name | نص اختياري | **للطباعة والنماذج فقط — ليس مصدر صلاحية أبدًا** |
| logo | ImageField | انظر استراتيجية الشعار |
| timezone | افتراضي Asia/Riyadh | كل datetimes timezone-aware؛ لا افتراض بقاء كل المدارس في نفس المنطقة |
| attendance_edit_window_minutes | 0–120، افتراضي 15 | إعداد فقط الآن — التفعيل في المرحلة 6 |
| unprepared_period_alert_minutes | 1–120، افتراضي 25 | إعداد فقط الآن — التفعيل في المرحلة 7 |

- اسم المدرسة يبقى في `School.name` (لا تكرار) — واجهة الإعدادات تعدله بصلاحية المدير.
- المدير/الوكلاء/المرشدون يعرضون **قراءة فقط** من العضويات الفعالة (`_staff_by_role`) — لا أسماء نصية كمصدر صلاحية.
- قيود DB: OneToOne (إعداد واحد لكل مدرسة) + Check على نطاقات الدقائق.

## الصلاحيات

| الدور | settings |
|---|---|
| SCHOOL_MANAGER | قراءة + كتابة |
| VICE_PRINCIPAL / COUNSELOR | قراءة فقط |
| TEACHER | محجوب كليًا (403) |
| PLATFORM_ADMIN | لا يعدل الإعدادات التشغيلية من APIs العادية |

الإنفاذ عبر `SchoolScopedAPIView` (`memberships/api_base.py`): read_roles/write_roles حسب HTTP method — الأساس الموحد لكل endpoints المدرسية القادمة.

## قواعد المستأجر

- `GET/PATCH /api/v1/school/settings/` تعمل على `request.school` حصرًا — لا يوجد أصلًا معامل school_id.
- Mass assignment ممنوع: `school`, `school_id`, `status`, `slug`, `created_by` ليست في Serializer الإدخال (مغطى باختبار يرسلها ويثبت تجاهلها).
- Audit: `SCHOOL_SETTINGS_UPDATED` / `SCHOOL_NAME_UPDATED` بالحقول المتغيرة فقط (بلا محتوى ملفات).

## استراتيجية الشعار

- التحقق الرباعي (`common/validators.py`): حجم ≤ 2MB، امتداد {png, jpg, jpeg, webp}، **محتوى فعلي عبر Pillow** (يرفض الامتداد المزيف والصيغ غير المدعومة كـ BMP المسمى png)، وسلامة الصورة (`verify`).
- اسم الملف المخزن مولد (`school_logos/school_{id}/logo.ext`) — الاسم الأصلي لا يستخدم.
- التخزين الحالي: **Local media للتطوير فقط** (`MEDIA_ROOT` + رابط عبر Django عند DEBUG فقط) — موثق صراحة أنه ليس افتراض إنتاج؛ Object Storage الخاص + Signed URLs يأتي في مرحلته، وحقل ImageField يجعل التبديل تغيير storage backend فقط.

## Caching

قرار موثق: **لا cache في هذه المرحلة** — القراءات صف واحد + استعلامات محدودة (اختبار query count ≤ 8). عند إضافته لاحقًا: مفاتيح tenant-aware (`school:{id}:settings`) مع invalidation عند التعديل.
