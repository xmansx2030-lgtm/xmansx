# التقويم الأكاديمي — كما نفذ في المرحلة 3

## AcademicYear

- الحقول: name، start_date، end_date، status (UPCOMING / ACTIVE / CLOSED / ARCHIVED).
- **قيد DB:** `UNIQUE(school) WHERE status='ACTIVE'` — عام نشط واحد لكل مدرسة (الحكم النهائي ضد التزامن) + Check `start < end`.
- مدرستان مختلفتان تملكان عامين نشطين معًا (مغطى باختبار).

### انتقالات الحالة

```text
UPCOMING ── activate ──► ACTIVE ── close ──► CLOSED ── archive ──► ARCHIVED
```

- **activate** (`transaction.atomic` + `select_for_update`): يغلق العام والفصل النشطين الحاليين ثم يفعّل العام القادم، بحيث لا يبقى فصل نشط تابع لعام مغلق. تفعيل عام نشط أصلًا → `409 ACADEMIC_YEAR_ALREADY_ACTIVE`، وإعادة تفعيل عام مغلق أو مؤرشف مرفوضة.
- **close** يغلق الفصل النشط التابع للعام في العملية الذرية نفسها.
- يقبل إنشاء العام `activate=true` اختياريًا؛ الإنشاء والتفعيل عندها معاملة واحدة تتراجع كاملة إذا تعذر التفعيل. السلوك الافتراضي يبقى إنشاء عام `UPCOMING`.
- تعديل حدود العام مرفوض إذا كان سيترك أي فصل قائم خارج الحدود الجديدة.
- **لا DELETE** — الأرشفة (Soft Archive) بدل الحذف المدمر (ADR-010)، والعام النشط لا يؤرشف قبل إغلاقه.

## Semester

- الحقول: name، sequence، start_date، end_date، status (UPCOMING / ACTIVE / CLOSED). لا افتراض لعدد الفصول (2 أو 3 أو أكثر — sequence 1..10).
- `school` denormalized يحدده الخادم من العام — لا يقبل من العميل.
- **قيود DB:** `UNIQUE(academic_year, sequence)` + `UNIQUE(school) WHERE ACTIVE` + Check `start <= end`.

### قواعد التواريخ (Service — `INVALID_SEMESTER_RANGE`)

```text
semester.start >= year.start
semester.end   <= year.end
semester.start <= semester.end
```

ولا يسمح بتداخل نطاق فصلين داخل العام نفسه، في الإنشاء أو التعديل.

### التفعيل

`activate_semester` ذري بنفس نمط العام: لا يقبل إلا فصلًا `UPCOMING` تابعًا للعام `ACTIVE`، ويغلق الفصل النشط الحالي للمدرسة ثم يفعّل الجديد. تفعيل المفعل → `409 SEMESTER_ALREADY_ACTIVE` وإعادة تفعيل فصل مغلق مرفوضة. `current_semester` يستنتج من status (لا حقل منفصل مخزن).

يقبل إنشاء الفصل `activate=true` اختياريًا؛ الإنشاء والتفعيل عندها معاملة واحدة تتراجع كاملة إذا تعذر التفعيل.

## APIs

```text
GET/POST   /api/v1/school/academic-years/
PATCH      /api/v1/school/academic-years/{id}/
POST       /api/v1/school/academic-years/{id}/activate|close|archive/
GET/POST   /api/v1/school/academic-years/{id}/semesters/
PATCH      /api/v1/school/semesters/{id}/
POST       /api/v1/school/semesters/{id}/activate/
```

كل الكائنات تجلب بـ `id + school=request.school` → معرفات مدرسة أخرى = 404 (مغطى باختبارات IDOR). Audit: `ACADEMIC_YEAR_CREATED/UPDATED/ACTIVATED/CLOSED/ARCHIVED`, `SEMESTER_CREATED/UPDATED/ACTIVATED`.
