# استيراد الطلاب من نور — كما نفذ في المرحلة 4

## الصيغ المدعومة

`.xlsx` فقط (openpyxl). ‏`.xls` و`.xlsm` (ماكرو) و`.xlsb` مرفوضة برسالة واضحة. حد الحجم 10MB وحد الصفوف 10,000.

## أمان الملف (قبل أي parsing)

1. الامتداد والحجم.
2. **فحص ZIP** (xlsx = zip): عدد المدخلات ≤ 200، الحجم غير المضغوط ≤ 60MB (zip bomb)، وجود `[Content_Types].xml` (ملف xlsx حقيقي).
3. openpyxl بـ `read_only + data_only`: **لا تنفيذ صيغ** (formula injection) وذاكرة محدودة. عند التصدير مستقبلًا يجب تعقيم الخلايا التي تبدأ بـ `=+-@` (موثق هنا كسياسة).

## الحقول والمطابقة (Mapping)

- الحقول: national_id, full_name, grade, section, student_number, guardian_name, guardian_mobile.
- اقتراح تلقائي من aliases نور المعروفة («السجل المدني» و«هوية الطالب»…) — غير المؤكد يترك للمستخدم في واجهة المطابقة.
- الإلزامي: full_name + grade + section + (**national_id** أو student_number كبديل موثوق). الاسم وحده لا يطابق أبدًا.

## Pipeline

```text
Upload (فحوص أمنية + اقتراح mapping) → 201
POST process {mapping} → 202 → Celery: parse → normalize → validate → compare → staging
GET job (polling) → READY_FOR_REVIEW
GET preview?category= → صفوف مصنفة مرقمة
POST commit (متزامن، ذري) → COMPLETED | 409 (stale/already/…)
```

## التطبيع

نصوص: NFKC + إزالة محارف العرض الصفرية + ضغط مسافات (غير مدمر للاسم). أرقام عربية→لاتينية. الصفوف: «الأول الثانوي/اول ثانوي/1 ثانوي» → `SEC_1` (غير المعروف لا يخمن Stage — code من النص وsequence=0 ويظهر في المعاينة). الفصول: «1/01/1/1/فصل 1» → `1`. جوال ولي الأمر يطبع إن صح ويترك فارغًا إن لا (ليس unique — عدة أبناء).

## المعاينة والتصنيف

`NEW / EXISTING_UNCHANGED / EXISTING_UPDATED / SECTION_CHANGED / GRADE_CHANGED / ERROR / DUPLICATE_IN_FILE` + ملخص بالأعداد + «سيتم إنشاء (صفوف/فصول)» + **المفقودون من الملف: عرض فقط — الملف ليس Source of Truth للحذف** (وضع `UPDATE_OR_CREATE`؛ ‏`FULL_SYNC` مستقبلي بمراجعات أقوى). تكرار الهوية في الملف يعلم كل التكرارات (لا اختيار عشوائي). أخطاء الصف برسائل عربية مرقمة بسطر الملف.

## الاعتماد (Commit)

- متزامن داخل `transaction.atomic` + `select_for_update` على الـ Job.
- **Idempotency:** ‏COMPLETED → ‏`IMPORT_ALREADY_COMMITTED` (409)؛ ‏PROCESSING/IMPORTING → ‏`IMPORT_ALREADY_RUNNING`؛ وقيد DB «job جارٍ واحد لكل مدرسة».
- **Stale preview protection:** إعادة مقارنة كاملة ضد قاعدة البيانات الحالية؛ أي اختلاف عن المعاينة المعتمدة → تحديث الصفوف والملخص (يثبت) ثم `IMPORT_PREVIEW_STALE` (409) ليعيد المستخدم المراجعة. تغير العام النشط منذ الرفع → `ACTIVE_ACADEMIC_YEAR_REQUIRED` (الـ Job يحفظ العام وقت الإنشاء).
- التطبيق: إنشاء صفوف/فصول (Audit لكل جديد) → طلاب جدد (هوية مشفرة) → تحديثات (Audit بأسماء الحقول لا القيم) → انتقالات (إنهاء + إنشاء قيد).

## Celery والملفات المؤقتة

- المهمة تستلم `job_id` فقط وتستمد المدرسة من `job.school` (لا request.school في الخلفية، ولا school_id خام).
- فحص الحالة قبل العمل — retry لا يكرر معالجة منتهية. لا retry لأخطاء الملف (نهائية). Stack traces للسجلات/Sentry فقط — المستخدم يرى رمزًا آمنًا.
- **PII مؤقت:** الـ staging يخزن الهوية مشفرة+hash+masked (لا plaintext)، ويحذف مع ملف Excel بعد COMPLETED/CANCELLED — لا تنزيل للملف الأصلي إطلاقًا، والملف في مسار مولد (لا اسم المستخدم).

## Audit

`STUDENT_IMPORT_UPLOADED/VALIDATED/COMMITTED/FAILED` — الاعتماد يسجل **ملخصًا** (created/updated/enrollment_changes/unchanged/errors/missing) لا صفًا لكل طالب؛ التغييرات المهمة تتبع عبر: Audit `STUDENT_UPDATED` لكل تحديث بيانات + سجلات Enrollment التاريخية نفسها (السياسة موثقة هنا).

## قياس الأداء (بيئة التطوير — 2026-08-18)

| rows | parse+preview | commit | parse peak mem |
|---|---|---|---|
| 500 | 0.47s | 0.88s | 3.9MB |
| 1500 | 2.74s | 2.39s | 9.1MB |
| 3000 | 8.78s | 4.05s | 18.6MB |

(أمر `manage.py benchmark_import` — تطوير فقط، ينظف بياناته.)
