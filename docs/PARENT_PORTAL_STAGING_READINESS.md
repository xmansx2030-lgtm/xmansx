# بوابة ولي الأمر — جاهزية Staging صناعي مقيد

تاريخ العمل: 2026-10-08. أساس المصدر: `d8f8de6d4365e518cff269d438c25715c31a4a7e`.
هذه الوثيقة تصف بيئة محلية مستقلة قابلة لإعادة الاختبار. لا تثبت وجود Staging
خارجي، ولا تسمح بإطلاق عام أو إرسال SMS. نتائج التشغيل النهائية في
[تقرير جاهزية الإصدار](PARENT_PORTAL_RELEASE_READINESS_REPORT.md).

## 1. حدود البيئة وقرارات التشغيل

- لا توجد في الأدلة المتاحة بيئة Staging خارجية مستقلة مصرح باستخدامها.
- لا DNS أو موارد مدفوعة أو مفاتيح إنتاج أو نسخ قواعد مدارس حقيقية.
- مشروع الاختبارات HTTP: `xmansx-parent-release-verification`، PostgreSQL5545،
  Redis6400، API8012، وواجهة الاختبار5175؛ جميع المنافذ مربوطة بـ127.0.0.1.
- مشروع القبول HTTPS مستقل: `xmansx-parent-synthetic-staging`، الأصل الوحيد
  `https://localhost:8445`. له PostgreSQL وRedis وتخزين خاص منفصل كلياً عن HTTP.
  لا يُنشر منفذ قاعدة البيانات أو Redis أو Gunicorn في مشروع HTTPS.
- قاعدة البيئة الصناعية تحمل اسم `parent_verification` في كل مشروع مستقل؛
  تشابه الاسم لا يعني اشتراك Volume أو Docker network. يعاد استخدام الاسم
  المقيد حتى تظل حواجز الأوامر الصناعية دقيقة.
- التسجيل المدرسي معطل افتراضياً. `--enable-registration` يفتح المدارس الثلاث
  الجديدة التابعة لتشغيل Fixture المحدد فقط؛ لا يغير مدرسة موجودة.
- استعادة الحساب النهائية وتغيير رقم الدخول لا تُفعّل بإعداد Staging؛ يلزم
  اعتماد سياسة إثبات الهوية المستقلة المشار إليها في وثائق الاستعادة.
  أكد صاحب المشروع عدم وجود سياسة استعادة معتمدة حالياً. لذلك يظل التنفيذ
  النهائي مغلقاً، والإطلاق العام محجوباً، حتى استيفاء الاعتماد والأدلة والأدوار.

## 2. الملفات المتتبعة اللازمة

| الملف | الغرض |
| --- | --- |
| `docker-compose.parent-verification.yml` | الأساس المحلي الموثق السابق، مع Mount كامل Checkout للملفات الجذرية |
| `docker-compose.parent-release-verification.yml` | مشروع/Volumes/منافذ HTTP جديدة تحفظ البيئة السابقة |
| `docker-compose.parent-staging.yml` | مشروع HTTPS منفصل، Gunicorn/Worker/Beat/Frontend، شبكة داخلية بلا خروج |
| `backend/config/settings/parent_staging.py` | إعدادات إنتاج فعلية مع حواجز loopback والبيئة الصناعية |
| `scripts/parent_staging_materials.py` | توليد مفاتيح مستقلة وشهادة localhost في ملفات متجاهلة؛ يرفض استبدال المفاتيح |
| `scripts/parent_staging_storage.py` | ضبط ملكية Volume الصناعي فقط للمستخدم65534 دون روابط رمزية |
| `scripts/parent_staging_acceptance.py` | فحص Runtime حقيقي بدور التطبيق المقيد: Redis/RLS/Worker/Beat/المسار والتخزين |
| `scripts/parent_staging_fixture_check.py` | تحقق Owner من المدارس الصناعية الجديدة وتعطيل التسجيل وغياب إعدادات/رسائل SMS |
| `scripts/parent_staging_restore_drill.py` | نسخ/استعادة صناعية إلى قاعدة فارغة جديدة ومجلد خاص مستقل دون استبدال المصدر |
| `scripts/parent_staging_schema_refresh.py` | أداة QA محلية فقط، ترفض الرجوع لأي Migration غير0006 أو عند وجود أي سجل استعادة |
| `infra/parent-staging-nginx.conf` | TLS محلي وProxy يثبت Forwarded-Proto، ومنع Cache لواجهات API |
| `seed_parent_staging` | Fixture إضافي يستخدم خدمات الموافقة/التفعيل/الأعذار/التصحيح القائمة |

المواد المحلية في `artifacts/parent-staging/` متجاهلة بالكامل، بما فيها `.env`
والشهادة والمفتاح وبيانات Fixture. قيم الأسرار لا تُطبع ولا تُثبت في Git.
احتفظ بالمفاتيح مع نسخة البيانات الصناعية؛ إعادة توليدها ليست خطوة تحديث.

## 3. الإعدادات الأمنية

`parent_staging` يستورد إعدادات الإنتاج الحالية: DEBUG=False، RLS مفعّل،
Secure/HttpOnly session cookie، SameSite=Lax، Secure CSRF، HTTPS redirect،
AllowedHosts=localhost، وCSRF Trusted Origins=الأصل8445 فقط. Django Admin معطل.
HSTS المحلي صفر حتى لا تُترك سياسة دائمة لشهادة اختبار ذاتية التوقيع؛ TLS
والكوكيز الآمنة باقية. لا تستخدم هذا الاستثناء في بيئة منشورة.

دور HTTP/Gunicorn/Worker هو `parent_verify_app`: LOGIN NOSUPERUSER NOBYPASSRLS
NOINHERIT. دور DDL `parent_verify_owner` داخل حاوية اختبارات/تهيئة فقط. لا تضع
بياناته في خدمة التطبيق. فعل السياسات وTriggers وراجع Catalog من نفس SHA؛
نجاح `/health` وحده لا يثبت جميع الحواجز.
Gunicorn/Worker/Beat يعملون بمستخدم65534 دون قدرات Linux أو اكتساب صلاحيات،
وبنظام ملفات حاوية read-only؛ tmpfs مؤقت وVolumes خاصة محددة هي مواقع الكتابة.

TLS يستخدم مفاتيح Fernet/HMAC/Django عشوائية مستقلة، ليست قيم الاختبار العامة
في مشروع HTTP. يرفض Production settings مفتاح Fernet التطويري. ملفات Compose
تستخدم `--env-file artifacts/parent-staging/.env` لتعيين مفاتيح حاوية البذر أيضاً؛
لا تخلط Fixture مشفر بمفاتيح HTTP مع قاعدة TLS.

Redis noeviction؛ Cache0، security1، broker3، results4، واختبارات pytest2.
الـsecurity cache يستخدم RedisCache ويُفشل الطلب بأمان عند التعذر. Worker حقيقي
concurrency1، queues celery/imports/maintenance، وBeat فعلي؛ لا eager في التطبيق.
وزارة التقويم ونسخ الاحتياط الدورية والخدمات الخارجية وSentry/R2 معطلة في البيئة
الصناعية. لا يُرسل SMS لاستعادة الحساب.

خدمات TLS التطبيق/Worker/Beat على Docker network داخلي دون مسار إنترنت. هذا
حاجز إضافي لمنع إرسال خارجي حتى لو أدخل شخص إعداد مزود في المدرسة الصناعية.
Nginx وحده يرتبط أيضاً بجسر ingress حتى ينشر Docker منفذ loopback8445؛ لا
يُضاف الجسر للتطبيق أوWorker أوBeat. تصل Nginx شهادة TLS ومفتاحها فقط، ولا
تصل ملفات مفاتيح الحسابات أوFixture. لا Proxy عام في إعداد Nginx.
لا توجد بيانات مزود SMS في Fixture. الصور تسحب/تبنى من المضيف قبل التشغيل؛
هذه الشبكة لا تمنع حركة المضيف أو متصفحه، ولا تدعي عزل حاسوب المستخدم كله.

## 4. إنشاء البيئة محلياً

نفذ من Checkout نظيف للـSHA المسجل في تقرير الإصدار. لا تستخدم الشجرة التي
تحوي تعديلات المستخدم المتزامنة. تتطلب الأوامر Docker Compose يدعم !override
و!reset، وDocker Desktop Linux containers.

```powershell
$verificationFiles = @('-f', 'docker-compose.parent-verification.yml', '-f', 'docker-compose.parent-release-verification.yml')
docker compose @verificationFiles config --quiet
docker compose @verificationFiles up -d postgres redis
docker compose @verificationFiles build tests
docker compose @verificationFiles run --rm --no-deps tests python /workspace/scripts/parent_portal_verification_init.py
New-Item -ItemType Directory -Force artifacts/parent-staging | Out-Null
$materialRoot = (Resolve-Path artifacts/parent-staging).Path
docker compose @verificationFiles run --rm --no-deps --volume "${materialRoot}:/materials" tests python /workspace/scripts/parent_staging_materials.py --output /materials
$stagingFiles = @('--env-file', 'artifacts/parent-staging/.env', '-f', 'docker-compose.parent-verification.yml', '-f', 'docker-compose.parent-release-verification.yml', '-f', 'docker-compose.parent-staging.yml')
docker compose @stagingFiles config --quiet
docker compose @stagingFiles up -d postgres redis
docker compose @stagingFiles run --rm --no-deps tests python /workspace/scripts/parent_portal_verification_init.py
docker compose @stagingFiles run --rm --no-deps --volume "${materialRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python manage.py seed_parent_staging --password Parent-Staging-Local-2026! --output /fixtures/fixture.json
docker compose @stagingFiles run --rm --no-deps --volume "${materialRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python /workspace/scripts/parent_staging_fixture_check.py --fixture /fixtures/fixture.json --expected-registration disabled
docker compose @stagingFiles build staging-frontend
docker compose @stagingFiles up -d staging-app staging-worker staging-beat staging-frontend
# Wait for the real Beat schedule to produce its heartbeat; do not write a fake one.
docker compose @stagingFiles exec -T staging-app python /workspace/scripts/parent_staging_acceptance.py
curl.exe --insecure --fail https://localhost:8445/api/v1/readiness/
```

كلمة المرور المذكورة قيمة صناعية عامة فقط. أمر البذر الأخير يبقي التسجيل معطلاً.
لرحلة قبول التسجيل استخدم **تشغيلاً جديداً** إلى ملف Fixture جديد وأضف صراحة
`--enable-registration`. لا تُعدل بيانات مدرسة خارج slugs الخاصة بالتشغيل.

```powershell
docker compose @stagingFiles run --rm --no-deps --volume "${materialRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python manage.py seed_parent_staging --password Parent-Staging-Local-2026! --output /fixtures/fixture-acceptance.json --enable-registration
docker compose @stagingFiles run --rm --no-deps --volume "${materialRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python /workspace/scripts/parent_staging_fixture_check.py --fixture /fixtures/fixture-acceptance.json --expected-registration enabled
docker compose @stagingFiles run --rm --no-deps staging-storage-init
```

بعد رحلة القبول أغلق التسجيل في المدارس الثلاث نفسها وأعد التحقق:

```powershell
docker compose @stagingFiles run --rm --no-deps --volume "${materialRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python /workspace/scripts/parent_staging_fixture_check.py --fixture /fixtures/fixture-acceptance.json --expected-registration disabled --close-registration
```

التهيئة تحقق اسم البيئة/القاعدة/المستخدم/المضيف، وتُطبق Migrations قبل منح دور
التطبيق صلاحيات الجدول/Sequence. لا يكتمل إطلاق التطبيق قبل storage-init.

لا تشغل اختبارات الأداء أو pytest الثقيلة أثناء قياس زمن المتصفح. صورة Backend
تُعاد من Checkout المراد اختباره. الكود Mount read-only؛ ملفات الجذر مثل
`render.scalable.yaml` موجودة داخل `/workspace` دون ملف محلي غير متتبع.

## 5. بيانات Fixture الصناعية

لكل تشغيل جديد ثلاث مدارس، مدير في كل مدرسة، ووكيل/معلم/مرشد مستقلون لكل
مدرسة. المدير في Fixture الأساسي يحمل أيضاً دور المعلم لرحلة التحضير السابقة.
يوجد ولي أمر جديد، ومعلم له حساب عالمي سابق، وولي حالات قبول له ثلاثة أبناء
في المدارس الثلاث، ومعلم صناعي مستقل آخر له ابنه الخاص لا يتأثر بعلاقة المعلم
التي يعلقها سيناريو PWA. المعرفات مثل `S<run><index>` و`W<run>` صناعية وغير صالحة كهوية وطنية.
الأرقام صيغ تجريبية توافق Validator الحالي؛ لا تُستخدم مع مزود SMS ولا نفترض
أن نطاقها محجوز لدى شركة اتصالات. لا تدخل أي رقم أو هوية شخص فعلي.

| الحالة الصناعية | موضعها |
| --- | --- |
| Draft + ABSENT واعتماد مباشر في المتصفح | طالب مدرسةA الأساسي |
| ABSENT معتمد/Full حسب سياسة التحاضير القائمة | مدرسةB الأساسية |
| حاضر بعد تصحيح إداري محفوظ | ابن قبولA، الحصة2 |
| غائب مع عذر معتمد، والحقيقة ABSENT باقية | ابن قبولA، الحصة1 |
| عذر مرفوض | ابن قبولA، طلب الحصة2 قبل التصحيح |
| تصحيح معتمد وتعديل AttendanceChange | ابن قبولA |
| تصحيح Pending وDraft | ابن قبولB |
| لم تبدأ الحصة | ابن قبولC في `not_started_date` المستقبلي، بسياق جدول أصلي عبر الخدمة القائمة ودون جلسة تحضير |
| LATE counted7 / ON_TIME counted0 | ابنا قبولA/B |
| لا بصمة ولا استنتاج غياب | ابن قبولC |
| إنذار وPDF خاص منشور | ابن قبولA |
| ملاحظة مرشد داخلية مع sentinel + نص أسري منفصل | ملف إرشاد ابن قبولA |
| رابط تفعيل منتهٍ | طالب أساسي إضافي فيC |

الـPDF الصناعي الصغير لا يثبت محرك WeasyPrint؛ الاختبارات الكاملة تنفذ المحرك
الفعلي مستقلاً. إنشاء Fixture ليس إثبات نجاح واجهة المستخدم؛ نتيجة Playwright
وHTTP/RLS موثقة منفصلة في التقرير.

## 6. قبول المتصفح والإعدادات الفعلية

تحقق من الدور من التطبيق بـ`SELECT current_user, rolsuper, rolbypassrls`، ومن
DEBUG/RLS/كوكيز/Origins، وعدم وجود SMS integration. تحقق من TLS والـno-store
والتحميل الخاص، ثم نفذ Playwright من Fixture جديد خاص بالتشغيل.

```powershell
$env:E2E_BASE_URL = 'https://localhost:8445'
$env:PARENT_E2E_PREVIEW = '1'
$env:PARENT_E2E_EXTERNAL_PREVIEW = '1'
$env:PARENT_E2E_SYNTHETIC_STAGING = '1'
$env:PARENT_VERIFICATION_LOCAL_ONLY = '1'
$env:PARENT_E2E_FIXTURE = (Resolve-Path artifacts/parent-staging/fixture-acceptance.json).Path
$env:NODE_EXTRA_CA_CERTS = (Resolve-Path artifacts/parent-staging/localhost.crt).Path
$env:E2E_SEED_PASSWORD = 'Parent-Staging-Local-2026!'
Set-Location frontend
npm ci
npx playwright test --config playwright.parent.config.ts
```

قبول الشهادة الذاتية محدود إلى localhost8445 في Test harness، ولا يغير إعدادات
منتج المتصفح. لتثبيت Service Worker يقبل Chromium فقط SHA256 SPKI للشهادة
الصناعية المولدة ذات SAN localhost؛ لا `--ignore-certificate-errors` عام ولا
إضافة شهادة إلى مخزن الثقة في النظام. طلبات Node/Playwright API تضيف فقط
الشهادة المولدة عبر `NODE_EXTRA_CA_CERTS` إلى الثقة الافتراضية لهذه العملية؛ Browser وAPI كلاهما
يستخدمان `ignoreHTTPSErrors=false`. يرفض Test harness مسار شهادة canonical آخر.
يعين المتغير في عملية الاختبار قبل تشغيل Node، دون setx أو تعديل trust/env للمستخدم.
لا تغيّر
مهلة API الأصلية ولا تعتمد على Mock للمصادقة. سيناريو
انتهاء الجلسة يحذف جلسة صناعية فعلية عبر أمر محمي قبل POST، ويطلب count>0.
للمشروع HTTP استخدم الأصل5175 و`PARENT_E2E_RELEASE_VERIFICATION=1` مع Preview
وبذر يحمل `--enable-registration`؛ لا تخلط أعلام TLS في ذلك التشغيل.

الرحلات تشمل التسجيل/QR/موافقة/رفض/تفعيل حساب قائم وجديد، ثلاث مدارس، حالات
الحضور/الدقائق الصباحية، عذر/تصحيح، IDOR، تعليق علاقة، ملف مسحوب، انتهاء جلسة،
وتبديل حسابين على الجهاز مع عدم وجود بيانات APIs/ملفات خاصة في CacheStorage.
وظائف الحارس والاستئذان الإداري تثبت باختبارات الانحدار؛ لا يوجد طلب خروج للأهل.

## 7. Migrations والنسخ الاحتياطي والتخزين

اعرض Migrations parents/students، ثم `check` و`makemigrations --check --dry-run`.
اعتماد جديدة من نفس SHA قبل تشغيل Worker/التطبيق. لا تنفذ rollback إلى Backend
قديم يزيل منع Password reset العالمي. استخدم Forward fix أو rollback واجهة
متوافق يحتفظ بحواجز الحسابات وRLS وTriggers وجداول العلاقات.

قبل ترقية قاعدة موجودة إلى parents0006، يفحص مسؤول DDL حالات الطلبات القديمة:

```sql
SELECT status, COUNT(*)
FROM parents_globalmobilechangerequest
GROUP BY status
ORDER BY status;
```

يجب أن تكون جميع الحالات `PENDING` قبل قيد intake-only الجديد؛ وجود أي حالة
أخرى يوقف الترقية للمراجعة وخطة Forward fix تحفظ التاريخ. لا تحول السجلات
صامتاً إلى PENDING ولا تحذفها لإمرار القيد. القاعدة الجديدة الفارغة تنشئ الجدول
من Migrations، أما قاعدة موجودة فتحتاج هذا الفحص المسبق ونسخة محمية.

التخزين الخاص خارج MEDIA، بلا public URL، بصلاحيات700 للمجلدات و600 للملفات،
ويمتلكه مستخدم التطبيق65534. nginx يخدم dist فقط؛ لا Alias أو Mount للملفات الخاصة.
صنّف نسخة البيانات والمفاتيح الصناعية والشهادة مستقلة عن الإنتاج.

للاختبار اللاحق استخدم أوامر النسخ الموجودة في [BACKUP_RESTORE](BACKUP_RESTORE.md):
`create_database_backup` و`verify_storage_integrity` و`backup_private_objects`.
استعد إلى قاعدة جديدة فارغة داخل المشروع الصناعي وأسماء ملفات مستقلة، ثم
`verify_restored_data` وتحقق Checksums والروابط والتنزيل المصرح/المرفوض. لا تستعد
فوق قاعدة Staging المصدر ولا تمس مدرسة أخرى. اختبارات الانحدار الآلية لا تغني
عن DR drill خارجي لمزود التخزين عند اعتماده لاحقاً.

النسخ والاستعادة عملية صيانة بصلاحية Owner مستقلة؛ لا تستخدم دور تطبيق HTTP
لـpg_dump عبر مدارس متعددة ولا تمنحه BYPASSRLS. الأمر الصناعي المتتبع يستدعي
خدمات النسخ/الاستعادة الموجودة ويخلق قاعدة فارغة ذات بادئة `parent_staging_restore_`،
ويطابق محتوى الجداول والسياسات وChecksums الملفات في مجلد جديد. لا يحذف قاعدة
أو ملف المصدر. استثنى مقارنة محتوى سجل مهمة النسخ نفسه، لأن dump يلتقطه RUNNING
قبل اكتماله، بينما يُقارن عدد سجلاته. قيم الحسابات وdigests لا تُطبع.

```powershell
docker compose @stagingFiles run --rm --no-deps --user 65534:65534 -e PARENT_STAGING_LOCAL_ONLY=1 -e DJANGO_SETTINGS_MODULE=config.settings.local -e DATABASE_BACKUP_ROOT=/tmp/parent-verification/backups -e BACKUP_ENVIRONMENT=synthetic-staging tests python /workspace/scripts/parent_staging_restore_drill.py
```

`parent_staging_schema_refresh.py` ليس مسار rollback تشغيلياً. يستعمل فقط أثناء
QA لهذه القاعدة الصناعية عندما تكون **الجداول الأربعة الجديدة فارغة تماماً**،
ويثبت أن خطة الرجوع0006→0005 لا تشمل Migration آخر قبل السماح بها. بيانات
استعادة موجودة تمنع استخدامه. استخدم Forward fix للبيئات التي تحمل أي بيانات.

## 8. الأداء والمراقبة

قِس 1/5/10 أبناء وثلاث مدارس و2000 علاقة أجنبية و500 إشعار وسنة مواظبة و20
مستخدماً متزامناً. سجّل query counts وp50/p95 والخطة الفعلية ومجال القياس؛
لا تُسمّ زمن حاوية محلية قياس إنتاج. النتائج قبل/بعد بالظروف نفسها في التقرير.
تجنب Cache دائم لبيانات الأبناء؛ الإبطال عند logout/تبديل الحساب/تعليق العلاقة
يظل إلزامياً. إن بقيت تكلفة مادية، تُسجّل ولا تُخفى بتجاوز RLS.

افحص `/api/v1/health/` وreadiness ومسار operational health الموجود، Redis
security، Worker ping وBeat heartbeat والـqueues. Nginx/Gunicorn access logs تسجل
الطريقة وحالة HTTP والمدة فقط؛ لا تحفظ URI أو query string أو cookies.
هذا ضمان لصيغة access logs المضبوطة فقط. App/Sentry scrubber الحالي يقلل
البيانات الحساسة عند توصيل Sentry لاحقاً؛ لا DSN خارجي في البيئة الصناعية.
Nginx/proxy error logs الموروثة قد تتضمن URI عند خطأ upstream، وتحتاج مراجعة
Redaction وRetention قبل أي نشر عام؛ لا تُعطّل الأخطاء ولا تفترض ضماناً شاملاً
لجميع Logs. فشل Redis الأمني أو RLS
أو التنزيل المسحوب أو غياب Worker heartbeat يمنع القبول.

## 9. SMS Smoke Plan — معلق دون إرسال

يتطلب لاحقاً تصريحاً صريحاً يحدد رقم اختبار صاحبه وافق، مدرسة صناعية ومزود
Dreams أوMsegat ونطاق **رسالة تفعيل واحدة ورسالة غياب واحدة**. تبدأ المدرسة
دون مقدم طلبات إضافية وتحت مراقبة مركزية. يسجل المزود الرسالتين ومرجعيهما،
ويؤكد المستلم وصولهما، وتتحقق سجلات المنصة وعدم التكرار. لا يكفي نجاح Mock.
قواعد FULL/أهلية الغياب ومصدر `Student.guardian_mobile` تبقى كما هي، بما فيها
ولي غير مسجل في البوابة. لا SMS للاستعادة أو لتغيير رقم الدخول.

لا تنفذ Smoke في شبكة TLS المحلية المحجوبة؛ يحتاج بيئة خارجية منفصلة مصرحاً
بها ومدرسة/رقماً محددين. عند نتيجة UNKNOWN لا إعادة عمياء؛ أوقف الدفعة وافحص
المزود قبل أي إعادة وفق السياسة الحالية. لا تفتح تسجيل عام لتجربة الرسالتين.

## 10. ما يجب حسمه قبل بيئة منشورة

اعتماد مصدر إثبات ملكية الحساب الأصلي والتحقق من الرقم الجديد دون OTP متخيل،
ومراجعين مستقلين وأدوارهم؛ نطاق HTTPS رسمي ومفاتيح خاصة مستقلة ودور RLS
مقيد؛ تخزين خاص ونسخ/استعادة مثبتان؛ Monitoring وتخطيط سعة Redis/PG/Worker؛
متصفحات/أجهزة فعلية وخطة تعطيل تسجيل المدارس؛ ثم تصريح نشر Staging واضح.
لا تفترض جاهزية عامة لمجرد نجاح هذه البيئة المحلية أو ربط origin في ملف env.

## 11. الأدلة المحلية المنفذة

هذه نتائج تنفيذ مستقلة في مشروع Docker الصناعي؛ لا تشير إلى بيئة منشورة أو
وصول SMS خارجي. السجلات وFixtures والأسرار والصور تحت مسارات متجاهلة.
بيئة التشغيل المفحوصة: Python3.13.16/Django5.2.18/PostgreSQL18.6/Redis8.0.6/
nginx1.27.5، مع Frontend Linux Node24. صورة Backend:
`sha256:52133aa572da2a9778f0d4f6eb5b77267ef15d4eeabdb0d6e6cb5eb300ca547a`؛
صورة Frontend: `sha256:c6cc169c491a30289168464fb11d5fa1105553207229882045ffdeada6108d59`.
الأوامر تشغل كود Checkout عبر mount للقراءة فقط. الـtags الأساسية وبعض نطاقات
dependencies القائمة ليست lock كامل؛ إعادة build قد تحل patch versions جديدة.
أعد الاختبارات وسجل الإصدارات/digests الجديدة، أو استخدم الصور المفحوصة ذاتها
مع المصدر المثبت لإعادة قياس البيئة نفسها. لم تتغير dependency/lockfiles ضمن هذه المهمة.

| الفحص | النتيجة الفعلية |
| --- | --- |
| بناء صورة Frontend الإنتاجية | exit0، 167.71s، Linux Node24،121 PWA entries؛ لا تغييرات dependency/lockfile |
| تهيئة TLS PostgreSQL جديدة | exit0،140.00s، جميع Migrations حتى parents0006 ثم NB app role |
| Rich fixture افتراضياً | exit0،71.22s،3 مدارس جديدة؛ Owner audit:0 مدارس تسجيل enabled،0 SMS integration/notices |
| تشغيل قبول صريح جديد | exit0،26.33s،3 مدارس صناعية إضافية؛ enabled بالضبط3 التابعة لهذا التشغيل،0 SMS integration/notices |
| فحص Runtime التطبيق | exit0،6.89s؛ UID65534،DEBUG=False،81 forced RLS tables،NB role،Secure cookies،Redis noeviction/db0/1/3/4،بلا default external route |
| Worker/Beat فعليان | Worker ping وBeat heartbeat الفعلي ناجحان؛ الفحص نفسه نجح داخل Worker؛ الثلاثة read-only/cap_drop ALL/no-new-privileges |
| HTTPS readiness الفعلية | HTTP200،status ready،database ok،redis ok من localhost8445 |
| مراجعة SQL النهائية | بعد إثبات0 صف في جداول الاستعادة الأربعة، reverse0006 فقط ثم forward؛exit0،29.65s،إعادة منح NB role ناجحة |
| DR drill صناعي | exit0،16.43s؛ restore DB منفصلة فارغة،97 عدد جدول مطابق/96 محتوى مطابق،81 forced RLS/142 policy،6 ملفات خاصة مستعادة و0 integrity errors |
| فحوص سكربتات/Seeder/Profile | Ruff وgit diff --check ناجحان؛ strict E2E TS ناجح مع Origin وSecure cookie assertions |
| أول قبول TLS بالمتصفح | 5 passed /1 failed /0 skipped،136.99s wall؛ فشل تثبيت SW بسبب شهادة الاختبار الذاتية فقط |
| تحقق شهادة PWA المحدد | Chromium جديد بالتحقق TLS العادي وSPKI الشهادة المحلية فقط ثبت SW الفعلي بحالة activated؛ لا تعطيل TLS عام |
| قبول TLS الثاني | 5 passed /1 failed /0 skipped،228.45s wall؛ PWA نجح؛ فشل توقع child نشط لمعلم علّق سيناريو PWA علاقته سابقاً |
| قبول TLS النهائي بعد عزل Fixture وإعادة تحميل المصدر | **6 passed /0 failed /0 skipped**،Playwright2.0m،123.87s wall،exit0؛ API/Browser TLS عادي مع الشهادة المحددة فقط |
| إغلاق التسجيل بعد القبول | Owner audit ناجح: globally enabled=0،SMS integrations=0،SMS notices=0،والمدارس الثلاث النهائية مغلقة |
| Runtime بعد القبول والإغلاق | NB role/UID65534/81 forced RLS/private0700-0600/no route/Redis/Worker/Beat وHTTPS readiness ناجحة |

أول فحص Runtime قبل موعد Beat الفعلي120s فشل بسبب غياب heartbeat، ثم نجح بعد
موعد الجدولة الحقيقي؛ لم تُكتب heartbeat اصطناعية. أول DR harness افترض `id`
لكل جدول، بينما جلسات Django تستخدم مفتاحاً آخر؛ صُححت مقارنة محتوى الصفوف
ترتيباً مستقراً لكل جدول وأعيدت الاستعادة كاملة. لم يُعدل منطق التطبيق لحل ذلك.
الـDR يقارن قاعدة مستعادة وملفات منفصلة، ولا يثبت استعادة مزود خارجي أو تبديل
Gunicorn إلى تلك القاعدة؛ يحتاج ذلك إجراء تشغيلياً منفصلاً مع الأدوار والمفاتيح.

أثبتت DOM وAPI في التشخيص الثاني بقاء معرف المعلم وصلاحية TEACHER ووجود علاقة
SUSPENDED_CONTACT_REVIEW مع student=null. أضيف في Fixture معلم/ابن مستقلان
لسيناريو تبديل الحساب، مع إثبات User.id/TEACHER/own-child GET200 ورفض الأبناء
الثلاثة السابقين GET404؛ لم يُفك تعليق العلاقة الأصلية أو تُضعف اختبارات PWA.

الصور النهائية `artifacts/parent-portal-desktop.png` و`-tablet.png` و`-mobile.png`
فُحصت بصرياً، مع RTL قابل للقراءة ومقاسات1366x900/768x1024/390x844 دون page
overflow. الاختبار يثبت keyboard tabs وaria-selected/tabpanel، وغياب browser
page errors، وسحب البيانات بعد التعليق وانتهاء الجلسة وتبديل الحساب. هذه أدلة
Chromium محلي، ولا تثبت كل قارئات الشاشة أو أجهزة PWA الفعلية في البيئة المنشورة.
