# التفعيل بالبريد وتوثيق وسيلة الاسترداد — تحقق الإصدار

التاريخ: 2026-10-08. أساس التوسعة `356331c5601270fdc97cefe03d78ed243fcd110e`.
فرع العمل: `codex/parent-email-activation-20261008`. نسخة الكود المثبتة المختبرة:
`279541deed4d554e07c17a7145c6dc1ef1fcb524`.
هذا تغيير للرحلة أقره صاحب المشروع بعد سياسة تفعيل SMS السابقة؛ لا يعيد تفسير
نتائج التقارير التاريخية بوصفها اختبارات لهذا التغيير.

البيئة: Linux/Python3.13.16/Django5.2.18/pytest9.1.1/PostgreSQL18.6/Redis8.0.6،
وWeasyPrint70 فعلي. Frontend على Windows/Node26.7/Vitest4.1.11/Playwright1.62.1.
الأدلة المحلية متجاهلة في `tmp/email-activation/` بالنسختين؛ سجل Backend النهائي
`terminal-full-backend.log`، وسجل قبول المتصفح `warm-playwright.log` في Checkout
النظيف. لا تستخدم الأدلة Runtime بوصفها ملفات مصدر لازمة لإعادة إصدار الكود.

## 1. السلوك المنفذ

1. يقدم ولي الأمر طلب التسجيل مع بريد صحيح، وتراجع المدرسة الهوية والصفة والطالب.
2. موافقة المدرسة وإعادة إصدار التفعيل تستخدمان EMAIL افتراضياً. تستقبل المدرسة
   حالة التسليم فقط، دون الرابط السري. يرسل العامل رسالة واحدة تحمل اسم المدرسة
   في اسم المرسل وعنوان الرسالة والمحتوى، من عنوان Resend الموثق المضبوط في
   `RESEND_FROM_EMAIL`؛ لا يُستخدم نطاق المدرسة بوصفه عنوان مرسل غير موثق.
3. الرابط يفتح صفحة التفعيل ويمسح Fragment من History. فتحه أو فحصه لا ينشئ حساباً
   ولا يوثق البريد ولا يستهلك الرمز. التأكيد الصريح بكلمة مرور جديدة للحساب الجديد
   يجمع إنشاء الحساب وربط الطالب واستهلاك الرابط وتوثيق البريد في معاملة واحدة.
4. بعد نجاح المعاملة تصبح بيانات الأبناء المعتمدين متاحة. لا تُرسل رسالة توثيق
   ثانية للحساب الجديد في هذه الرحلة. البريد المعتمد يصلح للاسترداد الشخصي المؤهل
   بكلمة مرور جديدة، مع نفس رقم الدخول ومعرف الحساب والعلاقات.

الحساب الموجود يجب أن يسجل الدخول بنفسه. توثيق بريده الأول يتطلب إعادة إثبات
كلمة المرور الحالية؛ ربط ابن لا يغير كلمة المرور أو البريد الموثق سابقاً أو
العضويات الوظيفية. إذا كان له بريد موثق، يبقى هو وسيلة الاسترداد؛ البريد الذي
وضعه مقدم طلب المدرسة لا يستبدله. التعارض مع بريد موثق لحساب آخر يفشل برد عام
ويلغي المعاملة كاملة، دون إنشاء حساب أو منح علاقة جزئياً.

مسارا SMS/MANUAL السابقان باقيان كخياري توافق صريحين؛ لا يحققان توثيق البريد
بأنفسهما، وتظل قراءة الأبناء فيهما محجوبة إلى اكتمال إثبات البريد المنفصل.
السلوك الافتراضي الجديد لا يرسل SMS للتفعيل. رسائل الغياب لم تتغير.

## 2. البيانات والأمان

تضيف `parents0009` إلى `GuardianActivation` القناة، وبصمة بريد التسجيل، ومعرف
محاولة UUID، والحساب الذي استهلك الرابط. لا جداول مستخدمين موازية ولا تغيير في
`User.email` أو `User.mobile`، ولا تحويل تلقائي لبريد تاريخي إلى اعتماد.

الرمز عشوائي256bit، مخزن كبصمة فقط. وسيطات Celery معرفا المدرسة والتفعيل فقط.
العامل يثبت مطالبة SENDING قبل الاتصال، ثم يعيد فحص الطلب والطالب والتواصل
والاشتراك تحت الأقفال قبل الإرسال المحدود بالمهلة. لا إعادة إرسال عمياء بعد
انقطاع العامل أو نتيجة غير مؤكدة. انتهاء محاولة SENDING القديمة يظهر UNKNOWN
في التاريخ؛ يعيد الموظف المخول إصدار محاولة جديدة بعد التحقق، ويبطل السابقة.

حالات المزود: قبول مرجع UUID يسجل SENT (قبول المزود فقط)، والرفض FAILED، وعدم
اليقين UNKNOWN. لا يُسمى قبول المزود وصولاً. المدة هي الأصغر من مدة التفعيل
ومدة توثيق البريد المضبوطتين؛24ساعة افتراضياً. المنتهي والمستهلك والملغى لا يعمل.
الفشل أو تغيّر نور/الموافقة يمنع الإرسال أو الاستهلاك وفق الحالة الحالية.

حارس PostgreSQL يمنع تغيير ربط البريد والقناة والمعرف والمهلة، ويمنع إعادة
استخدام الاستهلاك أو إلغاء الإبطال. توثيق البريد الجديد في فعل ACTIVATE يتطلب
بصمة رابط EMAIL المطابق والحساب الذي استهلكه وعلاقة الطالب الدقيقة. سياسات FORCE
RLS السابقة محفوظة، دون SECURITY DEFINER أو bypass عام. المدرسة لا تستطيع اعتماد
البريد أو اختيار كلمة مرور حساب موجود أو تغيير الجوال العالمي.

الهجرة إضافية، تعتمد0008 وتحفظ سجلات SMS/MANUAL السابقة. تطبيقها قبل تحديث
التطبيق والعامل والواجهة، مع إغلاق التسجيل أثناء التحديث. إذا توجد بيانات EMAIL
يرفض reverse0009؛ يرفضه أيضاً دور لا يستطيع إثبات الفراغ على مستوى القاعدة.
استخدم Forward fix أو إصداراً متوافقاً، ولا ترجع إلى Backend يفتقد حمايات الحسابات.

## 3. المشكلات المثبتة والإصلاحات

اكتشف فحص المصدر أن SELECT FOR UPDATE على التفعيل مع `select_related("school")`
يقفل المدرسة أيضاً بعد حصول العملية على KEY SHARE. أثبت اختبار اتصالين حقيقيين
بدور NOSUPERUSER/NOBYPASSRLS أن تسليمين لطفلين مستقلين لا يستطيعان الاحتفاظ
بأقفالهما معاً: BrokenBarrierError،1فاشل في78.73s قبل التصحيح. هذا احتجاز زائد
واحتمال تعارض عند ترقية قفل المدرسة، وليس دليلاً على تسريب بيانات.

حُصر FOR UPDATE في سجل التفعيل بـ`of=("self",)`، مع بقاء ترتيب المدرسة KEY SHARE
ثم الطالب ثم الطلب ثم التفعيل، ودون تخفيف أقفال الطالب أو إثبات الموافقة. نجحت
المجموعة الجديدة22/22 في89.47s بعد التصحيح؛ يحتفظ اختبار الطفلين بنفس التزامن
والأدوار الفعلية والحاجز الذي كشف الخطأ.

أثبت اختبار رجوع الهجرة باتصالين حقيقيين أن فحص الفراغ قبل إزالة الحارس يستطيع
تفويت INSERT لم يُثبت بعد: ينتظر DROP TRIGGER الكاتب ثم يكمل بعد تثبيت سجل EMAIL،
فيزيل الحارس رغم وجود البيانات. فشل الاختبار قبل الإصلاح1/1 في34.49s. أضيف
ACCESS EXCLUSIVE على جدول التفعيل قبل فحص الفراغ داخل معاملة الرجوع نفسها؛ ينتظر
الكاتب أولاً ثم يرفض الرجوع عند ظهور السجل. بقيت البيانات والحارس، ونجحت مجموعة
التفعيل والهجرات27/27 في228.90s. الكاتب يعمل بدور NOSUPERUSER/NOBYPASSRLS؛ تنفيذ
DDL الرجوع يستخدم مالك الهجرة الفعلي. لا تعديل لسياسات RLS أو إسقاط بيانات.

## 4. سجل التنفيذ

الاختبارات لا ترسل بريداً أو SMS فعلياً. Provider tests تحاكي HTTP الخاص بـResend؛
المتصفح يستخدم العامل الحقيقي وملفات بريد خاصة `.invalid` ضمن بيئة معزولة.

| التشغيل الفعلي | ناجح/فاشل/متجاوز | الزمن/النسخة |
| --- | --- | --- |
| Full Backend المرشح الأول |1444/0/0 |1331.46s؛ قبل إضافة اختباري rollback/reissue واختبار قفل الطفلين |
| اختبارات التفعيل النهائية المركزة |22/0/0 |89.47s بعد إصلاح القفل |
| Full Backend من Checkout نظيف بعد إصلاح القفل |1447/0/0 |1224.16s؛ Wall1242.26s؛495edaf |
| التفعيل والهجرات بعد إصلاح نافذة الرجوع |27/0/0 |228.90s؛ نسخة الإصلاح قبل تثبيتها في279541d |
| Full Backend النهائي بعد حماية الرجوع |1448/0/0 |468.55s؛ Wall474.55s؛279541d، مصدر نظيف |
| Full Frontend نظيف،44ملفاً |444/0/0 |448.60s؛1118803 |
| E2E أول من Checkout نظيف، Desktop/Tablet/Mobile |3/0/0 |1.6m؛1118803 |
| E2E نهائي بعد استقرار بدء الخدمة |3/0/0 |17.1s؛ Wall18.49s؛279541d، Fixture جديد |
| TypeScript/ESLint/strict E2E TS |Exit0 |1118803؛ الواجهة مطابقة في495edaf |
| Production/PWA Docker build |Exit0 |صورة مستقلة من Checkout نظيف، مصدر الواجهة نفسه |
| Ruff0.16.4 |Exit0 |279541d، backend/scripts |
| Django/Migration check النهائيان |Exit0/Exit0 |279541d |
| OpenAPI generation/validation |Exit0 |1118803؛ عقود API والهجرة مطابقة في495edaf |

الواجهة وإعداداتها وCompose لم تتغير بين1118803 و279541d؛ تصحيح495edaf غيّر
الأقفال واختبارها، وتصحيح279541d غيّر حماية الرجوع واختبارها وتوثيقها. فحص
`git diff 1118803 279541d -- frontend` فارغ؛ نتائج Frontend والبناء تنطبق على
المصدر المطابق. لا تعاد نسبة اختبار نسخة قديمة إلى مصدر مختلف.
OpenAPI يحتفظ بـ15تحذيراً(13فريداً) و520تشخيصاً من نوع Errors(97فريداً) في الواجهات
القديمة؛ Exit0 لا يعني خلو المخطط كله من المشاكل. لا تشخيص جديد صادر من التوسعة.

أضافت التوسعة23حالة Backend واختباري Frontend ورحلة جديدة بثلاثة مقاسات. المجموعة
الكاملة تتضمن اختبارات SMS الغياب لـDreams/Msegat وNoor/contact/import وRLS
SQL/HTTP وStudentLeave/Gate وPDF/private-storage/backup القديمة، دون skip.
تحذير HarfBuzz-Subset السابق لم يفشل PDF؛ لا native-engine skips في Linux.
قبول المتصفح الجديد3/3 هو تغطية هذه التوسعة؛ لا تنسب رحلات المتصفح التسع التاريخية
إلى هذا التشغيل الجديد. لا تغيير Dependencies أو حدود Query-budget أو RLS.

فشل Vitest المرشح الأول1/444 بسبب مسار غير صحيح في الاختبار الجديد؛ صحح إلى
`/parent-management` وصححت عضوية Fixture المدير، ثم نجحت444/444 في المرشح وفي
النسخة النظيفة. صححت أخطاء تنسيق Python و`exact` غير المدعوم في Testing Library
وتضييق نوع مشروع Docker في helper؛ نجحت الفحوص الصارمة دون تخفيف قواعدها.
فشل فحص Runtime الأول لأن Beat لم يصدر heartbeat بعد بدء التشغيل؛ نجح بعد
نبضته الطبيعية، دون كتابة نبضة وهمية أو تغيير Redis.

المحاولة الثانية للمتصفح على495edaf نجحت2/3 وفشلت Desktop أثناء انتظار إيصال
التسجيل5ثوانٍ. تتبع الشبكة أثبت أن تهيئة CSRF استغرقت13.6ثانية ولم يُرسل POST
التسجيل؛ كانت مجموعة Backend الثقيلة تعمل بالتزامن. ثم تكرر الفشل2/3 على279541d
بعد إعادة تشغيل Gunicorn دون تلك المجموعة، بأول طلبات CSRF نحو4–6ثوانٍ. استقرت
الطلبات التالية إلى بضعة مللي ثوانٍ؛ نجح قبول3/3 بخدمة مستمرة وFixture جديد دون
إعادة تشغيلها. لم يغير مسار CSRF أو مهلة assertion أو حدود المعدل أو Redis،
ولا أضيف retry للاختبارات. الارتباط الملحوظ ببدء الخدمة ليس إثباتاً لسبب داخلي
محدد؛ يحتاج قبول بدء العمليات الجديدة وفحص latency قبل التوسع العام. نجاح
الخدمة الدافئة لا يلغي الملاحظة ولا يضمن سعة الإنتاج.

## 5. قبول البيئة والعزل

النسخة النظيفة: `xmansx-parent-email-activation-clean-20261008`. مشروع القبول
`xmansx-parent-email-activation-synthetic-staging` علىhttps://localhost:8445 فقط،
بـDEBUG=false وUID65534 وNOSUPERUSER/NOBYPASSRLS و83 FORCE RLS tables، وRedis
noeviction وقواعد0/1/3/4، وعامل وBeat حقيقيين، وTLS وSecure cookies وCSRF،
وتخزين خاص700/600. التطبيق والعامل بلا مسار خروج خارجي وبلا مفتاح Resend.
مصدر Checkout كامل read-only؛ الأسرار وFixture والروابط والأدلة Runtime متجاهل.

فُحصت صور صفحة التفعيل بصرياً في1366×900 و768×1024 و390×844؛ يظهر اسم المدرسة
والنص الذي يوضح التوثيق الصريح، دون overflow أفقي. الرحلات الناجحة لا page errors.
يشمل المتصفح منع قراءة الأبناء قبل التأكيد ورفض إعادة الرابط والاستئذان والحارس،
ثم الاسترداد ورفض كلمة المرور القديمة ونجاح الجديدة مع نفس الحساب والعلاقة.

أوقف مؤقتاً TLS edge القديم على8445 فقط لاستعمال المنفذ بالبيئة الجديدة؛ لم
تستبدل قواعده أو Volumes أو شهادته أو مصدره. أُغلق تسجيل مدارس جميع Fixtures
وتحققglobal_enabled_schools=0 وsms_integrations=0 وsms_notices=0. نجح فحص Runtime
النهائي على279541d مع نبضة Beat حقيقية بعمر105.5ثانية. أوقفت خدمات القبول الجديدة
واحتفظ بموادها وقاعدتها، ثم أعيد تشغيل TLS edge السابق على8445 فعلياً. لا نشر خارجي.

## 6. حماية الأنظمة القائمة وحالة Git

لا فرق عن356331c في مصادر school_sms أو الحضور/الغياب أو Noor أو student_leaves
أو StudentGateRelease. لا شرط بريد أو حساب/علاقة ولي أمر لأهلية SMS الغياب؛ المصدر
يبقىStudent.guardian_mobile وDreams/Msegat وسياسة التكرار والفشل الحالية.
لا طلب استئذان إلكتروني أو سلطة خروج للأهل. ملفات selectors/access الخاصة بقراءة
الأبناء لم تتغير؛ لا cache حساس جديد أو أرقام أداء إنتاجية مخترعة.

المستودع الأصليxmansx عندd8f8de6 محفوظ ولم يستخدم للتعديل أو التثبيت.23مساراً
في Commit1118803، ثم إصلاح قفل واحتفاظ باختباره في495edaf، وحماية رجوع الهجرة
واختبارها في279541d. يضيف Commit التوثيق
النهائي هذا السجل وتحديث الإحالات فقط؛ لا أسرار أو Screenshots أو Logs في Git.
لا push أو merge أو نشر إنتاجي أو إرسال خارجي جديد.

تأكدت مراجعة النهاية من بقاء الأصل عند SHAد8f8de6 الكامل،56مساراً متغيراً وصفر
staged، وبصمة binary diff مطابقة للبداية:
`763C4D0D9D4376463D025A1A768BC8E23105D886DBA202093D5BD62A18CD36FF`.
نسخة الاختبار النظيفة خالية من تغييرات المصدر أثناء الاختبارات.

ظهرت أثناء الإنهاء ستة مسارات متزامنة تخص تصميم قوالب البريد: تعديل
`backend/parents/email_recovery_provider.py`، وملفات جديدة
`backend/common/email_templates.py` و`backend/tests/test_email_templates.py` و
`scripts/preview_transactional_emails.py` و`scripts/verify_email_previews.mjs`،
و`docs/EMAIL_TEMPLATE_DESIGN_VERIFICATION.md`.
لم تستبدل أو تثبت أو تختبر ضمن الإصدار هنا؛ مصدر النسخة النظيفة لا يحتوي عليها.
دمج تصميم القالب لاحقاً يحتاج اختبار عقود أغراض البريد والقالب والتسليم من جديد.

## 7. إعادة التنفيذ والقرار

من Checkout نظيف للكود279541d أو Commit التوثيق المتوافق:

```powershell
$vf=@('-p','xmansx-email-activation-verification','-f','docker-compose.parent-verification.yml','-f','docker-compose.parent-release-verification.yml','-f','docker-compose.parent-email-verification.yml')
docker compose @vf up -d postgres redis
docker compose @vf build tests
docker compose @vf run --rm --no-deps tests pytest --create-db --reuse-db -q -rs
docker compose @vf run --rm --no-deps tests python manage.py check
docker compose @vf run --rm --no-deps tests python manage.py makemigrations --check --dry-run
ruff check backend scripts
Push-Location frontend
npm ci
npm run test -- --maxWorkers=2
npm run typecheck
npm run lint
npm run build
Pop-Location
```

للقبول HTTPS اتبع [دليل Staging](PARENT_PORTAL_STAGING_READINESS.md) مع مشروع
`xmansx-parent-email-activation-synthetic-staging`، Overlay البريد المتتبع بعد
Overlay Staging، ومجلد مواد جديد مستقل لمشروع جديد. اختر Fixture جديداً لكل
مجموعة رحلة؛ لا تعيد استعمال حسابات الرحلة المستهلكة ولا تمسح Redis لتجاوز الحدود.
أمر المتصفح: `npx --no-install playwright test e2e/parent-email-activation.spec.ts --config playwright.parent.config.ts`.
أصل الاختبارhttps://localhost:8445، وNODE_EXTRA_CA_CERTS للشهادة الصناعية نفسها،
وأعلامPARENT_E2E_EXTERNAL_PREVIEW وPARENT_E2E_SYNTHETIC_STAGING
وPARENT_VERIFICATION_LOCAL_ONLY=1، وPARENT_E2E_FIXTURE للملف الجديد.
أغلق مدارس Fixture بعدها بأداةparent_staging_fixture_check المتتبعة.

**الحكم النهائي: PASS WITH ISSUES.**

| القرار | النتيجة | الدليل أو العائق |
| --- | --- | --- |
| Local technical readiness | PASS |1448 Backend و444 Frontend و3 E2E، وفحوص المصدر والهجرات والبناء من الكود المثبت |
| Restricted synthetic Staging | PASS WITH ISSUES | رحلة HTTPS الصناعية ناجحة؛ تأخر أول CSRF بعد بدء عمليات جديدة موثق ويحتاج قبول بدء التشغيل |
| Public production readiness | FAIL — لا تفتح التسجيل حالياً | قبول وصول قالب التفعيل الجديد عبر Resend الحقيقي ومعالجة Spam وخطة enrollment/support ومراجعة بدء التشغيل لم تغلق |

قبول قالب التفعيل الجديد عبر Resend الحقيقي لم ينفذ. التصريح السابق كان لرسالتين محددتين فقط؛ لا يجيز
إرسال رسالة إضافية هنا. اختبار الوصول التاريخي انتهى إلىGmail Spam وليس Inbox؛
يلزم قبول مصرح به لقالب التفعيل الجديد ومعالجة قابلية الوصول قبل فتح الرحلة
للعامة. حسب سجل [تجهيز Resend السابق](RESEND_PARENT_RECOVERY_SETUP.md)، جُهز بالفعل
نطاق `mail.mowadhabah.com` ومفتاح Sending access مقيد به؛ لا حاجة لاستخدام نطاق
`xmansx.com`. ضبط أسرار التطبيق والعامل عند التشغيل الخارجي، وقبول وصول القالب
الجديد وخطة enrollment/support، تظل متطلبات تشغيلية. هذا التشغيل الصناعي لا
يستخدم المفتاح الحقيقي ولا يثبت نشر Staging خارجي أو جاهزية إطلاق عام.

Commit التقرير النهائي توثيقي فقط؛ يستخرج SHA بواسطة
`git log -1 --format=%H -- docs/PARENT_EMAIL_ACTIVATION_VERIFICATION.md`.
المقارنة مع279541d لمسارات Backend/Frontend/scripts/Compose خالية من اختلاف
المصدر المثبت. لم تدخل تغييرات تصميم القوالب المتزامنة في هذا Commit أو نتائجه.

## 8. جرد التوسعة

الفرق المثبت عن356331c هو26مساراً:7جديدة و19معدلة؛ لا Dependencies أو Lockfiles
أو أسرار أو ملفات الأدلة الصناعية، ولا المسارات الستة المتزامنة المذكورة أعلاه.

```text
M backend/config/settings/base.py
A backend/parents/activation_email.py
M backend/parents/api.py
M backend/parents/email_recovery_provider.py
A backend/parents/migrations/0009_email_activation.py
M backend/parents/models.py
M backend/parents/serializers.py
M backend/parents/services.py
A backend/tests/test_parent_email_activation.py
A backend/tests/test_parent_email_activation_rollback_race.py
A docker-compose.parent-email-verification.yml
M docs/PARENT_ACCOUNT_RECOVERY_OPERATIONS.md
A docs/PARENT_EMAIL_ACTIVATION_VERIFICATION.md
M docs/PARENT_EMAIL_RECOVERY_ARCHITECTURE.md
M docs/PARENT_EMAIL_RECOVERY_VERIFICATION.md
M docs/PARENT_PORTAL_STAGING_READINESS.md
M docs/RESEND_PARENT_RECOVERY_SETUP.md
A frontend/e2e/parent-email-activation.spec.ts
M frontend/e2e/parent-email-mailbox.ts
M frontend/playwright.parent.config.ts
M frontend/src/features/parent/ActivationDelivery.tsx
M frontend/src/features/parent/ActivationPage.tsx
M frontend/src/features/parent/ParentManagementPage.tsx
M frontend/src/features/parent/RegistrationPage.tsx
M frontend/src/features/parent/api.ts
M frontend/src/features/parent/parent.test.tsx
```
