# الطلاب — كما نفذ في المرحلة 4

## Student vs StudentEnrollment (الفصل الجوهري)

- **Student** = هوية الطالب داخل المدرسة: الهوية (مشفرة+hash+masked)، الاسم، رقم الطالب، بيانات ولي الأمر، status (ACTIVE/INACTIVE/TRANSFERRED/GRADUATED/ARCHIVED). **لا grade/section عليه.**
- **StudentEnrollment** = وضعه الدراسي في فترة: (academic_year, grade, section, status, enrolled_at, ended_at). الانتقال بين الفصول = **إنهاء القيد القديم (ended_at + TRANSFERRED) وإنشاء قيد جديد** — التاريخ لا يعدل في مكانه ولا يحذف (ADR-010).
- Enrollment يمثل **العام الدراسي كاملًا** (قرار موثق): لا ربط بالفصل الدراسي (Semester) — التغير داخل السنة سجل جديد بتواريخ.

## Grade / Section

- `Grade`: name/code/sequence — `UNIQUE(school, code)`؛ الـ code مطبع (SEC_1...) والاسم للعرض.
- `Section`: تابعة لصف — `UNIQUE(school, grade, code)`؛ التطبيع يمنع «1/01/فصل 1» من إنشاء فصول مكررة.
- تنشأ أثناء **اعتماد** الاستيراد فقط (get_or_create) — المعاينة تعرض «سيتم إنشاء…» قبلها.

## القيد الحالي

- قيد DB: `UNIQUE(student, academic_year) WHERE status='ACTIVE'` — قيد فعال واحد لكل طالب/عام.
- Selectors موحدة (`students/services/enrollments.py`): `get_current_enrollment`, `students_for_section(school, section, academic_year)` — جاهزة لشاشة الحضور (المرحلة 6) بلا تكرار منطق.
- `validate_enrollment_integrity`: كل الأطراف (student/grade/section/year) من نفس المدرسة — Cross-Tenant FK مرفوض حتى بمعرفات يدوية (مغطى باختبار).

## قواعد المستأجر والعرض

- كل الاستعلامات عبر `request.school`؛ المعرفات الأجنبية 404؛ القوائم لا تسرب.
- القوائم تعرض `national_id_masked` فقط (`******1234`) — الرقم الكامل لا يظهر في المرحلة 4 (والـ Admin كذلك).
- البحث: بالاسم `icontains`، وبالهوية **مطابقة تامة عبر HMAC** (أي صيغة إدخال تطبع أولًا) — لا `contains` على قيمة مشفرة.
- الترقيم إلزامي (25 افتراضيًا، حد أقصى 100) وquery ثابت الاستعلامات (Prefetch للقيد الفعال) — محروس باختبار ≤ 10.

## الصلاحيات

قراءة: MANAGER/VICE/COUNSELOR — الاستيراد: MANAGER فقط — TEACHER: لا قائمة عامة (وصوله لطلاب فصله يأتي مع الحضور في المرحلة 6).

## دورة الحياة والحذف النهائي (المرحلة 4.1)

انظر [STUDENT_LIFECYCLE.md](STUDENT_LIFECYCLE.md) و[DATA_PURGE.md](DATA_PURGE.md):
حالات الخروج (متخرج/منتقل/منسحب/غير نشط) تغلق القيد الفعال؛ مفقودو نور يراجعون
ويصنفون ولا يحذفون تلقائيًا؛ والحذف النهائي (فردي/جماعي عبر Celery) للمدير حصرًا
بمعاينة وتأكيد كتابي وتنظيف تخزين وAudit بلا PII.
