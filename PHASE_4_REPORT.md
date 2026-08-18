# PHASE 4 REPORT — Students + Grades + Sections + Noor Excel Import

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 129) تحققت بتشغيل فعلي موثق أدناه.

## Models

`Grade` (UNIQUE school+code)، `Section` (UNIQUE school+grade+code + تكامل school)، `Student` (هوية مشفرة/hash/masked، UNIQUE(school, hash)، UNIQUE(school, student_number) جزئي)، `StudentEnrollment` (partial UNIQUE: قيد ACTIVE واحد لكل طالب/عام)، `StudentImportJob` (يحفظ school+academic_year وقت الإنشاء + قيد «job جارٍ واحد لكل مدرسة») + `StudentImportRow` (staging مؤقت بلا plaintext).

## Student identity strategy

المطابقة: hash الهوية أولًا → student_number بديلًا موثوقًا — **الاسم وحده لا يطابق أبدًا**. الهوية فريدة داخل المدرسة لا عالميًا (لا ربط تلقائي بين مدارس). Student = هوية؛ Enrollment = الوضع الدراسي التاريخي (الانتقال = إنهاء قيد + إنشاء قيد).

## Encryption / HMAC lookup

`common/security/identifiers.py`: تطبيع (أرقام عربية، 10 خانات تبدأ 1/2) + Fernet/MultiFernet + HMAC-SHA256 بمفتاح منفصل + تقنيع. المفاتيح من البيئة؛ **الإنتاج يفشل بدونها — مثبت فعليًا** (`ImproperlyConfigured: Missing FIELD_ENCRYPTION_KEYS`) ويرفض قيم dev-only. خطة التدوير موثقة في [docs/IDENTIFIER_SECURITY.md](docs/IDENTIFIER_SECURITY.md).

## Grades / Sections / Enrollment history

التطبيع يمنع التكرار الصوري («اول ثانوي»=«الأول الثانوي»، «01»=«1»)؛ تنشأ عند الاعتماد فقط مع Audit؛ تاريخ القيد محفوظ دائمًا (old TRANSFERRED+ended_at، new ACTIVE) — مثبت باختبار Backend وE2E.

## Import architecture / Supported files / Excel security

Pipeline كامل (Upload→Validate→Parse→Map→Normalize→Validate→Compare→Preview→Approve→Commit→Report) موثق في [docs/STUDENT_IMPORT.md](docs/STUDENT_IMPORT.md). ‏xlsx فقط (openpyxl read_only+data_only — لا تنفيذ صيغ)؛ ‏xls/xlsm مرفوضة؛ 10MB/10K صف؛ فحص ZIP ضد القنابل (مدخلات/حجم غير مضغوط/بنية xlsx).

## Mapping / Preview categories / Comparison

اقتراح تلقائي من aliases نور + واجهة مطابقة يدوية عند الغموض (مغطى باختبار رؤوس غير معروفة). فئات: جدد/بلا تغيير/تحديث/انتقال فصل/تغير صف/أخطاء/تكرارات + «سيتم إنشاء…» + **المفقودون من الملف (عرض فقط — لا حذف أبدًا، وضع UPDATE_OR_CREATE)**.

## Commit / Idempotency / Stale preview

Commit متزامن ذري بـ select_for_update؛ اعتماد مكرر → `IMPORT_ALREADY_COMMITTED` بلا تكرار بيانات (اختبار)؛ **إعادة مقارنة كاملة عند الاعتماد**: تغير الواقع منذ المعاينة → تحديث المعاينة (يثبت خارج rollback) + `IMPORT_PREVIEW_STALE` 409 (اختبار سيناريو كامل يتضمن الاعتماد الناجح بعد المراجعة)؛ تغير العام النشط → `ACTIVE_ACADEMIC_YEAR_REQUIRED` (الـ Job يحفظ عامه).

## Celery

parse/preview عبر Worker (202 + polling)؛ tenant safety: المهمة تستمد المدرسة من `job.school` حصرًا؛ idempotent بفحص الحالة؛ فشل الملف → FAILED برمز آمن (stack traces للسجلات فقط). **worker import مثبت فعليًا داخل Docker عبر E2E** (polling انتظر الـ Worker الحقيقي).

## Permissions / Tenant isolation

الاستيراد MANAGER فقط (vice/teacher → 403 — اختبار)؛ القراءة MANAGER/VICE/COUNSELOR؛ TEACHER بلا قائمة عامة (403 + UI مخفية). العزل: student/job/grade/section أجنبية → 404، commit لـ job أجنبي → 404، القوائم لا تسرب، cross-school enrollment مرفوض — كلها باختبارات فعلية + E2E (مدير A/معلم B: fetch مباشر 403).

## Audit

الأحداث الـ 12 الجديدة منفذة؛ سياسة الـ bulk موثقة: ملخص للاعتماد + `STUDENT_UPDATED` لكل تحديث بيانات (بأسماء الحقول لا القيم) + تاريخ Enrollment نفسه كأثر — لا هوية كاملة في أي metadata.

## Frontend

صفحة «الطلاب» (بحث اسم/هوية دقيقة، فلاتر صف/فصل، ترقيم، masked، حارس دور للمعلم، nav حسب الدور) + Wizard من 5 خطوات (سحب وإفلات، مطابقة معبأة بالاقتراح، معاينة بفئات وأعداد وأخطاء مرقمة بالصف، تنبيه المفقودين، ملخص تأكيد، نتيجة) مع polling أثناء المعالجة وقفزة تلقائية للمعاينة المحدثة عند stale. مفاتيح tenant-aware + إبطال قوائم الطلاب بعد الاعتماد.

## API endpoints

`GET /students/(+{id})`, `GET /grades/`, `GET /sections/`, `POST /student-imports/`, `GET /{id}/`, `POST /{id}/process|commit|cancel/`, `GET /{id}/preview/` — كل الرموز المطلوبة (البند 120) منفذة برسائل عربية.

## Tests (Backend)

**174/174 PASS** (127 regression + 47 جديدة): تشفير/HMAC/تطبيع (17)، تدفق الاستيراد الكامل (11: جدد/مطابق/انتقال/مفقودون/تحديث اسم/أخطاء وتكرارات/idempotency/stale/تغير العام/mapping يدوي)، أمان الملفات (8: نص باسم xlsx، zip تالف، xlsm، xls، حجم، قنبلة مدخلات، قنبلة توسع، صيغ لا تنفذ)، قوائم وعزل (11).

## E2E results

**8/8 PASS** ضد Docker الحقيقي (Worker/Postgres/Redis): 5 regression + 3 جديدة — الرحلة الكاملة (رفع→مطابقة→معاينة جدد(8)→اعتماد→قائمة بأسماء وهويات مقنعة + بحث HMAC + ثبات بعد reload)، التحديث (انتقال(1)/جديد(1)/بلا تغيير(6) + المفقود محفوظ + تاريخ صحيح)، والعزل. الـ fixtures تولد بهويات فريدة لكل تشغيل (global-setup) لنتائج حتمية.

## Performance results (بيئة التطوير)

| rows | parse+preview | commit | parse peak mem |
|---|---|---|---|
| 500 | 0.47s | 0.88s | 3.9MB |
| 1500 | 2.74s | 2.39s | 9.1MB |
| 3000 | 8.78s | 4.05s | 18.6MB |

قائمة الطلاب: استعلامات ثابتة (Prefetch) محروسة باختبار ≤ 10 مع ترقيم إلزامي.

## Fresh migration / Docker

قاعدة جديدة كليًا → migrate من الصفر PASS؛ `makemigrations --check` نظيف؛ `check` و`check --deploy` (تحذير W021 الوحيد مقصود). Docker: الخدمات الست تعمل (backend/worker healthy) والاستيراد نفذ عبر الـ Worker الفعلي.

## Security review

IDOR/العزل (404) ✓ PII (masked في كل مكان، staging مشفر، لا plaintext في logs/audit/اختبارات) ✓ mass assignment (school/uploaded_by من الخادم) ✓ Excel خبيث/قنابل/صيغ ✓ ملفات مؤقتة (خاصة، تحذف بعد الاعتماد/الإلغاء، لا تنزيل) ✓ stale/double-commit (قيود+اختبارات) ✓ Celery tenant context (من الـ Job) ✓.

## OpenAPI debt status

لم ينفذ في هذه المرحلة (قرار تركيز). **موعد نهائي ملزم موثق في ARCHITECTURE.md: بداية المرحلة 5 أو 6 على الأكثر — قبل APIs الحضور.**

## Known limitations

- تنزيل ملف الأخطاء (CSV) مؤجل بقرار (البند 72 يسمح) — الأخطاء معروضة كاملة في الواجهة.
- guardian بيانات مدمجة في Student (لا Guardian entity — قرار MVP موثق).
- رفع حد rate limit للدخول في compose التطوير فقط (`LOGIN_RATE_LIMIT_IP_MAX=500`) بعدما أوقفت الحدود الصارمة E2E المتكرر — الإنتاج على الافتراضي الصارم.
- الاسم يخزن منظفًا تنظيفًا غير مدمر (NFKC + مسافات) — لا حقل `full_name_original` (التنظيف لا يغير الحروف).

## Technical debt

- OpenAPI (موعده أعلاه).
- إعادة النظر في صلاحية استيراد الوكيل (مقيدة للمدير في MVP بقرار موثق في PERMISSIONS.md).

## Risks

| الخطر | التخفيف |
|---|---|
| ملفات نور بصيغ صفوف غير معروفة | fallback آمن (code من النص، sequence=0) + المعاينة تعرضه قبل الاعتماد |
| تضخم بيانات E2E التراكمية في dev DB | fixtures فريدة لكل تشغيل + تأكيدات غير حساسة للتراكم |

## Files changed

Backend: students app كامل (models/migration/services 8 ملفات/tasks/api/urls/admin/benchmark command)، common/security/identifiers + pagination، audit (12 حدثًا)، settings (مفاتيح تشفير + حدود استيراد + rate limit env)، seed (أعوام نشطة)، 5 ملفات اختبار جديدة + xlsx_helper. Frontend: features/students (api/StudentsPage/ImportWizard/tests)، AppShell/routes، e2e (spec + global-setup + fixtures generator). Docs: 3 جديدة + 4 محدثة + .env.example.

## Commits

Commit واحد: `feat: add student records and Noor import workflow`. لا push.

## Ready for Phase 5?

**نعم.** الطلاب والقيود والاستيراد الآمن جاهزة. المرحلة 5 (Staff Import) ستعيد استخدام: pipeline الاستيراد (بنمط أبسط — اسم+جوال)، إعادة استخدام User العالمي (جاهزة من المرحلة 2)، وإنشاء Memberships — مع معالجة دين OpenAPI في بدايتها حسب الموعد الملزم.
