# تحقق مستقل — بريد استرداد ولي الأمر، الإصدار الأول

تاريخ التنفيذ: 2026-10-08. هذا سجل توسعة جديدة، وليس إعادة اعتماد لأرقام التقارير
السابقة. أساس الإصدار `010961953e63e91040428de3f5849d6ecd863f69`.
نسخة الكود المثبتة المختبرة من Checkout نظيف:
`12a1050e6677757242cfcd048fcbe2b9d740d0f7`.

**الحكم النهائي: PASS WITH ISSUES.** التحقق التقني المحلي وStaging الصناعي
المقيد ناجحان؛ فتح التسجيل العام غير معتمد حالياً قبل إغلاق متطلبات Resend
والقبول التشغيلي الخارجي المذكورة في القسم11.

## 1. نطاق التنفيذ وقرار المنتج

التسجيل الجديد يرفض البريد المفقود أو غير الصحيح في React وBackend. يبقى التسلسل
طلب تسجيل، مراجعة المدرسة، الموافقة، تفعيل SMS الحالي، ثم إثبات ملكية بريد
الاسترداد بإجراء POST صريح. لا تكشف APIs بيانات الأبناء قبل استكمال إثبات البريد.
البريد يستخدم حصرياً لتوثيق وسيلة الاسترداد وإعادة تعيين كلمة المرور؛ لا إشعارات
مدرسية أو تسويق أو SMS استرداد. تسجيل الدخول يبقى الجوال وكلمة المرور.

يرتبط البريد بمعرف `accounts.User` نفسه في نموذج منفصل؛ لا تستبدل الميزة
`User.email` أو `User.mobile`. حساب المعلم الموجود يربط بريده شخصياً بكلمة مروره
الحالية؛ لا يتحول البريد الذي قدمه شخص في تسجيل عام إلى اعتماد لحسابه. مساحة
الموظف تبقى متاحة أثناء انتظار توثيق مساحة ولي الأمر.

الاسترداد البريدي يعيد كلمة المرور فقط لحساب مؤهل يملك بريداً موثقاً. لا يعيد
تفعيل علاقات معلقة أو ملغاة، ولا ينقل الأبناء أو العضويات أو ينشئ حساباً بديلاً.
إدارة المنصة وأدوار المدرسة غير المعلم مستبعدة من الاسترداد البريدي، بما فيها
العضويات المعلقة؛ يلزم لها إثبات إضافي غير مفترض. تنفيذ الاستعادة المركزية
وتغيير رقم الدخول العالمي يظلان مغلقين، ضمن حدود الإصدار الأول المعتمدة.

## 2. حالة المستودع والحفاظ على عمل المستخدم

شجرة المستخدم الأصلية `xmansx` عند `d8f8de6d4365e518cff269d438c25715c31a4a7e`
احتوت 56 مساراً محلياً متغيراً في بداية المهمة. لم تستخدم للبناء أو التعديل أو
التثبيت. العمل في `xmansx-parent-release-20261008` على
`feature/parent-email-recovery-20261008` المشتق من إصدار010961؛ الاختبار النهائي
في `xmansx-parent-release-clean-20261008` عند SHA مثبت وMount كامل read-only.

تطابق المسارات مع عمل المستخدم في `.env.example` و
`backend/config/settings/base.py` يحتاج دمجاً يدوياً لاحقاً مع مراجعة الإعدادات
واختبارات التوافق؛ لا نسخ فوق الملفات ولا دمج تلقائي في هذه المهمة. الأرقام
التاريخية16 ملفاً لا تصف حالة بداية هذه المهمة56. تؤكد مراجعة التسليم النهائية
عدد المسارات وبصمة Diff الأصلية. لم يحدث push أو merge أو deployment إنتاجي.

الفحص النهائي الفعلي:HEAD الأصلي d8f8de6،56 مساراً،صفر staged، تطابق كامل
لقائمة porcelain وبصمة binary diff مع بداية المهمة:
`763C4D0D9D4376463D025A1A768BC8E23105D886DBA202093D5BD62A18CD36FF`.
الدليل المتجاهل `tmp/email-original-final-preservation-proof.json`؛ لا ادعاء أن
وجود تغييرات المستخدم في تلك الشجرة يمثل الإصدار المختبر هنا.

سجل Commit الكود cb1b3a2 عدد68 ملفاً:23 جديداً و45 معدلاً. أضيف تصحيح Seeder
ودليل Staging في e800394؛ مجموع الفرق عن010961 عنده69 مساراً:23 جديداً و46 معدلاً.
التصحيحان69ece90 و12a1050 احتفظا بعدد69 مساراً. Commit التوثيق النهائي يضيف
هذا التقرير بوصفه المسار السبعين:24 جديداً و46 معدلاً، ولا يغير شجرة الكود
المختبرة12a1050. يستخرج SHA تسليم التوثيق بواسطة `git log -1 --format=%H -- docs/PARENT_EMAIL_RECOVERY_VERIFICATION.md`؛ يذكر SHA الكامل أيضاً في رسالة التسليم.
لا حذف مصدر، ولا تغيير Dependencies أو Lockfiles. ملفات الروابط الصناعية،
المواد المشفرة، الأسرار، Logs وScreenshots موجودة في مسارات متجاهلة فقط.

## 3. النماذج والهجرات

- `AccountRecoveryEmail`: ارتباط عالمي واحد بالحساب، بريد أساسي موثق ومرشح
  مستقل، تشفير Fernet الموجود، HMAC لغرض مستقل، وقت إثبات وإصدارات البيانات.
  قيد فريد على HMAC البريد الموثق يمنع اعتماده لحسابين دون كشف التعارض للعامة.
- `AccountRecoveryEmailDelivery`: Outbox UUID، نوعان فقط، حالة إرسال واضحة،
  بصمة Bearer دون رمزه الخام، ارتباط بإصدار البريد وكلمة المرور والجوال، مهلة
  وإبطال واستهلاك أحادي ومرجع مزود محدود. لا عنوان أو رابط في Audit.
- حقول طلب التسجيل الثلاثة: البريد المشفر وبصمته وعرضه المقنع. الحقول الجديدة
  قابلة للإضافة على السجلات القديمة؛ لا اعتبار أي `User.email` قديم موثقاً.
- `parents0007`: الجدولان، FORCE RLS وسياسات SELECT/INSERT/UPDATE الدقيقة
  الست، Constraints وTriggers للارتباط وإثبات البريد وانتقالات الرموز.
- `parents0008`: توسيع حماية الجوال الحالية ليشمل اعتماد الاسترداد المحتفظ به
  بعد حذف آخر علاقة مدرسية؛ لا SECURITY DEFINER ولا bypass عام. يرفض Reverse
  عند وجود أي بيانات استرداد. أقفال ACCESS EXCLUSIVE تمنع إدخال بيانات بين
  فحص الفراغ واستعادة الدالة السابقة. الرجوع الصناعي الفارغ اختبار توافق فقط.

السياسة المتبعة Forward fix أو Backend متوافق يحتفظ بجداول وحراس الاعتماد،
ولا Rollback يعيد إعادة الضبط الإداري السابقة أو يسقط علاقات فعلية.

## 4. العقود الجديدة

| المسار تحت `/api/v1` | العمليات والغرض |
| --- | --- |
| `/parent/recovery-email/` | GET حالة شخصية مقنعة؛ POST تسجيل/تغيير المرشح بكلمة المرور الحالية |
| `/parent/recovery-email/resend/` | POST إعادة إرسال شخصية مقيدة |
| `/parent/recovery-email/verify/check/` | POST فحص رابط؛ لا استهلاك GET |
| `/parent/recovery-email/verify/` | POST إثبات صريح بحساب مصادق مطابق |
| `/auth/parent-password-recovery/` | POST طلب عام برقم الدخول ورد202 موحد |
| `/auth/parent-password-recovery/check/` | POST فحص Bearer محدود، دون جلسة |
| `/auth/parent-password-recovery/complete/` | POST كلمة مرور جديدة وتأكيد، ذرية، دون دخول تلقائي |

سبعة مسارات وثماني عمليات ذات DTOs مكتوبة. حمايات CSRF/Session، وRedis/IP/mobile
rate limits، وفشل آمن عند تعذر حماية المعدل. بيانات البريد غير موثقة لا تصلح
لإعادة الضبط. صالحية التوثيق24ساعة والاسترداد15دقيقة افتراضياً، ضمن حدود إعدادات
الإنتاج. كل تغيير مؤثر أو استهلاك أو انتهاء يبطل الرابط القديم.

## 5. نتائج الأمان وRLS

السياسات العالمية لا تمنح مدير مدرسة أو bypass المنصة العام سلطة على اعتماد
الاسترداد. إثبات البريد يطابق الحساب المصادق؛ Reset bearer لا يسمح بقراءة ابن أو
تغيير الجوال أو اكتساب جلسة. أقفال User ثم عضوياته وأدواره ثم البريد والمحاولة
تسلسل تغير الصلاحيات والاستهلاك المتزامن. خدمات Noor وعلاقات المدارس تحت سياساتها
وأقفالها السابقة.

الرمز عشوائي256bit، مخزن كبصمة فقط في PostgreSQL، لا وسيطات Celery أو Logs أو
Audit أو Sentry. الروابط تحمل Fragment يمسح من History إلى ذاكرة المكون، دون
TanStack/browser storage، مع no-store/no-referrer. إبطال الجلسات يعتمد رفض Django
لـsession auth hash القديم عند الطلب التالي؛ لا ادعاء حذف كل صفوف django_session.

اختبارات PostgreSQL الحقيقية تشمل NOSUPERUSER/NOBYPASSRLS، IDOR، محاولة bypass
مدرسة، حساب مختلف، التوثيق المتزامن، الاسترداد المتزامن، تغير الأدوار والبريد
وكلمة المرور، إبطال الجلسات، حفظ العلاقات المعلقة، وفشل المعاملة دون تحديث جزئي.
منع إعادة الضبط المدرسي/الإداري يمتد إلى حساب يحتفظ ببريد استرداد ولو حذفت آخر
علاقة. بقاء الاعتماد يسمح باسترداد شخصي مؤهل ولا يمنح أي صلاحية طالب.

## 6. Resend وحالات التسليم

REST ثابت HTTPS إلى Resend، مفتاح sending-only ونطاق/مرسل معتمدان عند التشغيل
الخارجي، بلا SMTP fallback أو نظام إشعارات عام. Celery يستلم UUID المحاولة فقط.
يعيد العامل فحص البيانات الحالية ثم يصنع الرمز في الذاكرة قبل إرسال قالب عربي
خالٍ من بيانات الطلاب والمدارس والجوال وكلمات المرور المؤقتة.

قبول UUID صحيح من المزود يسجل `SUBMITTED_TO_PROVIDER`، لا إثبات وصول. الرفض
و429 يسجلان FAILED، والـtimeout/network/5xx/قبول مبهم يسجل UNKNOWN. لا retry
أعمى لإعادة بناء رمز مفقود، ولا تكرار مهمة مستهلكة. إعادة الإرسال الشخصية بعد
المهلة تصنع محاولة جديدة وتبطل السابقة. SENDING قديم يتحول UNKNOWN عند مراجعته؛
لا ادعاء وجود مراقب دوري جديد لكل محاولة. يجب مراقبة Queue والعامل والحالات
العالقة ضمن التشغيل.

كل الاختبارات الآلية تستخدم Mock Resend أو private synthetic-file adapter.
الأخير محدود localhost/profile صناعي و`.invalid` دون مفتاح Resend، بدليل700
وملفات600 ومستخدم65534. ليس وسيلة إرسال إنتاجية أو صندوق رموز DB. لم يحدث إرسال
Resend أو SMS فعلي أو تسجيل حساب مزود أو تغيير نطاق إرسال.

## 7. المشكلات المثبتة والإصلاحات

| الشدة | السبب المثبت | الإصلاح والدليل |
| --- | --- | --- |
| عالية | حذف آخر علاقة في purge سمح لمدرسة أخرى بإعادة ضبط حساب يحتفظ باعتماد بريد؛ HTTP200 بكلمة موظف قبل الإصلاح | retained-credential guards في Admin/staff/platform/subscriptions وTrigger0008؛ nine boundary cases وthree real-role purge cases |
| عالية | طلب كلمة المرور الأولية القديم استأنف بعد الاسترداد الناجح، أعاد كتابة كلمة مرور الحساب وأحيا جلسة قديمة | Fresh User FOR UPDATE/session/password/initial flag checks وAudit ذري؛ اختبار NBRole فشل قبل الإصلاح ثم نجح مع اختباري UX القديمين3/3 |
| متوسطة | حذف حساب orphan ذي FK اعتمادات تسبب500 عند COMMIT الحقيقي | حفظ الهوية واعتمادها دون فك تشفير أثناء purge، مع قفل User rows مرتبة قبل إزالة العضويات |
| متوسطة | Reset عرض عام لحسابA أزال drafts/cache لجلسة المعلمB؛ إعادة إرسال متأخرة أعادت بيانات حساب سابق | session recheck وحراسة هوية الرد وcleanup اختياري يحتفظ بمسودات الموظف؛ اختبارات frontend مستقلة |
| متوسطة | تعداد زمني سريع بين حساب مفقود وصالح | limits للجميع وحد أدنى مع jitter؛ تخفيف محسوب دون ادعاء زمن ثابت تحت كل حمل |
| أداء | استخدام write-action RLS GUCs في إثبات قراءة زاد خمس polls إلى235 استعلاماً | exact owner read context وفحص fresh retained؛165 في focused بعد الإصلاح، سقف175 الأصلي لم يتغير |
| واجهة | حالة SENDING/CANCELLED غير ممثلة ورسالة قبول مزود غير دقيقة | status union وإرشادات accepted/failed/unknown منفصلة مع اختبارات |
| أدوات | أمر مسح مفاتيح PowerShell أبقى متغيرات فارغة فأهمل Compose env-file الصحيح | Remove-Item Env في عملية فرعية؛ config --quiet نجح دون تغيير مفاتيح محفوظة |
| Fixture | معرف طالب بريد جديد تصادم مع معرف طالب الموظف القديم في المدرسةA | Prefix صناعي مستقلR؛ البذر الحقيقي نجح بعدها بثلاث حالات منفصلة، دون تغيير القيد الفريد |
| واجهة | خطأ البريد المطلوب بقي بعد تصحيح الحقل وأخفى وصف الغرض | إعادة تحقق الحقل عند تعديله بعد خطأ؛ اختبار UI يثبت زوال الخطأ وعودة الوصف دون إرسال طلب |
| Fixture | طلاب البريد الجدد دخلوا الفصل الأساسي بعد حفظ roster fingerprint، فأعاد اعتماد التحضير409 | فصول بريد صناعية مستقلة؛ لا تعديل لقواعد الكشف أو اختبار التحضير القديم |
| واجهة | رابطا العودة في صفحة الاسترداد ظهرا متلاصقين في المقاسات الثلاثة | مجموعة flex قابلة للالتفاف ومسافة واضحة؛ فحص بصري للصور الصناعية دون تغيير الرحلة |
| قبول متصفح | تشغيل تسع رحلات من IP واحد تجاوز حد الدخول20/300s فأعاد429 للأربع الأخيرة | مجموعتان3 و6 مع انقضاء النافذة طبيعياً؛ الحدود وRedis وassertions محفوظة، والأوامر متتبعة في دليل Staging |

الفحوص القديمة احتاجت بيانات البريد الإلزامي وإثباتاً صريحاً للـfixtures التي
كانت تقرأ الأبناء مباشرة. لم تخفف assertions أو budgets أو RLS، ولم يضف skip.
اختبار race كان يراقب INSERT بدلاً من COMMIT ذي FK المؤجل؛ صحح قياس PID/Lock
مع الحفاظ على السيناريو الأمني. فشل Calendar render timeout منفرد تحت عدة أعمال
ثقيلة؛ نجح9/9 منفرداً، ثم442/442 بكامل Vitest مع maxWorkers2 دون تغيير الاختبار.

## 8. سجل التحقق المرشح قبل النسخة النظيفة

| التنفيذ الفعلي | ناجح/فاشل/متجاوز | زمن Runner |
| --- | --- | --- |
| أول Full backend تشخيصي | 1408/5/0 | 621.35s |
| Focused نهائي،107 جديداً مع القديم | 174/0/0 | 225.06s |
| ترقية/رفض rollback/catalog بعد أقفال Reverse | 4/0/0 | 56.12s |
| أول Full frontend | 441/1/0 | 225.59s |
| Calendar القديم منفرداً | 9/0/0 | 25.58s |
| Full frontend44ملفاً/maxWorkers2 | 442/0/0 | 330.80s |

نجحت TypeScript وESLint وstrict E2E TS وProduction/PWA build وDjango وMigration
check وRuff وdiffcheck فعلياً في المرشح. هذه الأدلة تشخيصية؛ يعتمد قرار التسليم
على جدول النسخة النظيفة وقبول HTTPS النهائيين أدناه بعد اكتمالهما.

## 9. سجل النسخة النظيفة النهائي

كل صف يحدد SHA التنفيذ؛ لم تستخدم التقارير التاريخية بديلاً عن تشغيل جديد.
Checkout منفصل بشجرة مصدر نظيفة وMount كامل read-only، وPostgreSQL18.6/Redis8.0.6
خاصين بالاختبار. Linux/Python3.13.16، Django5.2.18، pytest9.1.1، WeasyPrint70 فعلي.
الواجهة Windows/Node26.7/npm11.19/Vitest4.1.11/TypeScript6.0.3/Playwright1.62.1.

| التنفيذ النظيف | ناجح/فاشل/متجاوز | مدة التنفيذ | SHA/دليل محلي متجاهل |
| --- | --- | --- | --- |
| Full backend، قاعدة اختبار جديدة | 1425/0/0 | Runner838.61s؛ Wall848.61s | e800394، `tmp/email-clean-full-backend-v2.log` |
| Full backend النهائي | 1425/0/0 | Runner578.12s؛ Wall586.43s | 12a1050، `tmp/email-terminal-full-backend.log` |
| Full frontend44ملفاً | 442/0/0 | Runner299.03s؛ Wall302.89s | 12a1050، `tmp/email-terminal-frontend-vitest.log` |
| E2E بريد، Desktop/Tablet/Mobile | 3/0/0 | Runner1.7m؛ Wall105.40s | 12a1050، `tmp/email-terminal-playwright-email.log` |
| E2E الرحلات السابقة | 6/0/0 | Runner2.9m؛ Wall174.78s | 12a1050، `tmp/email-terminal-playwright-existing.log` |
| TypeScript / ESLint | Exit0 / Exit0 | 81.96s / 98.40s Wall | 12a1050، `tmp/email-terminal-frontend-*.log` |
| Production/PWA build | Exit0 | 131.02s Wall | 12a1050، `tmp/email-terminal-frontend-production-build.log` |
| strict E2E TypeScript | Exit0 | 7.66s Wall | 12a1050، `tmp/email-terminal-frontend-e2e-typecheck-corrected.log` |
| Django system / migrations | Exit0 / Exit0 | 29.59s / 47.68s Wall | 12a1050، `tmp/email-terminal-django.log` و`email-terminal-migrations.log` |
| Ruff0.16.3 backend/scripts | Exit0 | 20.29s Wall | 12a1050، `tmp/email-terminal-ruff.log` |
| OpenAPI generation/validation | Exit0 | 34.39s Wall | 12a1050، `tmp/email-terminal-openapi.log` |
| Performance/RLS HTTP | 7/0/0 | Runner64.10s؛ Wall72.60s | e800394، `tmp/email-clean-performance.log` |
| HTTPS backup/restore drill | Exit0 | 22.27s Wall | 12a1050، `tmp/email-terminal-restore-drill.log` |

107 اختبارات Backend جديدة موزعة46 core،46 provider،9 credential boundary،
3 purge/RLS،2 migration safety،1 initial-password race. لا PDF skips في Linux؛
HarfBuzz-Subset legacy deprecation لا يفشل الاختبارات. تحذير Node عن localStorage
التجريبي ليس اعتماداً على تخزين رموز الاسترداد. فشل أمر E2E TypeScript الأول
TS5112 لأن CLI لم يحدد `--ignoreConfig`؛ صحح الأمر إلى الفحص الصارم أدناه، دون
تعديل المصدر أو تخفيف الضوابط.

OpenAPI:7 مسارات بريد/8 عمليات/8 استجابات نجاح مكتوبة، بلا تشخيص صادر من Views
البريد. تظهر15 warnings(13 unique) و520 diagnostics مصنفة Errors(97 unique) في
الواجهات القديمة رغم Exit0/validation؛ لا يصح إعلان كامل المخطط خالياً من المشاكل.

Playwright النهائي9/9 مجموعتان حقيقيتان3+6 على Fixture واحد جديد وSHA واحد.
الفاصل بعد المجموعة الأولى334.35s؛ لا تغيير لـ20 محاولات/IP/300s أو مسح Redis.
التشغيل المجمع الأول5/4/0 كشف أخطاء البريد/roster المذكورة؛ التشغيل المجمع
الثاني5/4/0 بعد إصلاحها أوقف الأربع الأخيرة بـHTTP429 الفعلي. أعيدت جميع الرحلات
بجدولة تراعي الحماية فنجحت كلها؛ لا Assertions مخففة أو اختبارات متجاوزة.

قبول المتصفح استعمل رابط التفعيل من وضع `MANUAL` التجريبي الموجود بعد موافقة
المدرسة، مع بقاء رحلة SMS المعتمدة دون تغيير. مسار `delivery="SMS"` مغطى فعلياً
بـ`test_activation_reuses_mocked_provider_without_absence_sms` ونتائج المزود
المحاكى في مجموعة Backend الكاملة؛ لا ادعاء وصول SMS فعلي أو توصيل رابط التفعيل
إلى هاتف خارجي. البريد بالمتصفح مر عبر العامل الحقيقي والمحول الصناعي الخاص،
ولم يتصل بخدمة Resend الحقيقية.

**حماية الأنظمة القائمة:** لا يوجد فرق في مصادر `backend/school_sms/` أو
خدمات الحضور/الغياب أو Noor أو `student_leaves`/`StudentGateRelease` مقارنة
بالإصدار010961. مجموعة Backend الكاملة تتضمن `test_school_sms.py` و
`test_parent_sms_regression.py`:Dreams وMsegat بإرسال محاكى، إعدادات المدرسة،
القوالب والاختيار/المصدر `Student.guardian_mobile`، منع التكرار وFAILED/UNKNOWN
وإعادة فحص المستلم. الحالة الحرجة تستمر دون حساب أو علاقة ولي أمر؛ البريد
غير مطلوب لأهلية SMS. لم يضف مسار إرسال غياب ثانٍ أو SMS استرداد ولم ترسل رسالة
حقيقية. لا تغير للسياسة القائمة التي تفصل FULL عن اكتمال جميع تحاضير اليوم.

تتضمن المجموعة `test_student_leaves.py` وإجراءات الحارس الأصلية. قبول المتصفح
9/9 يرفض محاولات ولي الأمر لإنشاء استئذان أو تأكيد الخروج، مع استمرار الرحلة
الإدارية في Backend. لا API أو زر أو نموذج استئذان إلكتروني للأهل. اختبارات
Noor/contact/import/merge وRLS SQL/HTTP وPDF/private-storage/backup القديمة ضمن
التشغيل الكامل نفسه، دون skip أو إسقاط مجموعات؛ الجدول أعلاه هو دليل نتيجته.

تشغيل cb1b3a2 النظيف الأول أوقف عمداً عند اكتشاف تعارض Seeder؛ Exit137 بعد
353.03s وليس نتيجة PASS أو test skip. أعيد تشغيل المجموعة كاملة بقاعدة جديدة
على e800394 بعد التصحيح. لا تدخل نتيجة التشغيل المقطوع في أعداد النجاح.

الأوامر من جذر Checkout النظيف، مع PostgreSQL/Redis منفصلين عن التطبيق:

```powershell
$vf = @('-p','xmansx-parent-release-clean-verification','-f','docker-compose.parent-verification.yml','-f','docker-compose.parent-release-verification.yml')
docker compose @vf build tests
docker compose @vf run --rm --no-deps -e GENERATED_DOCUMENTS_ROOT=/tmp/parent-verification/email-clean-full-v2-private tests pytest --create-db --reuse-db -q -rs -o cache_dir=/tmp/parent-verification/email-clean-v2-pytest-cache
# الجولة النهائية من12a1050 أعادت استعمال قاعدة pytest المعزولة، دون تغيير الهجرات:
docker compose @vf run --rm --no-deps -e GENERATED_DOCUMENTS_ROOT=/tmp/parent-verification/email-terminal-full-private tests pytest --reuse-db -q -rs -o cache_dir=/tmp/parent-verification/email-terminal-pytest-cache
docker compose @vf run --rm --no-deps tests python manage.py check
docker compose @vf run --rm --no-deps tests python manage.py makemigrations --check --dry-run
$evidenceRoot = (Resolve-Path tmp).Path
docker compose @vf run --rm --no-deps --volume "${evidenceRoot}:/output" tests python manage.py spectacular --file /output/email-clean-schema.json --format openapi-json --validate
docker compose @vf run --rm --no-deps tests python -c "import subprocess,sys; subprocess.run([sys.executable,'-m','pip','install','ruff==0.16.3'],check=True); subprocess.run([sys.executable,'-m','ruff','check','--no-cache','.', '/workspace/scripts'],check=True)"
Push-Location frontend
npm ci
npm run test -- --maxWorkers=2
npm run typecheck
npm run lint
npm run build
npx --no-install tsc --ignoreConfig --noEmit --strict --noUnusedLocals --noUnusedParameters --skipLibCheck --module ESNext --moduleResolution bundler --target ES2023 --lib ES2023,DOM,DOM.Iterable --types node --verbatimModuleSyntax --allowImportingTsExtensions --moduleDetection force playwright.parent.config.ts e2e/parent-portal.spec.ts e2e/parent-email-recovery.spec.ts e2e/parent-email-mailbox.ts
Pop-Location
git diff --check
git status --porcelain=v1
```

يربط Compose كامل Checkout عند `/workspace:ro`، بما فيه ملفات الجذر مثل
render.scalable.yaml. لا ملف غير متتبع يعوض نقصاً في إعداد إصدار. المواد
الصناعية والمفاتيح وModules/Build ونتائج الأدلة وحدها Runtime متجاهل. يملك عملية
npm ci كاتب واحد، وقاعدة pytest كاتب اختبارات واحد. تقاس رحلات المتصفح والأداء
بعد انتهاء الاختبارات الثقيلة. أوامر TLS والبذر وإغلاق التسجيل وDR في دليل
Staging المتتبع.

## 10. الأداء والقبول الصناعي

القياس المستقل المعزول على e800394؛ خدمات القراءة والأمان المقاسة مطابقة في
12a1050، الذي أضاف إصلاح Fixture/واجهة فقط. لا تنسب هذه الأرقام إلى قدرة الإنتاج
أو ضمان latency؛ لم نقس CPU/RSS على خادم نشر. لا Cache دائم حساس جديد.

| الحالة | SQL الفعلي | الزمن المحلي |
| --- | --- | --- |
| خمس child polls مع2000 ولي أمر أجنبي | 165 إجمالاً؛ كان235 في المرشح قبل الإصلاح، سقف الاختبار175 محفوظ | 58.58/53.13/49.30/35.28/40.68ms |
| خمسة أبناء في ثلاث مدارس | 170 قبل وبعد2000 علاقة أجنبية | بعد الإضافة53.49/44.86/85.55/71.29/46.06ms |
| قائمة أبناء1/5/10 | 46/146/231؛ لا تغير بإضافة علاقات أجنبية | p50/p95:109.79/197.02؛359.20/443.82؛622.05/735.13ms |
| إشعارات1/5/10؛500 إشعار للحساب ذي5 أبناء | 35/89/114؛ pagination20 | عينة500 إشعار182.81ms؛ p50/p95 لقائمة5 أبناء329.44/451.10ms |
| سجل1 و366 يوماً | 30 لكلتا الحالتين | 366 يوماً p50/p95:58.69/178.92ms |
| عشرة polls متكررة | 34 لكل طلب | p50/p95:61.12/85.02ms |
|20 مستخدماً/20 workers/40 HTTP requests | 34/35؛ اختلاف سياق الجلسة الأولى موثق | Wall2721.74ms؛ p50/p95:1020.00/1234.83ms |
| ثلاثة تحميلات خاصة ثم سحب الصلاحية | 88 إجمالاً، الطلب التالي404 | 58.03/40.32/40.44ms |

خطط EXPLAIN الفعلية في `tmp/email-clean-performance.log` تشمل فهارس علاقات
الحساب والإشعارات. عينة انتظار الأقفال كل50ms رصدت صفر انتظار أثناء40 طلباً؛
لا يعني ذلك عدم وجود أي انتظار أقصر. peak Python tracemalloc لسجل366يوماً
1,173,476 bytes ليس RSS لكل العملية. إضافة فحوص البريد تجعل المقارنة مع154
استعلاماً تاريخياً لخمس أبناء غير متماثلة؛ لا ادعاء أن170 تحسين latency على154.

قبول TLS الفعلي على localhost8445 فقط، ثلاث مدارس وأرقام صناعية، لا بيانات
حقيقية ولا egress للتطبيق والعامل. Runtime النهائي UID65534/DEBUG=false،
NOSUPERUSER/NOBYPASSRLS و83 FORCE RLS tables، Redis noeviction وDBs0/1/3/4،
Worker وBeat heartbeat حقيقي، كوكيزSecure وCSRF/HTTPS، والتخزين700/600.
صور التسجيل/انتظار البريد وصفحة كلمة المرور في المقاسات1366×900 و768×1024
و390×844 فُحصت بصرياً؛ لا overflow أفقي أو browser page error في الرحلات الناجحة.
الفحص النهائي لصفحات Reset الثلاث أكد انفصال روابط العودة بعد إصلاح CSS.

تمرين DR إلى قاعدة جديدة `parent_staging_restore_a94653bb3df3` استعاد99 جدولاً،
تحقق من محتوى98 جدولاً ومن83 FORCE RLS tables و148 policy، وحمل30 ملفاً خاصاً
بصفر missing/checksum mismatch/errors. التطبيق احتفظ بدوره وقاعدة وملفات المصدر
لم تستبدل؛ لا رفع backup خارجي. تطابقت مفاتيح وتوثيق TLS الصناعية القديمة،
وكذلك الملفات الخاصة الستة السابقة حجماً وبصمة. الملفات الصناعية الجديدة تبقى
داخل التخزين الخاص. أعيد ضبط ملكية ملفات Fixture بخطوة التخزين المتتبعة بعد
البذر، قبل قبول Runtime، دون تجاوز الفحص الذي رفض الملكية الأولى.

ثبت HTTP503/SELF_REGISTRATION_UNAVAILABLE للتسجيل المدرسي العام مع CSRF/TLS
صحيحين ودون تغير أعداد المدارس والمستخدمين والجلسات. بعد القبول يغلق التسجيل
للمدارس الثلاث المخصصة أيضاً ويعاد فحص عدم وجود SMS integration أو notice.

## 11. المتطلبات التشغيلية وقرار الإصدار

لا تزال إعدادات Resend الخارجية والمفتاح الأقل صلاحية والنطاق/المرسل المعتمدان
وتصريح inbox smoke والتحقق من الوصول غير منفذة. يجب إكمال رحلة enrollment
للأهل السابقين وخطة دعم فاقد كلمة المرور والبريد الموثق مع إبقاء العمليات غير
المثبتة مغلقة. لا تفترض OTP أو تغييراً إدارياً أو تغيير رقم عبر البريد.

تفاصيل المتطلبات والأوامر في [Resend setup](RESEND_PARENT_RECOVERY_SETUP.md)،
والقبول الصناعي في [Staging runbook](PARENT_PORTAL_STAGING_READINESS.md).

| القرار | الحكم | السبب |
| --- | --- | --- |
| Local technical readiness | **PASS** | 1425 Backend و442 Frontend و9 E2E، الفحوص الثابتة والهجرات وRLS/PDF/DR ناجحة من الكود المثبت |
| Restricted synthetic Staging readiness | **PASS** | HTTPS/UID مقيد/RLS/Celery/Redis/private storage، بيانات صناعية فقط، لا إرسال خارجي أو تسجيل عام |
| Public production readiness | **FAIL — غير جاهز للفتح حالياً** | مفتاح Resend المقيد ونطاق/مرسل معتمدان وinbox smoke مصرح به وخطة enrollment للأهل السابقين لم تنفذ تشغيلياً |

ما يحتاج إغلاقاً قبل الفتح:اعتماد المرسل والنطاق ومفتاح إرسال محدود، ضبط
الإعدادات الآمنة للتطبيق والعامل، قبول وصول رسالة تحقق ورسالة استرداد مصرح بهما
من التطبيق مع فحص عدم التكرار، وخطة دعم/enrollment للحسابات السابقة التي لا
تملك بريداً موثقاً. لا تغني SUBMITTED_TO_PROVIDER أو المحاكاة عن إثبات الوصول.
تبقى feature-off في الإعداد الخارجي إلى إكمال ذلك، والتسجيل المدرسي معطلاً
افتراضياً؛ تجربة localhost الصناعية ليست نشر Staging خارجي أو إنتاجي.

سياسة الاسترداد البريدي المعتمدة في هذا الطلب منفذة لكلمة المرور فقط. افتقار
سياسة الاستعادة المركزية/تغيير الجوال لا يبطل اعتماد هذه السياسة المحددة؛ تلك
العمليات خارج الإصدار الأول ومغلقة. من فقد كل كلمة مرور وبريد موثق لا يملك
إثباتاً آلياً؛ لا يعالج بإنشاء حساب مكرر أو بتغيير إداري أو OTP مفترض. الحسابات
عالية الامتياز تظل محجوبة عن الاسترداد البريدي المنفرد.

لا توجد ثغرة عالية/حرجة مثبتة غير معالجة ضمن نطاق التحقق. المخاطر المتبقية هي
قبول الإرسال الخارجي غير المنفذ، تشخيصات OpenAPI القديمة، وقياسات محلية لا
تثبت سعة الإنتاج. لم يحدث push أو merge أو نشر إنتاجي أو إرسال SMS/Resend فعلي.

Commit التسليم النهائي توثيقي فوق SHA الكود المختبر؛ اختبار تطابق مسارات
backend/frontend/scripts/infra وCompose والإعدادات مع12a1050 يثبت أن نتائجه
تنطبق على الكود المسلّم. يمكن إعادة التنفيذ من Commit التسليم بالشروط والأوامر
المتتبعة أعلاه وفي دليل Staging، دون ملفات مصدر غير متتبعة أو مفاتيح إنتاجية.

## 12. جرد المصدر النهائي

A يعني ملفاً جديداً، وM ملفاً موجوداً عُدّل؛70 مساراً فقط، دون الأدلة المتجاهلة.

```text
A	backend/parents/credential_protection.py
A	backend/parents/email_recovery_api.py
A	backend/parents/email_recovery_models.py
A	backend/parents/email_recovery_provider.py
A	backend/parents/email_recovery_services.py
A	backend/parents/email_recovery_tasks.py
A	backend/parents/email_recovery_urls.py
A	backend/parents/migrations/0007_guardianregistrationrequest_email_encrypted_and_more.py
A	backend/parents/migrations/0008_retained_recovery_credential_mobile_guard.py
A	backend/tests/parent_email_helpers.py
A	backend/tests/test_parent_email_credential_boundary.py
A	backend/tests/test_parent_email_initial_password_race.py
A	backend/tests/test_parent_email_migration_safety.py
A	backend/tests/test_parent_email_provider.py
A	backend/tests/test_parent_email_recovery.py
A	backend/tests/test_parent_email_school_purge.py
A	docs/PARENT_EMAIL_RECOVERY_ARCHITECTURE.md
A	docs/PARENT_EMAIL_RECOVERY_VERIFICATION.md
A	docs/RESEND_PARENT_RECOVERY_SETUP.md
A	frontend/e2e/parent-email-mailbox.ts
A	frontend/e2e/parent-email-recovery.spec.ts
A	frontend/src/features/parent/emailRecovery.test.tsx
A	frontend/src/features/parent/EmailRecoveryPages.tsx
A	frontend/src/features/parent/recoveryEmail.ts
M	.env.example
M	backend/accounts/admin.py
M	backend/accounts/api/views.py
M	backend/config/settings/base.py
M	backend/config/settings/parent_staging.py
M	backend/config/settings/production.py
M	backend/config/urls.py
M	backend/operations/error_tracking.py
M	backend/parents/access.py
M	backend/parents/api.py
M	backend/parents/management/commands/seed_parent_e2e.py
M	backend/parents/management/commands/seed_parent_staging.py
M	backend/parents/models.py
M	backend/parents/serializers.py
M	backend/parents/services.py
M	backend/platform_team/api.py
M	backend/platform_team/services.py
M	backend/staff/services/management.py
M	backend/subscriptions/services/school_accounts.py
M	backend/subscriptions/services/school_purge.py
M	backend/tests/conftest.py
M	backend/tests/test_parent_concurrency_performance.py
M	backend/tests/test_parent_independent_account_security.py
M	backend/tests/test_parent_independent_migrations.py
M	backend/tests/test_parent_independent_performance.py
M	backend/tests/test_parent_portal.py
M	backend/tests/test_parent_release_performance.py
M	backend/tests/test_parent_release_read_scopes.py
M	backend/tests/test_parent_requests.py
M	docker-compose.parent-staging.yml
M	docs/PARENT_ACCOUNT_RECOVERY_ARCHITECTURE.md
M	docs/PARENT_ACCOUNT_RECOVERY_OPERATIONS.md
M	docs/PARENT_PORTAL_STAGING_READINESS.md
M	frontend/e2e/parent-portal.spec.ts
M	frontend/playwright.parent.config.ts
M	frontend/src/app/cacheSafety.test.ts
M	frontend/src/app/cacheSafety.ts
M	frontend/src/features/auth/LoginPage.tsx
M	frontend/src/features/parent/api.ts
M	frontend/src/features/parent/parent.test.tsx
M	frontend/src/features/parent/ParentPages.tsx
M	frontend/src/features/parent/ParentShell.tsx
M	frontend/src/features/parent/RegistrationPage.tsx
M	frontend/src/routes/index.tsx
M	scripts/parent_staging_acceptance.py
M	scripts/parent_staging_storage.py
```
