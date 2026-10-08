# Parent Portal — Independent Verification & Release Readiness

تاريخ المراجعة: 2026-10-08. هذه مراجعة للكود والتنفيذ الحاليين، مع اختبارات إثبات
قبل الإصلاح؛ نتائج A–F السابقة ليست نتائج هذه المراجعة.

## 1. Executive Summary

حالة التقرير: جارٍ استكمال Regression والتحقق من Checkout مثبت ونظيف.
لا يصدر حكم PASS قبل إتمامها. نطاق العمل محلي فقط؛ لا push أو merge أو نشر،
ولا SMS حقيقي أو مفاتيح إنتاجية أو بيانات مدارس حقيقية.

المراجعة أثبتت تجاوزين لإعادة تعيين كلمة مرور الحساب العالمي، وفجوة في ثبات هوية
العلاقة في PostgreSQL، وتعطلين متزامنين للدمج مع نور، وتعطلاً عند إنشاء المستند
الأولي، وفقدان توثيق تعديل التواصل، وعدم رفض رمز تفعيل بعد تصحيح هوية الطالب،
ومشكلات إزالة البيانات عند فقدان الصلاحية في واجهة مفتوحة، وتسرب رموز وهوية في Telemetry عند الاستثناء. أصلحت الحالات المثبتة
فقط، مع الاحتفاظ بقواعد الحضور والغياب والاستئذان وSMS الحالية.

استعادة الحساب عند فقدان رقم الدخول **غير منفذة بأمان حالياً**. الطلبات PENDING
ولا يوجد منفذ لتغيير `User.mobile`. هذا عائق قبل الإطلاق العام، وليس وظيفة تعمل.
يمكن اختبار إصدار Staging صناعي مع إبقاء التسجيل المدرسي معطلاً افتراضياً.

## 2. Repository State

- Repository: `xmansx2030-lgtm/xmansx`.
- Branch: `feature/parent-portal-20261008`.
- بداية هذه المراجعة وBaseline: `286c7163b57686575f4cb3785532c239fa338624`.
- عند البداية: تنفيذ البوابة السابق غير مثبت؛ 63 ملفاً جديداً و41 معدلاً، وفق
  الجرد الذي طابق فحص Git. لم توجد تعديلات مستخدم غير مرتبطة تم حذفها أو استبدالها.
- `package.json` و`package-lock.json` و`backend/pyproject.toml` لم تتغير عن Baseline.
- الإصدار المثبت وCheckout النهائي: يستكملان أدناه بعد التحقق الفعلي.
- Logs وبيانات Fixture الصناعية ولقطات الشاشة وملفات PDF الناتجة ملفات تشغيل
  متجاهلة؛ لا تدخل Commit. إعداد الاختبار وSeeder وCompose ملفات مصدر متتبعة.
- تم فحص هوية Git العامة والمحلية قبل التثبيت؛ لا تغيير للهوية أو بيانات اعتماد Git.

المرجع التاريخي A–F يظل كما هو؛ تصحيح سياسة Reset الحالية موثق في
[حماية التواصل](PARENT_PORTAL_CONTACT_SECURITY.md) و[التشغيل](PARENT_PORTAL_OPERATIONS.md).

## 3. Architecture Review

البوابة تطبيق Django ضمن Modular Monolith، وتعتمد حساب `accounts.User` والجلسات
والعضويات والاشتراك والطلاب والقيود والتحضير و`SchoolArrival` والأعذار والمستندات
والإرشاد والتدقيق الموجودة. طلب العذر/التصحيح سجل طلب مستقل، وليس سجلاً موازياً
لحقيقة الحضور. الاعتماد يعيد استخدام خدمات المنصة الحالية.

اكتشاف العلاقة العالمي يعرض معرفات العلاقات المملوكة فقط، ثم يعاد التحقق داخل
سياق المدرسة والطالب والعلاقة الحالية. لا يمنح ولي الأمر عضوية مدرسة أو صلاحية
موظف. React/TanStack Query يستخدمان فضاءً منفصلاً؛ Polling يقرأ نفس Backend.
Redis للأمان والحدود، وCelery لمسار SMS الموجود؛ لا قناة غياب ثانية.

الجرد التفصيلي لتعديلات الأنظمة السابقة مرفق في نهاية التقرير. لا إعادة تصميم
أو تغييرات Dependencies أو Cache دائم جديد لبيانات الأبناء.

دين معماري صريح: ADR-001 يمنع استيراد Models تطبيق آخر مباشرة داخل Views، لكن
`parents/contact_api.py` و`request_api.py` يستوردان Student/GeneratedDocument/
StudentWarning/CounselorCase مباشرة. هذا تعارض قابل للصيانة، دون ثغرة مثبتة؛ نقل
الاستعلامات إلى Selectors/Services خارج نطاق إصلاحات هذه المراجعة المحدودة.

## 4. Security Review

اختبارات HTTP الفعلية أعادت قبل الإصلاح ست حالات Reset من Django Admin وست حالات
Reset مركزي ناجحة خلاف السياسة، مع حالات ACTIVE/SUSPENDED/REVOKED. بعد الإصلاح:
Admin يرفض GET/POST وتبديل Hash عبر `save_model`؛ Reset المنصة يرفض الحساب العالمي
حتى مع `confirm_shared_account_impact=true`. Reset الموظف غير المرتبط يبقى متاحاً.
تأكيد أثر التغيير ليس إثبات ملكية، وSUPERUSER في Admin لا يمثل إجراء استعادة معتمداً.

التفعيل يستخدم رمزاً عشوائياً 256-bit مخزناً كبصمة SHA-256، بمدة صلاحية محدودة
ومرة واحدة، مع قفل الطالب والطلب والرمز في معاملة. حساب موجود يتطلب جلسة نفس
`User.id`؛ لا تتغير كلمته أو جواله ولا ينشأ حساب مكرر. أضيف تحقق هوية الطالب
المعتمدة عند فحص التفعيل وإكماله وإعادة إصداره بعد إثبات فشل الفحص السابق.

اختبار SQL بدور `NOSUPERUSER NOBYPASSRLS` أثبت إمكانية إعادة ربط `user_id` أو
`student_id` قبل الإصلاح. وتغيير متسق للمدرسة والطالب من سياق منصة مخول كان ممكناً
أيضاً. Migration0005 يمنع تغير هوية العلاقة حتى مع ذلك السياق؛ التغيرات المشروعة
لحالتها تبقى متاحة. لا تخفيف لسياسات RLS أو قيود الهوية الدقيقة.

التحميل الخاص يعيد فحص العلاقة والنشر والمصدر والمستند داخل معاملة مقفلة. الملف
غير المنشور أو الأجنبي أو المسحوب يعيد رفضاً، ولا `.url` عام للتخزين الخاص.
استجابات API تستخدم `no-store`. السحب لا يستطيع محو نسخة حملها الشخص سابقاً؛
المطلوب المثبت هو منع الطلب التالي وإزالة بيانات التطبيق وCache الخاص.

التحقق يشمل مستخدماً موظفاً وولي أمر في ثلاث مدارس، حساباً خاطئاً، جلسة مجهولة،
تعليقاً وإلغاءً، مرفقاً وPDF أجنبياً موجوداً فعلاً، ومحتوى المرشد الداخلي.
لا تستخدم اختبارات العزل Mock لـPostgreSQL.

## 5. Account Recovery Review

**هل توجد استعادة آمنة لتغيير رقم الدخول عند فقدانه؟ لا، ليس في التنفيذ الحالي.**
إذا كان يعرف رقمه المسجل وكلمة المرور يستطيع الدخول حتى مع فقدان SIM؛ المصادقة
بكلمة مرور ولا تشترط استقبال SMS. هذا استمرار للدخول القديم وليس تغييراً للرقم
أو استعادة عند نسيان الاعتماد. لا تستخدم تسجيلاً جديداً برقم آخر كبديل للاستعادة.
Uniqueness الحالية للرقم المطبع، وليس إثباتاً لهوية الشخص عبر أرقام مختلفة؛ غياب
سجل مالك مستقل يمنع الجزم بأن تسجيلين برقمين مختلفين لشخصين مختلفين.
تحديث `Student.guardian_mobile` لدى مدرسة أو من نور لا يغير `User.mobile` أو
`User.id` ولا يحذف الحساب أو علاقات المدارس الأخرى أو أدوار الموظف. العلاقة
المرتبطة بالتواصل تتعلق، حتى لو عاد الرقم القديم. هذا يحمي البيانات لكنه لا
يحل الوصول إلى حساب نُسيت كلمته وفقد صاحبه رقم الدخول.

المنفذ: طلب `GlobalMobileChangeRequest` مشفر ومقيد بمدرسة وبصلاحية Manager/VP،
وحارس PostgreSQL يمنع تغيير الرقم العالمي، وReset ولي الأمر عبر المدرسة والمنصة
وAdmin معطل. تغيير كلمة المرور الذاتي يتطلب الكلمة الحالية.

غير المنفذ: سجل مستقل موثق لهوية صاحب الحساب الأصلي، تحقق ملكية الرقم الجديد،
مراجعان مركزيان، مخزن إثبات خاص وسياسة احتفاظ، إجراء إتمام معتمد، إبطال شامل
للجلسات والرموز، وتدقيق استعادة مكتمل. طلب مدرسة واحدة وملاحظتها لا يوفر ذلك.
لا OTP مفترض، ولا SMS جديد للاستعادة أو تغيير الرقم.

إجراء مقترح للمراجعة التشغيلية فقط، **غير معتمد وغير قابل للتنفيذ الآن**:

1. دعم مركزي يستقبل طلباً موثقاً مرتبطاً بمعرف الحساب القديم، ويبقيه PENDING.
   الموظف المدرسي جامع طلب فقط، ولا يعتمد أو ينفذ تغيير الحساب العالمي.
2. حضور إلى نقطة تحقق معتمدة؛ موظف تحقق مستقل يقارن وثيقة أصلية مع إثبات سابق
   مستقل يربط الشخص بصاحب الحساب القديم. اسم الطالب/هويته/رقمه/طلب تفعيل أو
   ملاحظة حديثة من المدرسة لا تكفي. غياب إثبات سابق موثوق يبقي العملية معطلة.
3. تحقق مستقل من ملكية الرقم الجديد عبر سجل مشغل اتصالات قابل للتحقق وصاحب
   الهوية نفسه. امتلاك SIM أو إدخال رقم أو Screenshot لا يثبت ملكية الحساب القديم.
4. مراجع مركزي ثان بحساب وصلاحية مختلفين يراجع الإثباتين وتعارض المصالح والأثر
   على جميع المدارس. اختلاف المراجعين أو نقص الأدلة يمنع الإتمام.
5. تجهيز نتيجة قابلة للمراجعة تحفظ `User.id` وكل العلاقات والعضويات؛ معالجة تعارض
   رقم مرتبط بحساب آخر دون دمج أو نقل صلاحيات. حفظ الأدلة في مخزن خاص محدود الغرض؛
   Audit يحفظ المراجعَين ومرجع القضية والنتيجة دون الهوية أو الرقم أو الوثائق الخام.
6. خدمة مستقبلية معتمدة تقفل الحساب وتعيد فحص الأدلة وUniqueness في معاملة، وتبطل
   جميع الجلسات القديمة بتغيير اعتماد/Security Epoch مدروس، والرموز المرتبطة القديمة.
   تغيير الجوال وحده لا يبطل جلسات Django. لا تعطيل Trigger أو تجاوز SQL في هذا التقرير.
7. إخطار عبر قناة مستقلة موثوقة والتحقق من دخول جديد ورفض كل الجلسات القديمة،
   دون SMS استعادة. لا تعاد الجلسات أو العلاقات تلقائياً عند الرجوع عن العملية.

قبل الإطلاق العام يجب اعتماد وتوفير هذه الآلية أو معالجة العائق رسمياً.
لا يُطلب من صاحب الحساب إنشاء حساب آخر أو نقل أبنائه إلى هوية جديدة.

## 6. Noor & Contact Security

الرقم المكافئ بعد التطبيع لا يغير Revision. نور الفارغ أو غير الصالح يحتفظ
بالتواصل السابق وفق Baseline؛ الكتابة المباشرة/اليدوية التي تمسحه أو تغيره بصورة
مؤثرة تعلق العلاقات المرتبطة وتبطل التفعيل داخل معاملة الطالب نفسها. الأسماء
العربية والتغير الحقيقي والعودة للرقم السابق و`save/update/bulk_update/SQL`
مغطاة، دون إعادة تفعيل تلقائية أو تعديل هوية دخول الحساب.

اختبارات Commit نور الفعلي تغطي ست قيم، Commit مكرر لنفس Job، Job جديد مطابقاً،
وحقن فشل مباشرة بعد كتابة الطالب لإثبات Rollback للطالب والعلاقة والرمز والمراجعة
والتنبيه وJob/Staging. اختبارات التزامن تشمل الموافقة والتفعيل في ترتيبَي القفل.

أثبتت المراجعة Deadlock حقيقياً بين دمج الطلاب/التسوية ونور؛ أصلح بأخذ قفل المدرسة
قبل الطالب. وأثبت إنشاء PDF الأولي مقابل Acknowledgement دورة أقفال؛ قفل سعة
المدرسة الموجود يؤخذ أولاً في معاملة الإنشاء القصيرة، دون نقل Rendering إلى القفل.
حدود الاختبار 5s للقفل و15s للاستعلام مع Events محددة، دون تأخيرات تخفي التعارض.

تعديل الطالب القديم كان يقبل `contact_verification_note` دون حفظه؛ الإصلاح يحفظه
في مراجعة Revision الحالية فقط، ولا يستبدل الإثبات عند تعديل مكافئ لا يغير التواصل.
لا تنتقل العلاقات أو الطلبات أو النشر أثناء الدمج؛ المصدر المرتبط يظل مانعاً صريحاً.

ملاحظة محدودة: Python يستخدم `casefold` والـTrigger `lower` للاسم؛ بعض أشكال
Unicode اللاتينية مثل Straße/STRASSE قد تعلق العلاقة احتياطياً. لا تمنح وصولاً
إضافياً؛ لم يُغيّر التطبيع العام ضمن هذه المراجعة.

## 7. Existing Absence SMS Regression

تم استخراج مصادر الدوال من Baseline مباشرة؛ الدوال التالية متطابقة:
`candidate_absences`, `eligible_absences`, `recipient_issue`, `integration_payload`,
`save_integration`, `absence_message_template`, `render_absence_message`.
`school_sms/models.py`, `api.py`, `providers.py` متطابقة بعد توحيد نهايات الأسطر.

Dreams وMsegat وإعداد كل مدرسة والمعاينة والاختيار والصلاحيات والقوالب والسجل
ومنع التكرار وFAILED/UNKNOWN وفحص المستلم وRetry الحالي تستمر عبر Regression.
اختبارات إضافية لكلا المزودين: جدولة، ثم تغير رقم الطالب، ثم Worker يرفض قبل المزود
بـ`PRE_SEND_STATE_CHANGED` دون إرسال؛ Retry صريح لـFAILED يستخدم الرقم الحالي مرة
واحدة مع عداد المحاولة الموجود. كل استدعاء مزود Mock؛ لا إرسال خارجي.

مصدر المستلم يبقى `Student.guardian_mobile`. حساب ولي الأمر وعلاقته ليسا شرطاً؛
اختبارات SMS تشمل مستحقاً غير مسجل بالبوابة. الاستثناء الأمني الوحيد هو حظر صريح
للـStudent+الرقم الحالي، في المعاينة والطابور والعامل، دون تعطيل بقية الطلاب.

`FULL` يعني غياب كل الحصص **المعتمدة**، ويمكن أن يكون اليوم INCOMPLETE. أهلية SMS
السابقة تتطلب FULL وغياباً غير معذور وحصصاً معتمدة، ولا تشترط COMPLETE.
عرض البوابة يميز اليوم غير المكتمل؛ لم تتغير قاعدة إرسال SMS لهذا الاختلاف.

## 8. Student Leave & Gate Verification

كل ملفات `student_leaves` والحارس مطابقة Baseline. لا Parent Leave/Early Release
API أو زر أو نموذج أو صلاحية تأكيد خروج. تبقى إجراءات الحضور المدرسي والحارس
والمدير والوكيل وخدمات `StudentGateRelease` السابقة.

اختبار مستقل يرفض 403 من **المسارات الموجودة** `/api/v1/gate/student-leaves/`
ومسار التأكيد، إضافة إلى إنشاء الاستئذان الإداري. أصلح نقص إثبات سابق كان يقبل
404 لمسار غير موجود؛ لم يُغيّر كود الحارس لجعل الاختبار يمر.

## 9. Functional Verification

الاختبارات الجديدة والمجموعات الحالية تعاد فعلياً لتغطية: رابط/QR المدرسة، طلب
جديد وحساب موظف موجود، الموافقة والرفض واستكمال البيانات والتفعيل وانتهاء الرمز
ومرة واحدة وتغير الهوية، وثلاث مدارس بنفس المستخدم، وسحب علاقة دون تأثر البقية.

حقائق الحصص حاضر/غائب/لم تبدأ/غير مكتملة/معتمدة؛ لا تأخر دقائق داخل الحصة.
التأخر صباحي من `SchoolArrival.counted_late_minutes` فقط. لا تُستنتج حالة غياب من
عدم وجود بصمة. الأعذار PENDING ثم قرار مخول يستخدم خدمة الأعذار دون تغيير علامة
المعلم. تصحيح الحضور يعتمد بالخدمة وسجل التغيير الموجودين، ولا يحرره ولي الأمر.

الإنذار الصادر والمستند المسموح والنشر العائلي فقط يظهر، وAcknowledgement صريح
ومنـفصل عن قراءة التنبيه. ملاحظات المرشد الداخلية والملفات غير المنشورة محجوبة.

## 10. Frontend Review

أصلح شرط الحساب الخطأ في التفعيل باستعمال `requires_login` حتى مع جلسة حالية.
عند رفض تحميل/إقرار/POST، تمسح الذاكرة الخاصة ويعاد فحص علاقة الطفل؛ سحب النشر
وحده يحدث قائمة النشر دون إلغاء طفل صالح، و403 للاشتراك Read-only لا يخفيه.
انتهاء الجلسة يمسح Auth/Query Cache ويوجه الدخول، دون نجاح وهمي لطلب عذر فشل.
التعليق المؤكد يزيل الطفل وقوائم الطلبات والتنبيهات ويوقف Polling. انتهت الرحلات الخمس كلها ناجحة، بما فيها جلستان مختلفتان لحساب الموظف وربط الحساب نفسه ورفض المستند بعد التعليق.

الفشل الأول لبيئة المتصفح كان اختيار config.settings.local مع Role مقيد، بينما ContextRLS ظلFalse؛ أصلح Harness بملف إعداد متتبع محلي صارم config.settings.parent_verification. لا تعديل Authentication/RLS policy. انتظار SW غير المتزامن في waitForFunction انتهى قبل التفعيل؛ استبدل باستطلاع expect.poll ينتظر state=activated ثم Navigation. Session-expiry يؤخر POST حتى يحذف Helper جلسات Fixture الصناعية فعلياً، مع إيقاف مؤقت لتوقيت المتصفح أثناء بدء Docker كي لا يحجب TimeoutClient نتيجة403؛ خدمة الخادم والمصادقة غير Mock.

PWA يبقي API على NetworkOnly ولا يضيف Cache دائم لبيانات الأبناء. اختبار المتصفح
النهائي يجب أن يستخدم `npm run build` ثم Preview مع Service Worker فعلي، وليس
Dev Server. تصفح PDF بعد سحب الصلاحية Offline لا يعيد محتوى من Cache قديم.

Desktop1366×900/Tablet768×1024/Mobile390×844: أُعيدت اللقطات وفُحصت بصرياً، RTL واضح ولا Page Overflow. التركيز ولوحة المفاتيح وARIA الأساسية ضمن المتصفح. هذا ليس اعتماد WCAG كاملاً أو اختبار قارئ
شاشة بشري أو Safari/Firefox أو جهاز جوال فعلي.

## 11. Performance

قياس مستقل على PostgreSQL18 بدور NOSUPERUSER/NOBYPASSRLS، ابن واحد وخمسة أبناء
في ثلاث مدارس و2000 علاقة أجنبية؛ دون Cache جديد حساس:

| Workload | SQL queries | الزمن المحلي ms |
| --- | ---: | --- |
| ابن واحد | 26 | 35.56 |
| خمس قراءات أبناء قبل البيانات الأجنبية | 130 | 37.64,42.15,40.06,43.02,41.35 |
| خمس قراءات بعد 2000 علاقة أجنبية | 130 | 79.91,54.73,79.47,57.40,48.55 |
| قائمة خمسة أبناء/ثلاث مدارس | 154 | 314.72 |
| سجل366 يوماً / يوم واحد | 22 /22 | 48.51 /26.26 |
|500 إشعار، Page20 |99 |178.09 |
|3 تحميلات PDF خاص |64 إجمالاً |60.51,51.23,49.32 |

12 طلباً متزامناً عبر6 Workers: كل طلب27 استعلاماً، 344.07–467.06ms، إجمالي1248.87ms
شاملاً تهيئة الاتصالات/الجلسات. قياس Python Tracemalloc لسجل366 يوماً: ذروة1,172,847
Byte للطلب المقاس؛ ليس RSS الكلي أو ذاكرة الإنتاج. خطة PostgreSQL الفعلية تستخدم
Index Scan على FK user_id،5 صفوف، Execution0.126ms، لا Seq Scan لفهرس المالك.

عدد الاستعلامات ثابت عند زيادة العلاقات الأجنبية وطول التاريخ، ويتناسب مع عدد
الأبناء المملوكين/المدارس؛ ليس كل الصفحات O(1) في عدد الأبناء. قائمة5أبناء154
استعلاماً والتنبيهات99 تظل تكلفة يجب قياسها تحت سعة Staging الحقيقية؛ لا ادعاء
تحسين إنتاجي أو شهادة Throughput بهذه العينات المحلية.

Polling يستخدم الأساس30s مع Jitter موجود0.85–1.15 وتأخير عند الفشل، ويتوقف بالخلفية
والسحب. Redis مستقل: used1.17MiB/peak1.19MiB في عينة بعد الاختبارات، noeviction؛
Docker snapshot Postgres105.5MiB/Redis6.121MiB. لا Celery Worker/Beat في اختبار
الويب؛ مهامه في Pytest EAGER/MOCK. لا إثبات سعة Queue/Provider أو الإنتاج.

## 12. Database & Migrations

السلسلة الكاملة: students0007–0008، parents0001–0005. الجديد في المراجعة0008 يثبت
`db_default=1` لاستمرار INSERT التطبيق القديم؛0005 يمنع تغير هوية العلاقة.
0007 السابق لم يُعدّل لإخفاء الخطأ. Historical0006 INSERT أثبت NOT NULL قبل الإصلاح
ثم نجح واحتفظ بحارس UPDATE بعده. Migrations وRLS/Constraints/Indexes تعاد في قاعدة
معزولة؛ Existing Data وCatalog results تستكمل في سجل الاختبارات النهائي.

تسلسل الإصدار: إيقاف Writers الطلاب أثناء0007→0008، تطبيق **كامل** السلسلة ثم
فحص الدور والـCatalog والمهاجرات قبل إتاحتها. رجوع التطبيق يحتفظ بالأعمدة والجداول
والـTriggers؛ لا reverse أمني أو Fake Migrations أو إعادة اعتماد تلقائية. مسارات
Reverse المدرجة في ملفات Migration ليست خطة آمنة لرجوع خدمة فعالة.

توافق INSERT القديم ليس ترخيصاً للرجوع إلى BackendBaseline كاملاً بعد وجود حسابات
ولي أمر؛ كوده السابق يفتقد حظر Reset المدرسة/المنصة/Admin. أي RollbackBackend يجب
أن يحتفظ بهذه الإصلاحات وParentsApp، وإلا يبقى خارج الخدمة. يفضل Forward Fix أو
إرجاع Frontend متوافق فقط؛ أعمدة وTriggers وحدها لا تمنع Reset القديم لكلمة المرور.

Purge القديم يسجل الأبناء والملفات والتبعيات ويحفظ الحساب العالمي ذي علاقات أخرى؛
Attachments ضمن Inventory/Quota/BackupRestore. لا حذف إنتاجي نفذ.

Readiness القديم يفحص عدد FORCE-RLS إجمالياً ولا يثبت كل Parent Trigger؛200 وحده
ليس دليل صحة الإصدار. يلزم `showmigrations` واختبار Catalog والهوية/RLS الفعلية.

OpenAPI أعيد من CheckoutBaseline منفصل:15warnings(13unique)/520errors(97unique).
قبل ضبط أسماء Enum الجديدة:18warnings/520errors؛ الثلاث الجديدة تخص أسماء
ParentRequestStatus/EXCUSE/CORRECTION وتمت معالجتها بأسماء مستقرة فقط. لا إخفاء
أو تغيير عشرات APIs القديمة. يوجد46 Parent/Staff-parent paths و51 عملية بردود
مكتوبة، بما فيها Binary. النتيجة النهائية بعد التصحيح:15warnings(13unique)/520errors(97unique)، مطابقة Baseline؛ Whole Schema
لا يعد نظيفاً حتى لو انحسرت التحذيرات إلى Baseline.

## 13. Automated Tests

بيئة المراجعة الجديدة: Windows/PowerShell، Docker image `sha256:3f6a6282c9dc6fb453db569d0fbe1b6221b4e9e35b94a1b19e616ba1452a1351`، LinuxPython3.13.16/Django5.2.18/
Pytest9.1.1/WeasyPrint70، PostgreSQL18 وRedis8 منفصلان، Node26.7.0/npm11.19.0/Playwright Chromium من بيئة العمل. Python Dependencies ضمن نطاقات المستودع؛ لم يضاف Package. اختلاف Patch
عن بيئة التقرير السابق صريح. الاختبارات الصناعية تستخدم `test_parent_verification`،
وHTTP يستخدم `parent_verification` وRole مقيداً، ولا قواعد التطبيق السابق.

| التنفيذ الحقيقي لهذه المراجعة | Passed | Failed | Skipped | المدة |
| --- | ---: | ---: | ---: | --- |
| أول إثبات حساب، Harness URL خاطئ |0 |8 |0 |57.45s |
| إثبات حساب بعد تصحيح اسم Django Admin URL، قبل إصلاح المنتج |3 |13 |0 |62.52s |
| إثبات التكامل قبل الإصلاح |14 |9 |0 |63.60s |
| إثبات المدرسة/المستند بعد تصحيح Fixture، قبل الإصلاح |0 |2 |0 |25.37s (21deselected) |
| حساب/تواصل/أداء بعد الإصلاح |49 |0 |0 |49.88s |
| التكامل الكامل بعد الإصلاح |23 |0 |0 |32.50s |
| Frontend إثبات قبل الإصلاح |31 |4 |0 |50.76s |
| Frontend إثبات بعد الإصلاح |35 |0 |0 |22.48s |
| Frontend كامل بعد الإصلاح،43files |410 |0 |0 |145.01s |
| Backend كامل،PDF/RLS/SMS/Leaves/Gate |1234 |0 |0 |439.76s |
| Production/PWA Playwright كامل |5 |0 |0 |134.69s wall |
| تقوية اختبار Gate السابق للمسار الصحيح |1 |0 |0 |13.25s |

Migrations/Telemetry/Operations31passed/0failed/0skipped في46.74s، بما فيها ترقية بيانات Baseline فعلية وفحص56policy و14table وTriggers والقيود الدقيقة. FullBackend:1234passed/0failed/0skipped في439.76s؛ يتضمن PDF فعلياً وكل الاختبارات السابقة و50 حالة Backend مستقلة جديدة. HarfBuzz-Subset deprecation warning واحد لا يفشل الاختبارات. Playwright الكامل:5passed/0failed/0skipped،2.2min (134.69s wall) على Production Preview/ServiceWorker فعلي ودور HTTP مقيد. Checkout المثبت يستكمل قبل الحكم.
Frontend Typecheck0/51.07s، ESLint0/52.16s، Build/PWA0 في55.33s؛121 Precache asset. DjangoCheck0 وMigrationCheck0 (No changes detected) وRuff0 وdiffCheck0؛ showmigrations يؤكد كامل0001–0005 وstudents0007–0008.
مصادر Evidence: `tmp/independent-*.log`؛ ملفات محلية متجاهلة، ليست اعتماداً على F.

Recipe قابلة للإعادة من أي Checkout كامل، PowerShell، دون `.env` إنتاجي:

```powershell
docker compose -f docker-compose.parent-verification.yml config --quiet
docker compose -f docker-compose.parent-verification.yml up -d postgres redis
docker compose -f docker-compose.parent-verification.yml build tests
docker compose -f docker-compose.parent-verification.yml run --rm tests python /workspace/scripts/parent_portal_verification_init.py
docker compose -f docker-compose.parent-verification.yml run --rm tests
docker compose -f docker-compose.parent-verification.yml run --rm tests python manage.py check
docker compose -f docker-compose.parent-verification.yml run --rm tests python manage.py makemigrations --check --dry-run
docker compose -f docker-compose.parent-verification.yml run --rm tests python manage.py showmigrations parents students
```

Compose يحوي بيانات اعتماد **علنية للاختبار فقط**، ويتجاهل إعدادات إنتاج المضيف،
ويمتنع Initializer عن قاعدة غير مطابقة للاسم/الدور/Host/Local Flag المحددين.
كامل جذر Checkout يركب Read-only في `/workspace`، WorkingDir `/workspace/backend`؛
لذلك `render.scalable.yaml` موجود من المصدر المتتبع دون Absolute mount خاص سابق.
تشترك حاويات Seed/HTTP في Volume تخزين خاص محلي. لا Worker أو SMS Provider.

```powershell
# Create ignored runtime directories, not missing source/configuration.
New-Item -ItemType Directory -Force artifacts,tmp | Out-Null
$fixtureRoot = (Resolve-Path artifacts).Path
docker compose -f docker-compose.parent-verification.yml run --rm --no-deps --volume "${fixtureRoot}:/fixtures" -e DJANGO_SETTINGS_MODULE=config.settings.local tests python manage.py seed_parent_e2e --password Parent-Verification-Local-2026! --output /fixtures/parent-e2e-fixture.json
docker compose -f docker-compose.parent-verification.yml up -d app
Set-Location frontend
npm ci
npm run test
npm run typecheck
npm run lint
npm run build
$env:E2E_BASE_URL = 'http://localhost:5174'
$env:VITE_PROXY_TARGET = 'http://127.0.0.1:8011'
$env:E2E_SEED_PASSWORD = 'Parent-Verification-Local-2026!'
$env:PARENT_E2E_PREVIEW = '1'
$env:PARENT_VERIFICATION_LOCAL_ONLY = '1'
npx playwright install chromium
npx playwright test --config playwright.parent.config.ts
```

أوقف التنفيذ عند Exit Code غير صفري؛ لا تعتمد آخر أمر في سلسلة بعد فشل سابق.
Seeder ينشئ مدارس جديدة صناعية ويحتاج DEBUG/المضيف المحلي أو Stack المطابق بالضبط،
ولا يمسح مدرسة قائمة. Expire-session الاختباري مقيد بالـStack والـFixture والأرقام
والعلاقات الصناعية فقط. نقص Password/Fixture يفشل بدل Skip أو كلمة سر Fallback.
أعد Seed لكل تشغيل لأن التفعيل والقرارات مرة واحدة.

## 14. Issues Found

| ID | الشدة | المشكلة والإثبات |
| --- | --- | --- |
|SEC01 |High عند تمكين Admin |Reset عالمي دون ملكية؛6 HTTP failures |
|SEC02 |High |Platform SUPPORT/OWNER Reset مع تأكيد أثر فقط؛6 HTTP failures |
|SEC03 |High |تغيير هوية علاقة مثبتة وتهديد توافق التبعيات؛SQL NB-role |
|DB01 |High للإصدار/الرجوع |Baseline Student INSERT يفشل NOT NULL؛SQL Historical Model |
|DB02 |Medium |Deadlock دمج/تسوية مقابل نور؛2 DeadlockDetected فعلية |
|DB03 |Medium |إنشاء مستند أولي مقابل إقرار ولي الأمر؛DeadlockDetected فعلية |
|SEC04 |Medium |رمز تفعيل يظهر VALID بعد تصحيح هوية الطالب؛2 HTTP cases |
|AUD01 |Medium |فقدان إثبات تعديل تواصل مقبول بالواجهة القديمة؛حقل فارغ فعلي |
|UI01 |Medium |صلاحية مسحوبة تبقي بيانات خاصة في واجهة مفتوحة/Cache |
|UI02 |Medium |جلسة منتهية أثناء POST تبقي Auth Cache وتوجيه خاطئ |
|UI03 |Low |حساب خاطئ يعرض إجراء ربط بدلاً من دخول صاحب الحساب |
|QA01 |Medium للإثبات |اختبار الحارس404 لا يثبت403؛Harness skips/password fallback |
|SCHEMA01 |Low |ثلاثة Enum naming warnings جديدة؛لا تغير Runtime |
|SEC05 |High عند تشغيل Sentry |تسرب رمز تفعيل/Receipt/جوال/هوية/إثبات في Exception Locals؛SDK scrubber proof دون Network |
|OPS01 |Public-launch blocker |لا استعادة حساب عالمية آمنة معتمدة |

أخطاء Harness الأولية ليست عيوب منتج: اسم URL Admin، حقول Warning Fixture الناقصة،
وRegex لاختبار رفض مدرسة كان يحصل أصلاً. أصلحت قبل إعادة إثبات الحالات.

## 15. Issues Fixed

SEC01/02: `accounts/admin.py`, `subscriptions/services/school_accounts.py`؛ اختبارات
HTTP للحالة والدور، صمود جلسة صاحب الحساب، وReset عادي غير مرتبط. SEC03:
`parents/migrations/0005_immutable_relation_identity.py`؛ SQL الحقيقي مع تطابق FK.
DB01: `students/models.py` وMigration0008؛ INSERT تطبيق Baseline وتحديث محمي.
DB02: `students/services/manual_merge.py`, `reconciliation.py`؛ ترتيب مدرسة→طالب.
DB03: `documents/services/generation.py`؛ قفل السعة السابق قبل Warning بالإنشاء.
AUD01: `students/services/manual.py`؛ إثبات Revision محدد دون overwrite للتعديل المكافئ.
SEC04: `parents/services.py`؛ رفض الهوية القديمة دون حساب جديد أو تغير حساب موجود.
UI01–03: `ActivationPage.tsx`, `ChildPage.tsx`؛ اختبارات فشل/نجاح مع Negative Control.
QA01: Seeder/Playwright واختبار Gate الفعلي؛ لا تعديل Attendance/SMS/Gate Runtime.
SEC05: `operations/error_tracking.py`؛ تنقيح خاص بأحداث البوابة يمحو Frame Locals ونص الاستثناء والحقول الحساسة/Fragments، مع بقاء نوع الاستثناء وسطر Stack وRequestID/ErrorCode. أربعة اختبارات SDK فعلية دون Transport، وNegative Control يبقي تشخيص Attendance.
SCHEMA01: أسماء ثلاثة Enums في `config/settings/base.py` فقط.

كل مجموعة مؤثرة يعاد اختبارها ثم Full Regression، دون حذف اختبار أمني أو إضعاف RLS.

## 16. Remaining Risks

استعادة الحساب المركزي غير منفذة وتمنع الإطلاق العام بلا حل معتمد. Whole-schema
legacy diagnostics، HMAC rotation الشامل المستقبلي، وبيانات تاريخية متعددة السنوات
في يوم واحد دون سياق محفوظ تظل حدوداً صريحة. لا Cache حساس جديد لمعالجة الأداء.

لا إثبات إنتاجي لـSMS Inbox أو Throughput/Queues أو Backup Disaster Recovery أو
HTTPS/DNS/Release SHA لأن هذه المهمة تمنع الإنتاج. اختبارات PDF/Backup محلية
صناعية؛ نجاحها لا يثبت استعادة بيئة الإنتاج. يلزم اختبار أجهزة ومتصفحات هدف Staging.
Readiness200 وحده لا يثبت Migrations/Triggers الدقيقة. لا ثغرة مثبتة متبقية يجوز
إخفاؤها؛ أي نتيجة حرجة جديدة توقف قرار الانتقال إلى Staging حتى إصلاحها.

## 17. Operational Requirements

قبل Staging: origin HTTPS موثوق لـ`PARENT_PORTAL_BASE_URL` وAllowedHosts وCSRF
TrustedOrigins، Proxy HTTPS صحيح، Cookies Secure/HttpOnly/SameSite، PostgreSQL
بدون SUPERUSER/BYPASSRLS، Redis security منفصل متاح/Fail-closed، Celery queues
والعامل الموجودين، مفاتيح FIELD_ENCRYPTION_KEYS/HMAC الحالية دون تدوير ناقص،
PrivateStorage خارج Media العام مع صلاحيات ومساحة وInventory/Backup، وعدم كشف
مفاتيح مزود المدرسة أو الرموز في Logs/Sentry. التسجيل المدرسي Disabled افتراضياً؛
التمكين لكل مدرسة مخول، وليس Feature Flag عالمي يعطل النظام السابق.

راقب5xx، أخطاء RLS/Deadlock، Rate limits، pending reviews، activationFAILED/UNKNOWN،
download denials، Queue latency/provider outcomes، استهلاك DB/Redis/Storage.
راجع Settings/Origin/Role/Catalog/Backup مع نفس SHA في Staging، دون افتراض التطابق
من نجاح هذا Checkout المحلي. لا تعديل حي للإعدادات أو DNS ضمن المراجعة.

خطة Smoke لاحقة **غير منفذة** وتحتاج تصريحاً محدداً للمدرسة الصناعية والرقم
والمزود والرسالتين، دون Bulk:

1. رقم اختبار مصرح به، مدرسة تجريبية، Dreams أو Msegat بإعداد مشفر وصلاحية Manager/VP.
2. تحقق قراءة `/api/v1/sms/integration/`، ثم تسجيل صناعي وموافقة موثقة واحدة
   `/api/v1/staff/parents/registrations/<id>/decision/` مع `delivery=SMS`؛ مرة واحدة.
3. طالب صناعي مستحق وفق **القواعد الحالية**؛ قراءة
   `/api/v1/sms/absences/preview/?date=YYYY-MM-DD` ثم إرسال اختيار Student واحد
   بـ`POST /api/v1/sms/absences/send/` (`date`,`student_ids`).
4. افحص السجل `/api/v1/sms/students/<id>/history/` وسجل المزود والمرجع والرقم
   والتكرار؛ قبول المزود مختلف عن وصول Inbox الذي يؤكده صاحب الرقم.
5. UNKNOWN لا يعاد تلقائياً. عند رقم خاطئ/تكرار/نتيجة غير متوقعة أوقف الاختبار
   وتابع السجل، دون تشغيل إعادة محاولة أو تغيير شروط الغياب. راجع السبب أولاً.
6. اختبر المزود الثاني لاحقاً بتصريح منفصل إذا كان مطلوباً؛ لا تجرب تكامل مدرسة حقيقية.

## 18. Final Decision

لم يصدر الحكم النهائي بعد: يلزم إتمام Full Regression وPWA E2E وCheckout مثبت
ونظيف وإضافة النتائج الفعلية هنا. حدود الاستعادة والاختبارات الإنتاجية تبقى مهما
نجحت الاختبارات المحلية.

## Appendix — Legacy Change Inventory

| Legacy file | Reason and actual effect of current diff | Verification / open concern |
|---|---|---|
| accounts/admin.py | Makes global mobile read-only and denies guardian password reset/save overrides; discovers relationships in subject-only context. | Preserves existing account identifiers; DB guard remains authoritative. |
| accounts/api/serializers.py | Adds one owned relation existence query and `has_parent_portal` to existing auth payloads. | No sensitive parent fields; query-count budget must be measured, not only asserted. |
| common/tenant_rls.py | Restores outer context only when PostgreSQL is not in an aborted transaction. | Avoids masking the original SQL error; existing rollback-context tests apply. |
| config/settings/base.py | Registers parents app; adds trusted base URL, activation TTL and public registration rate limits. | No provider default/legacy entitlement changes. |
| config/settings/production.py | Production parent URL is explicit rather than localhost fallback. | Delivery configuration is verified separately; no deployment performed. |
| config/urls.py | Includes new parent paths after existing leave routes. | Existing URL patterns unchanged. |
| documents/services/generation.py | Initial creation and final file/quota transaction now lock school before warning/document. | Independent initial-generation/ack race proved deadlock; both short initial creation and final quota step now lock school before warning/document. |
| operations/storage_integrity.py | Adds private parent excuse attachment to backup/restore inventory. | Existing record types remain unchanged; existing round-trip test covers bytes. |
| school_sms/services.py | Batch-checks explicit student/current-number recipient blocks in preview and queue; adds blocked count. | Candidate/FULL/eligibility/template/completeness/retry policy unchanged. |
| school_sms/tasks.py | Rechecks explicit recipient block immediately with existing pre-send eligibility/recipient hash checks. | No portal relation/account prerequisite; actual provider is mocked in tests. |
| staff/services/management.py | Teacher password reset rejects global guardian accounts, while preserving existing shared-school rejection. | Subject-only discovery; ordinary non-guardian reset regressions pass. |
| students/admin.py | Adds proof fields, validates protected changes, persists proof on new review, takes school before student lock. | Protected edit role check is manager/deputy or superuser; immutable student school DB guard. |
| students/api/views.py | Legacy PATCH accepts contact reason, identity verification flag, and proof note. | Manual proof loss reproduced and fixed without changing legacy PATCH contract. |
| students/models.py | Adds revision owned by database trigger, with persistent database default1 restored by0008. | Direct `save`, queryset, bulk and SQL contact writes covered by existing tests. |
| students/services/imports/commit.py | Safe source/actor/hash provenance; locks matched student before applying contact changes. | Real Noor approval and activation races were missing; four ordered cases added. |
| students/services/imports/comparison.py | Compares normalized stored mobile to normalized import mobile. | Blank/invalid imported phone still does not erase the saved number. |
| students/services/manual.py | Takes school then student, requires proof for protected contact change and attaches safe provenance. | Lost verification note reproduced and fixed; current-revision proof persists, normalized no-op preserves original evidence. |
| students/services/manual_merge.py | Blocks source guardian relationships; includes mobile/revision in preview fingerprint; contact reviews remain on archived source. | Real deadlock reproduced, school-first locking fixed. Revoked-source blocker policy retained. |
| students/services/reconciliation.py | Allows harmless contact-review history to remain attached to archived source. | Guardian source relations remain blockers; real student-first/Noor deadlock fixed with school-first lock. |
| subscriptions/services/school_accounts.py | Guards guardian mobile and unconditionally denies guardian platform password reset; shared-account impact confirmation remains only for unrelated employee resets. | Existing non-parent path unchanged. |
| subscriptions/services/school_purge.py | Retains orphan staff account when guardian relations remain at another school. | Existing generic graph already includes new school models/files; no bulk deletion run. |
| subscriptions/usage.py | Counts parent private attachment bytes in school storage usage. | No staff/student/device counting changes; quota tests serialize two children. |
| tests/test_queries.py | Expands school counts to 1/4/20 and active/no-active contexts; +1 owned lookup, existing active-context queries are explicit. | Root measures query counts; no implementation-equivalent test added here. |
| tests/test_student_reconciliation_audit.py | Adds review-retention and source-grant rejection regressions. | Existing attendance collision test assertions retained. |

| Legacy frontend/config/docs | Reason and impact |
| --- | --- |
| .env.example / .gitignore | Trusted parent origin/limits and ignored synthetic fixtures/screenshots; no production secrets. |
| frontend/src/api/client.ts + client.test.ts | Correct multipart headers; preserve CSRF/session/timeout/URLs. |
| frontend/src/app/AppShell.tsx | School role-scoped management link and employee/parent space switch. |
| frontend/src/components/Tabs.tsx | Optional idPrefix connects ARIA panels; existing keyboard behavior retained. |
| auth/LoginPage, ChangeInitialPasswordPage, PublicRootPage | Shared destination preserves platform/employee/forced-password priority, adds parent-only destination. |
| auth/SelectSchoolPage, guards.tsx | Avoid parent-only staff school-picker loop; membership/role guards stay. |
| auth/returnTo.ts + returnTo.test.ts | Anchored parent/UUID allowlist; reject activation fragments and external URLs. |
| settings/SettingsPage.tsx | Role-protected parent tab; existing default and other tabs retained. |
| routes/index.tsx / types/auth.ts | Separate authenticated parent space; optional additive has_parent_portal. |
| docs/SCHOOL_SMS.md | Document existing FULL vs completeness and narrow explicit recipient blocks. |
| operations/error_tracking.py (independent audit) | Scrub only parent exception sensitive locals/fields/bearer fragments; unrelated diagnostics retained. |
| config/settings/base.py (independent audit) | Stable names for only three new parent enums; runtime contracts unchanged. |

Root-level full checkout mount is part of the tracked verification recipe; no old absolute root-file mount is required.


### Exact final source inventory

74 new files and42 modified files relative to the starting HEAD; all historical104 retained.

New files:

```text
backend/config/settings/parent_verification.py
backend/parents/__init__.py
backend/parents/access.py
backend/parents/api.py
backend/parents/apps.py
backend/parents/contact_api.py
backend/parents/contact_security.py
backend/parents/contact_urls.py
backend/parents/management/__init__.py
backend/parents/management/commands/__init__.py
backend/parents/management/commands/seed_parent_e2e.py
backend/parents/migrations/0001_initial.py
backend/parents/migrations/0002_contact_security_and_rls.py
backend/parents/migrations/0003_exact_family_identity_guards.py
backend/parents/migrations/0004_durable_contact_resolution.py
backend/parents/migrations/0005_immutable_relation_identity.py
backend/parents/migrations/__init__.py
backend/parents/models.py
backend/parents/purge_integration.py
backend/parents/rate_limit.py
backend/parents/request_api.py
backend/parents/request_models.py
backend/parents/request_serializers.py
backend/parents/request_services.py
backend/parents/request_urls.py
backend/parents/security.py
backend/parents/selectors.py
backend/parents/serializers.py
backend/parents/services.py
backend/parents/urls.py
backend/students/migrations/0007_guardian_contact_revision.py
backend/students/migrations/0008_guardian_contact_revision_db_default.py
backend/tests/test_parent_concurrency_performance.py
backend/tests/test_parent_contact_security.py
backend/tests/test_parent_enrollment_years.py
backend/tests/test_parent_http_rls.py
backend/tests/test_parent_independent_account_security.py
backend/tests/test_parent_independent_integrations.py
backend/tests/test_parent_independent_migrations.py
backend/tests/test_parent_independent_performance.py
backend/tests/test_parent_independent_telemetry.py
backend/tests/test_parent_noor_concurrency.py
backend/tests/test_parent_portal.py
backend/tests/test_parent_requests.py
backend/tests/test_parent_sms_regression.py
backend/tests/test_parent_sql_context_errors.py
docker-compose.parent-verification.yml
docs/PARENT_PORTAL_ARCHITECTURE.md
docs/PARENT_PORTAL_CONTACT_SECURITY.md
docs/PARENT_PORTAL_INDEPENDENT_VERIFICATION.md
docs/PARENT_PORTAL_OPERATIONS.md
docs/PARENT_PORTAL_STAGE_A_REPORT.md
docs/PARENT_PORTAL_STAGE_B_REPORT.md
docs/PARENT_PORTAL_STAGE_C_REPORT.md
docs/PARENT_PORTAL_STAGE_D_REPORT.md
docs/PARENT_PORTAL_STAGE_E_REPORT.md
docs/PARENT_PORTAL_STAGE_F_REPORT.md
docs/adr/ADR-012-guardian-access-independent-of-imported-contact.md
frontend/e2e/parent-portal.spec.ts
frontend/playwright.parent.config.ts
frontend/src/features/auth/destination.ts
frontend/src/features/parent/ActivationDelivery.tsx
frontend/src/features/parent/ActivationPage.tsx
frontend/src/features/parent/ChildPage.tsx
frontend/src/features/parent/ParentManagementPage.tsx
frontend/src/features/parent/ParentPages.tsx
frontend/src/features/parent/ParentSettingsTab.tsx
frontend/src/features/parent/ParentShell.tsx
frontend/src/features/parent/RegistrationPage.tsx
frontend/src/features/parent/SpaceSwitchButton.tsx
frontend/src/features/parent/api.ts
frontend/src/features/parent/parent.test.tsx
frontend/src/features/parent/shared.tsx
scripts/parent_portal_verification_init.py
```

Modified files:

```text
.env.example
.gitignore
backend/accounts/admin.py
backend/accounts/api/serializers.py
backend/common/tenant_rls.py
backend/config/settings/base.py
backend/config/settings/production.py
backend/config/urls.py
backend/documents/services/generation.py
backend/operations/error_tracking.py
backend/operations/storage_integrity.py
backend/school_sms/services.py
backend/school_sms/tasks.py
backend/staff/services/management.py
backend/students/admin.py
backend/students/api/views.py
backend/students/models.py
backend/students/services/imports/commit.py
backend/students/services/imports/comparison.py
backend/students/services/manual.py
backend/students/services/manual_merge.py
backend/students/services/reconciliation.py
backend/subscriptions/services/school_accounts.py
backend/subscriptions/services/school_purge.py
backend/subscriptions/usage.py
backend/tests/test_queries.py
backend/tests/test_student_reconciliation_audit.py
docs/SCHOOL_SMS.md
frontend/src/api/client.test.ts
frontend/src/api/client.ts
frontend/src/app/AppShell.tsx
frontend/src/components/Tabs.tsx
frontend/src/features/auth/ChangeInitialPasswordPage.tsx
frontend/src/features/auth/LoginPage.tsx
frontend/src/features/auth/SelectSchoolPage.tsx
frontend/src/features/auth/guards.tsx
frontend/src/features/auth/returnTo.test.ts
frontend/src/features/auth/returnTo.ts
frontend/src/features/public/PublicRootPage.tsx
frontend/src/features/settings/SettingsPage.tsx
frontend/src/routes/index.tsx
frontend/src/types/auth.ts
```
