# XMAN SX — Parent Portal Release Readiness

تاريخ التنفيذ: 2026-10-08. النطاق: إصدار محلي معزول مشتق من
`d8f8de6d4365e518cff269d438c25715c31a4a7e`، دون نشر أو Push أو Merge أو SMS
حقيقي أو بيانات مدارس حقيقية. نتائج المراجعة السابقة مرجع مقارنة فقط.

## 1. ملخص العمل

أضيف أساس **مراجعة استعادة الحساب فقط**، مع فصل المدرسة عن السلطة المركزية،
وحواجز PostgreSQL وصلاحيات مراجعين مستقلين. لا توجد استعادة نهائية تعمل.
أكد صاحب المشروع: «لا توجد سياسة معتمدة حالياً». لذلك لا يتغير رقم الدخول
ولا كلمة المرور عبر هذا المسار، ويبقى الإطلاق العام محجوباً.

أثبتت اختبارات جديدة تجاوزاً لإعادة تعيين حساب ولي أمر من إدارة فريق المنصة،
وسباقاً بين أول ربط ابن وإعادة تعيين الاعتماد، وسباقاً مماثلاً في Django Admin.
أصلحت المسارات المثبتة دون إعادة بناء البوابة. أضيف تجهيز HTTPS محلي صناعي
بخدمات PostgreSQL/Redis/Gunicorn/Celery/Beat حقيقية، وتحقق تخزين واستعادة منفصلة.
حُسنت استعلامات الأبناء والإشعارات تحت سياقات RLS المملوكة؛ لا دليل على تحسن
زمن الاستجابة أو سعة الإنتاج من هذه القياسات المحلية.

الحكم العام **PASS WITH ISSUES**: الجاهزية التقنية المحلية **PASS**، وStaging
الصناعي المحلي المقيد **PASS**، والإطلاق العام **FAIL / BLOCKED** بسبب غياب
سياسة الاستعادة وإثبات الهوية وتنفيذها النهائي. لا ثغرة عالية أو حرجة مثبتة
بقيت دون معالجة في النطاق المختبر؛ هذا لا يثبت خلو النظام من كل ثغرة محتملة.

النسخة النهائية للكود `dc079b7c102dab0c84c5b4f77c30a2f90d91fd36` اجتازت
**1318 Backend، صفر فشل وصفر تجاوز في399.47s**، وست رحلات HTTPS فعلية،
وفحوص Django/Migrations/Ruff/OpenAPI واستعادة18 ملفاً خاصاً. Frontend اجتاز
**410 اختباراً** وفحوص TypeScript/Lint/Build علىf574؛ شجرة الواجهة كاملة
متطابقة معdc079. ثبت إغلاق التسجيل الأبوي وإنشاء المدارس الذاتي بعد القبول
مع سلامة الملفات والمفاتيح والـVolumes السابقة، دون تغيير علم التسجيل في الإنتاج.

## 2. حالة استعادة الحساب العالمي

| السيناريو | المنفذ فعلياً | النتيجة |
| --- | --- | --- |
| فقد SIM مع معرفة رقم الدخول وكلمة المرور | المصادقة الحالية بكلمة المرور؛ لا تعتمد على استقبال SMS | يستمر الدخول للحساب نفسه |
| فقد SIM ونسيان كلمة المرور | استقبال طلب ومراجعة تحضيرية فقط | لا إعادة تعيين؛ عائق تشغيلي |
| تغيير رقم الدخول العالمي | طلب مشفر مرتبط بالحساب الأصلي | لا تغيير `User.mobile` |
| رقم مقترح يخص حساباً آخر | فحص التعارض قبل استمرار المراجعة | Conflict؛ لا دمج أو نقل تلقائي |
| موظف وولي أمر في آن واحد | نفس `User.id` والعضويات والعلاقات | لا سيطرة مدرسية على الاعتماد العالمي |
| علاقة معلقة | لا تنفيذ استعادة ولا إعادة تفعيل | تبقى معلقة حتى قرار المدرسة المستقل |

`Student.guardian_mobile` رقم التواصل المدرسي؛ ليس هوية الحساب العالمي.
تغيير نور أو تحديث المدرسة قد يعلق العلاقة المتأثرة، ولا يغير `User.mobile`
أو ينشئ حساباً جديداً أو ينقل أبناء المدارس الأخرى. معيار عدم تكرار الرقم
المطبع لا يثبت أن شخصاً واحداً لا يملك حسابين برقمين مختلفين؛ لا يوجد سجل هوية
مستقل معتمد يمكن استخدامه لدمج الأشخاص بأمان.

لم يوجد مصدر سبق ربطه بصاحب الحساب الأصلي يكفي لاستعادة مفقودة الاعتماد، ولا
طريقة مستقلة منفذة للتحقق من الرقم الجديد. معرفة الطالب، رقم نور، امتلاك رقم
جديد، تأكيد المدرسة، أو مرجع أدلة شكلي لا تكفي. لم يُفترض OTP، ولم يُضف SMS
استعادة. التفاصيل في [معمارية الاستعادة](PARENT_ACCOUNT_RECOVERY_ARCHITECTURE.md)
و[إجراءاتها](PARENT_ACCOUNT_RECOVERY_OPERATIONS.md).

## 3. ما نُفذ فعلياً

احتفظ التنفيذ بـDjango Modular Monolith وPostgreSQL RLS وعزل المدارس،
وSession authentication/CSRF وAudit وRedis/Celery وReact/TanStack Query/PWA
القائمة. يقرأ حقائق الحضور والأعذار والمستندات عبر النماذج والخدمات الحالية؛
لا مصدر بيانات حضور موازٍ ولا مساحة موظف جديدة لولي الأمر.

- أربعة نماذج: `GlobalAccountRecoveryCase` و`RecoveryReviewAuthorization`
  و`RecoveryEvidenceReference` و`RecoveryReviewDecision`، باستخدام المستخدم
  والمدرسة والطالب والطلب الموجودين؛ لا مصدر حضور موازٍ.
- ثلاثة أنواع طلب: استعادة كلمة المرور، تغيير الرقم، أو كلاهما. ربط المصدر
  والحساب والطالب والمدرسة غير قابل للتبديل؛ مهلة القضية30 يوماً وVersion
  مملوك لحارس قاعدة البيانات. طلب كلمة المرور يرفض إدخال رقم جديد.
- حالات `PENDING / IDENTITY_REVIEW / NEEDS_EVIDENCE / AWAITING_SECOND_REVIEW /
  POLICY_BLOCKED / REJECTED / EXPIRED / CANCELLED` فقط. لا `APPROVED/EXECUTED`.
  انتهاء الوقت يمنع المراجعة حتى دون تغيير الاسم المخزن إلى EXPIRED؛ لا ادعاء
  بوجود مهمة دورية لتحديث الحالة.
- المدرسة: Manager/VP حالي فقط، استقبال طلب لعلاقة طالبها، عرض قضاياها وإلغاؤها.
  لا مراجعة مركزية أو أدلة مركزية أو Provisioning أو إعادة تعيين عالمي.
- المركز: مسؤولية FIRST أو SECOND صريحة ومؤقتة، مع موظف منصة وحساب نشطين.
  Owner/Operations وحدهما لا يكفيان. لا API/Admin لتوفير Grants، ودور التطبيق
  لا يستطيع إنشاؤها أو تعديلها حتى مع Bypass المنصة المعتاد.
- منع صاحب الحساب ومقدم الطلب وأي عضو، حتى غير نشط، في المدرسة المقدمة من
  مراجعة القضية. المراجع الثاني مختلف؛ هما حسابا تطبيق مختلفان، وليس حسابي
  قاعدة بيانات مختلفين. ضمان أنهما شخصان مستقلان يحتاج IAM معتمداً مستقبلاً.
- مراجع أدلة UUID غير خام، محدودة الصلاحية وقابلة للإلغاء. `verified:false`
  صريح دائماً. تغييرها يبطل اعتماد Version السابق. الملاحظات المركزية مشفرة
  ولا تعود في DTO؛ Audit يحفظ المعرفات والإجراءات دون الرقم أو كلمة المرور
  أو محتوى الإثبات أو UUID المرجعي الخام.
- تسع مسارات/عشر عمليات API جديدة، Session/CSRF، DTO محدد، أخطاء إدخال طبيعية،
  Rate limits ذرية، `private/no-store`، مع Scrubbing إضافي في Error tracking.
- تكامل Purge محدد بالمدرسة والطالب والفاعل/المهمة: مراجعات ثم مراجع ثم قضية
  قبل المصدر القديم؛ لا تجاوز RLS عام ولا حذف حساب عالمي بسبب مدرسة واحدة.
- حراس Team/Admin وتفعيل حساب قائم يقفلون User ويعيدون فحص الاعتماد الحالي.
  التفعيل يرفض Snapshot أو Session hash قديماً، ويحتفظ بكلمة الحساب ورقمه.

## 4. ما بقي معطلاً عمداً

`execute_recovery()` مغلق في الكود؛ لا Feature flag يفتحه. الطلب الصحيح من
مراجع مخول لقضية موجودة يعيد423؛ قد تسبق ذلك400/403/404/429 للتحقق والصلاحيات
والقضية والحدود. لا Mutation للرقم أو كلمة المرور أو الجلسة أو الرمز.

غير منفذ: إثبات صاحب الحساب الأصلي، تحقق مستقل للرقم الجديد، مخزن وثائق إثبات
معتمد، قناة شخصية آمنة لإنشاء كلمة مرور، تنفيذ ذري/Exactly-once، إبطال شامل
للجلسات والرموز بعد استعادة ناجحة، وProvisioning IAM غير صناعي. الاختبارات
تثبت المنع وعدم التغيير؛ **لا تثبت نجاح استعادة أو إبطال جلساتها**. قبول مراجعَين
يصل إلى POLICY_BLOCKED ولا يصبح تصريح تنفيذ. لا جمع إلزامي لصور الهوية.

## 5. نتائج المراجعة الأمنية

| المسألة المثبتة | الشدة | إثبات السبب والإصلاح |
| --- | --- | --- |
| Team reset يسمح بإعادة تعيين حساب Parent-only أضيف لفريق المنصة دون عضوية مدرسة | عالية | قبل الإصلاح7 failed/4 passed في18.54s؛ بعد الحارس36 passed في22.62s؛ كل حالات العلاقة محمية |
| أول ربط بحساب قائم يقبل إثباتاً سبق Reset أثناء السباق | عالية | Restricted-role concurrency:2 failed في12.46s ثم2 passed في28.78s؛ User lock ومقارنة Hash الحالية |
| Admin password form يفحص عدم وجود علاقة قبل أول ربط، ثم يحفظ Password بعده | عالية | قبل الإصلاح اكتمل الربط ثم Reset302؛ بعد الإصلاح تُسلسل العمليتان: Reset السابق يبطل إثبات التفعيل، والحساب المرتبط يرفض Reset403 |
| Admin mobile form المفتوح قبل أول ربط يصل لحارس DB ويرفع500 بدلاً من منع صحيح | متوسطة | الرقم بقي محمياً قبل الإصلاح؛ إعادة الفحص تحت User lock تعيد403 قبل DB error |
| Joined inbox relation scan يتسع لآلاف العلاقات الأجنبية | متوسطة/أداء | SQL فعلي وEXPLAIN قبل/بعد؛ حدد Owner predicate بدل تخفيف RLS |
| Staging أغلق Parent registration دون إغلاق مسار إنشاء المدارس الذاتي | متوسطة/مطابقة تشغيلية | أغلق العلم الموجود SELF_REGISTRATION_ENABLED في البيئة الصناعية فقط؛ Profile يرفض True، وPOST فعلي بـCSRF صالح يعيد503 قبل Serializer مع ثبات عدد المدارس والمستخدمين والجلسات؛ لا واقعة إنشاء غير صناعي |

اختبارا Admin قبل الإصلاح:2 failed في19.94s، وبعد الإصلاح المجموعة الأوسع:
40 passed في28.75s، تضم الأربعة Race cases والـ18 اختباراً أمنياً سابقاً والـ11
اختبار Team جديداً والسبعة القديمة. تبقى إعادة تعيين الموظف غير المرتبط متاحة.
لم يُخفف أي اختبار أو Policy/Trigger لتمرير النتيجة.

RLS منفذ فعلياً على PostgreSQL بأدوار `NOSUPERUSER NOBYPASSRLS`، بما فيها
HTTP وAdmin والتزامن والعزل والـPurge. Recovery tables ترفض Bypass المعتاد
ما لم تتحقق سلطتها المحددة. اختبارات تشمل Foreign IDs، مدرسة أخرى، منحة منتهية
أو ملغاة، Self-review، عضو المدرسة، تغيّر Version/اعتماد، مرجع منتهٍ/ملغى،
تعارض الرقم، Repeat stage، Updates مباشرة وPrivilege escalation وRollback.
الموافقة الواحدة أو الاثنتان لا تنفذان تغييراً. معرفات العلاقات الأصلية ثابتة.

التحميل الخاص يعيد التحقق من العلاقة والنشر والمصدر الحالي. E2E يثبت403/404
بعد السحب، إزالة البيانات من صفحة مفتوحة، وعدم Cache دائم للأطفال/الملفات
عند Logout أو تبديل المستخدم. لا دعوى بإزالة ملف سبق للمستخدم تنزيله على جهازه.

## 6. نتائج Noor والتواصل والحضور

كل مجموعات الاتصال ونور والتفعيل والدمج السابقة أعيدت في Full Regression،
بما فيها `test_parent_contact_security.py`, `test_parent_noor_concurrency.py`,
`test_parent_independent_integrations.py`, reconciliation/import وSQL guards.
تطبيع الرقم المكافئ لا يسحب علاقة؛ التغير المؤثر يعلقها في المعاملة نفسها،
وDirect update/bulk_update لا يتجاوزان الحماية. لا إعادة تفعيل عند عودة الرقم.
الرقم الفارغ/غير الصالح المستورد لا يمحو الرقم الموجود حسب سياسة نور القائمة.

يبقى ترتيب القفل المدرسة ثم الطالب ثم العلاقة/المصدر. إضافة قفل User للتفعيل
لا تمنح Admin قفل مدرسة عكسياً؛ لا Deadlock مخفي بتحويل التزامن إلى Sequential.
سباقات Noor ضد الموافقة والتفعيل والدمج، وفشل المعاملة، مشمولة في الاختبارات
الحقيقية. لا مسار تنفيذ Recovery يتنافس على تعديل الجوال لأنه معطل.

لم تتغير `parents/selectors.py` أو أنظمة attendance/devices في هذه المهمة.
يعرض ولي الأمر حقائق التحضير الحالية وDraft/Submitted/Not started وعدم اكتمال
اليوم، دون تأخر حصص بالدقائق. الدقائق تخص SchoolArrival صباحاً؛7 دقائق في
Fixture مع ON_TIME=0 وغياب بصمة لا يُستنتج منه غياب. الأعذار طلبات تراجع
بالخدمات الحالية، ولا تمحو حقيقة ABSENT؛ التصحيح المعتمد يسجل AttendanceChange.

## 7. نتائج SMS وحماية الاستئذان والحارس

جميع ملفات `backend/school_sms/`, `backend/attendance/`, `backend/devices/`
و`backend/student_leaves/` متطابقة معd8 في هذه المهمة؛ لا تعديل لقواعد الأعمال.
Full Regression يعيد `test_school_sms.py`, `test_parent_sms_regression.py`
والاختبارات المستقلة، بما فيها Dreams/Msegat وMock provider وNo-account recipient
وإعادة فحص الرقم بعد الجدولة وFAILED/UNKNOWN ومنع التكرار.

يبقى مصدر المستلم `Student.guardian_mobile`؛ لا شرط User أو Guardian relation.
FULL يعني غياب جميع الحصص **المعتمدة**، وقد يكون `completeness_status=INCOMPLETE`.
لم يُضف COMPLETE شرطاً لإرسال الغياب. الحظر الأمني الموجود محدد بالطالب والرقم؛
لا يوقف رسائل بقية الطلاب. لا قناة غياب ثانية ولا Recovery SMS.

كل Student leaves/Gate regression يعاد، وE2E يرفض صلاحية Parent-only من المسارات
الموجودة. لا API/زر/نموذج Parent leave أو Early release. خروج الطالب باقٍ
إجراءً مدرسياً حضورياً. Mock provider لا يثبت قبول المزود أو وصول الهاتف؛
**لم تُرسل أي SMS فعلية**.

## 8. الأداء والاعتمادية

قياس HTTP عبر Django Client تحت الدور المقيد، مع1/5/10 أبناء وثلاث مدارس
و2000 ولي أمر أجنبي و500 إشعار لكل صاحب. المرجع يستخدم ملفات استعلاماتd8
الثلاثة كـRO overlays مشتقة من Git، مع نفس Image/Schema/Fixtures الحالية
وقاعدة اختبار جديدة. ملفات المقارنة ليست مدخلات الإصدار النهائي.

| الأبناء | SQL children قبل → بعد | SQL inbox page20 قبل → بعد | Children p50/p95 ms قبل → بعد | Inbox p50/p95 ms قبل → بعد |
| ---: | --- | --- | --- | --- |
| 1 | 38 →38 | 27 →27 | 42.102/50.514 →189.457/246.412 | 20.765/22.305 →106.705/121.198 |
| 5 | 154 →130 | 99 →73 | 142.378/210.908 →450.058/488.423 | 202.896/271.520 →306.196/349.112 |
| 10 | 299 →215 | 189 →98 | 521.581/587.974 →970.371/1043.150 | 202.996/364.157 →505.936/564.637 |

النتائج الزمنية أعلاه لعينة Intermediate batching قبل Owner predicate الأخير؛
لا ينسب التقرير إليها مكسب سرعة. Seven samples لكل حالة؛ p95 فيها Maximum
nearest-rank، وليست دراسة إحصائية للإنتاج. العدد ثابت بعد إضافة الصفوف الأجنبية.
الضوابط غير المعدلة تباطأت أيضاً:366 مقابل يوم تاريخ=22SQL،32.643/38.235→
134.205/148.507ms؛ عشرة Polls تفصيلية=26SQL لكل Poll،26.872/33.384→
101.219/184.076ms. المقارنة الزمنية متأثرة ببيئة مضيف غير مضبوطة.

20 مستخدماً مختلفاً، اتصال مقيد لكل مستخدم، طلبان لكل منهم: p50/p95
1122.977/1270.951→1685.082/2713.358ms، Burst wall2802.080→5273.880ms.
رُصد0 Waiting lock في33/40 عينة؛ دورية50ms قد تفوت انتظاراً قصيراً.
لا قياس موثوق لقمة CPU/RSS أو Throughput الإنتاج.

أظهر EXPLAIN على **COUNT/Page SQL الفعلي** في النسخة الوسيطة مسح PK غير محدود
يحذف2004/2005 علاقات أجنبية، وأحد COUNT استغرق15.260ms. الإصلاح الأخير يضيف
`relation__user_id` المطابق مع Owner/Owned IDs الحاليين. الخطط الست النهائية
تستخدم `parents_guardianstudentrelation_user_id_50f1d01c` مع Index Cond لصاحب
الحساب،10 صفوف مملوكة و0 أجنبية محذوفة، Scan0.038–0.054ms. COUNT للمدارس
الثلاث1.177/2.025/2.340ms وPage4.108/2.151/2.455ms؛ هذه Snapshots لحدود
العمل وليست Speedup أو Capacity مثبتة.

اختبار الخطة النهائي و14 Scope/IDOR/Subscription/Revocation/Lock cases:
15 passed في86.68s، وFull Regression يعيد الحالات17 الجديدة كلها. لا Index أو
Cache حساس دائم جديد، ولا تغيير DTO/Pagination/Polling30 ثانية/الاشتراك.
بقيت بعض استعلامات الحضور لكل طفل وCatch-up إشعارات مستقل؛ لا ادعاء إزالة كل N+1.
الأدلة: `tmp/release-performance-matched-before-v2.log`, `...matched-after.log`,
`...bounded-inbox-plans-scopes.log` وJSON الخطط في Checkout الإصدار.

## 9. نتائج Staging الصناعي وواجهة المستخدم

لا توجد بيئة خارجية معتمدة في الأدلة المتاحة. جهز وشُغّل **Staging محلي مقيد**
عند `https://localhost:8445` في مشروع Docker مستقل، ببيانات ومفاتيح وVolumes
صناعية جديدة، دون استعمال قاعدة الإنتاج. Runbook المتتبع:
[PARENT_PORTAL_STAGING_READINESS.md](PARENT_PORTAL_STAGING_READINESS.md).

DEBUG=False، إعدادات إنتاج، Session/CSRF secure، الأصل المحلي المحدد فقط، Admin
مغلق، Application role حقيقي NOSUPERUSER/NOBYPASSRLS. Application/Worker/Beat
UID65534، Read-only، Capabilities dropped وNo-new-privileges، شبكة داخلية دون
Default route للخارج؛ Nginx وحده ينشر منفذ loopback. Redis noeviction وقواعد
0/1/3/4 منفصلة، Worker فعلي بالصفوفcelery/imports/maintenance وBeat heartbeat فعلي.
لا بيانات مزود SMS أو Sentry/R2/نسخ دوري خارجي/وزارة في البيئة الصناعية.

Fixtures: ثلاث مدارس ومدير/وكيل/معلم/مرشد لكل مدرسة، حساب جديد وEmployee-parent
وحساب واحد بأبناء ثلاث مدارس، حاضر/غائب/Draft/Submitted/Not started، صباحي7/0/دون
بصمة، عذر مقبول/مرفوض، تصحيح مقبول/Pending، إنذار/PDF خاص وإرشاد داخلي وأسري
منفصلان. الحساب المستقل المستخدم لتبديل المستخدمين لا يعاد تفعيل علاقة سحبها
اختبار سابق. IDs صناعية، وصيغ جوال متوافقة لا ندعي أنها نطاقات اتصالات محجوزة.

التسجيل **معطل افتراضياً**؛ يفتح Seed قبول صريح ثلاث مدارس جديدة محددة فقط،
ثم يغلقها بعد E2E. انتهى التشغيل النهائي مع Global parent enabled0/SMS
integrations0/SMS notices0؛ المدارس18 كلها ذات slugs صناعية. لا فتح تسجيل عام.

إنشاء المدارس الذاتي مغلق بصورة مستقلة: `SELF_REGISTRATION_ENABLED=false`
للتطبيق والعامل وBeat والاختبارات، وProfile يرفض True قبل التشغيل. أثبت طلب
HTTPS مجهول، بعد CSRF صالح، أن `/api/v1/auth/register-school/` يعيد503
`SELF_REGISTRATION_UNAVAILABLE` قبل Serializer. قبل/بعد الطلب أثناء فتح قبول
الأبوين فقط بقيت School/User/Session counts عند18/86/22، وبعد إغلاق القبول
بقيت18/87/33. الفرق بين اللقطتين نتيجة رحلات التسجيل والدخول الفعلية؛ كل طلب
إنشاء مدرسة مرفوض له مقارنة مستقلة ثابتة. لا تعديل Base/Production أو خدمة التسجيل.

ست رحلات HTTPS حقيقية من Checkout نظيف عندdc079 نجحت: التسجيل/QR/موافقة/تفعيل/ثلاث
مدارس/حضور/عذر/تصحيح/ملف، حساب الموظف، رفض/رابط منتهٍ، Production service worker
والاتصال المفقود/التعليق، إبطال جلسة **فعلية** أثناء عذر دون نجاح وهمي، وحالات
Fixture الإضافية وتبديل مستخدمين على الجهاز. Browser/API `ignoreHTTPSErrors=false`؛
قبول Chromium للشهادة يقتصر على SPKI للشهادة الصناعية، وNode process-only
CA للشهادة نفسها؛ لا إيقاف تحقق عام أو تثبيت ثقة نظام.

تحقق الاحتفاظ: أحجام وSHA256 الملفات الستة الأصلية محفوظة؛ أصبح المجموع18
بعد إضافة Fixtures مستقلة. هويات الـVolumes الستة وملف البيئة والشهادة
ومفاتيح المشروع كما كانت؛ لا حذف أو نقل أو إعادة توليد مواد قديمة.

الصور الجديدة desktop1366×900/tablet768×1024/mobile390×844 فُحصت بصرياً؛ RTL واضح،
لا Horizontal page overflow أو Page error. اختبار Keyboard/ARIA أساسي ناجح؛
لا دعوى شهادة توافق كاملة لكل قارئات الشاشة أو الأجهزة.

## 10. قاعدة البيانات وMigrations والتخزين

يتضمن الإصدار `students0007–0008`, `parents0001–0006`؛ الجديدة هنا0006 فقط.
Dependencies تشمل accounts0002 وplatform_team0001 وschools0006 وparents0005
وstudents0008. أُصلح نقص Dependency في محاولة Fresh install فعلية:2 setup
errors في87.69s، قبل إعادة التشغيل الناجح. لم يعدل الاختبار لتجاهلها.

Four new FORCE RLS tables/17 policies؛ Parent totals18 tables/73 policies.
Runtime catalog81 FORCE RLS tables/142 policies. Guards SQL Invoker وبـsearch_path
محدد، هوية المصدر ثابتة، Stage/version/lifecycle constraints وScope purge.
Upgrade من Students0006 ببيانات حضور تاريخية فعلية وكتابة Models قديمة محفوظة
نجح. Mechanical reverse للجداول الجديدة الفارغة الصناعية اختبار آلية فقط.

قبل Upgrade قاعدة قائمة افحص حالات `parents_globalmobilechangerequest`:
يجب أن تكون PENDING قبل قيد Intake-only، وأي غير ذلك يوقف الترقية للمراجعة؛
لا تحويل أو حذف صامت. الطلبات القديمة لا تُحوّل تلقائياً إلى قضايا جديدة.
شغل DDL بدور مالك، طبق migrations ثم صلاحيات الدور، ثم خدمات SHA المتوافق.

Private volumes مستقلة عن MEDIA/Nginx، Dir700/File600، وصول عبر Permission API
فقط. Restore صناعي سابق من72 إلى قاعدة فارغة مستقلة نجح في26.27s wall
(Restore14,384ms):97 Table counts و96 Content digests مطابقة، ستة ملفات
خاصة و0 Missing/Mismatch/Error،81 FORCE RLS/142 policies محفوظة. استثني
Content BackupRun لأن Snapshot يسجل RUNNING ثم يكمل؛ العدد نفسه قورن.
لم يُستبدل Source DB أو ملفاته، ولم يتحول Application role إلى BYPASSRLS.

بعد تصحيح Storage alias، أعيد DR من1e2 النظيف على `/var/lib` إلى قاعدة جديدة
فارغة `parent_staging_restore_a3b84369bed2`: Exit0 في16.32s wall، Actual restore
10,508ms،97 Table counts/96 Content digests مطابقة، **12 Private objects**،
0 missing/mismatch/errors،81 FORCE RLS/142 policies محفوظة. الزيادة من6 إلى12
نتيجة الاحتفاظ بملفات Fixture السابق وإضافة Fixture جديد؛ لا حذف للقديم أو
تبديل للمفاتيح. فحص Runtime فعلي للتطبيق والعامل نجح (~3.95s لكل منهما)،
بـUID65534 والدور المقيد والجذور الثلاثة المركبة وصلاحيات700/600 وNo egress
وWorker/Beat heartbeat حقيقي. الأدلة المصححة منفصلة عن محاولة DR الفاشلة.

**DR النهائي منdc079 النظيف** إلى قاعدة فارغة جديدة
`parent_staging_restore_a2aee7e49a0d`: Exit0 في17.4772s wall، Actual restore
10,698ms؛97 Table counts/96 Content digests مطابقة، **18 Private objects**،
0 missing/mismatch/errors و81 FORCE RLS/142 policies. قاعدة المصدر والملفات
وصلاحيات التطبيق لم تُستبدل. فحص Runtime بعد إغلاق التسجيل نجح للتطبيق في
4.9106s وللعامل في4.5951s؛ Beat heartbeat حقيقي بعمر51.2/55.8s، مع دورتين
Scheduled/Received/Succeeded موثقتين، وليس Heartbeat مصنوعاً. تحقق TLS عادي
بشهادة المشروع يعيد readiness200؛ شروط UID65534/700/600/RLS/No egress محفوظة.

النسخ لا يكفي دون Private objects والمفاتيح؛ المواد الصناعية محفوظة منفصلة
في مجلد متجاهل. لا إثبات لتجربة استعادة إنتاج أو مخزن خارجي. Forward fix هو
الافتراضي؛ **لا Rollback يعيد Backend قبل حراس Reset القديمة أو الجديدة**،
ولا إسقاط جداول/علاقات فعلية أو Security migrations لتصحيح Release.

## 11. نتائج الاختبارات وإعادة الإنتاج

**السجل النهائي المعتمد:** Backend والفحوص والـHTTPS/Runtime/DR من Checkout
نظيف عند `dc079b7c102dab0c84c5b4f77c30a2f90d91fd36`. Vitest وفحوص الواجهة
منf574 النظيف مع إثبات تطابق شجرة `frontend` كاملة، بما فيها E2E/Config، معdc079؛
لا ادعاء بإعادة Vitest علىdc079. أعيدت الرحلات الست نفسها فعلياً علىdc079.

| الفحص النهائي | ناجح / فاشل / متجاوز أو النتيجة | زمن Runner؛ زمن الأمر Wall |
| --- | --- | --- |
| Full backend/PDF/RLS/Noor/SMS/Gate/Backup | **1318 /0 /0** | **399.47s؛406.9470s** |
| Vitest،43 ملفاً،شجرة الواجهة المطابقة | **410 /0 /0** | **121.50s؛124.978s** |
| Playwright ordinary HTTPS | **6 /0 /0** | **1.8m؛112.7441s** |
| TypeScript | Exit0 | 40.2614s |
| Strict E2E TypeScript | Exit0 | 4.744s |
| ESLint | Exit0،بلا warnings/errors | 46.317s |
| Production/PWA build | Exit0،121 precache entry | 49.375s |
| Django system check | Exit0،0 silenced | 19.7319s |
| Migration check/dry-run | Exit0،No changes | 23.0123s |
| Strict Ruff0.16.3،كل Backend/scripts تحت إعدادات Backend | Exit0،All checks passed | 15.3467s،شامل تثبيت الأداة في الحاوية المؤقتة |
| OpenAPI generate/validate | Exit0؛Legacy diagnostics محفوظة | 24.9420s |
| DR قاعدة فارغة/Private restore | Exit0؛97/96 Tables،18 files،0 errors | 17.4772s؛Restore10,698ms |
| إغلاق التسجيل الأبوي وفحص SMS | Exit0؛Global parent0/SMS0 | 4.0378s |
| Anonymous CSRF-valid school signup بعد الإغلاق | 503 SELF_REGISTRATION_UNAVAILABLE؛Counts ثابتة | 1.015s |
| Runtime بعد الإغلاق | Exit0 لكل من التطبيق والعامل | 4.9106s /4.5951s |
| git diff --check / tracked clean checkout | Exit0 /لا تغييرات متتبعة | لا أخطاء Whitespace |

الأدلة النهائية المحلية: `tmp/terminal-full-backend.log`, `terminal-ruff.log`,
`terminal-django-check.log`, `terminal-migrations-check.log`, `terminal-openapi.log`,
`terminal-staging-playwright.log`, `TERMINAL_STAGING_EVIDENCE.md`، و
`final-frontend-verification-report.md` وسجلاته. كل الأدلة تحت Checkout النظيف
ومتجاهلة في Git؛ التقرير وإعدادات إعادة التشغيل وحدهما جزء من المصدر.

الأعمال السابقة أدناه **سجل تشخيصي تاريخي** يوضح نتائج كل SHA؛ لا تستبدل
السجل النهائي ولا تنسب نتيجة من SHA آخر دون إثبات تطابق الملفات المختبرة.

Commit الكود المختبر أولاً: `72cedc1cbd424294d5c21d42977adff1ce7803ea`، من
Detached checkout نظيف مستقل. المصدر المتتبع Mount read-only كاملاً داخل
`/workspace`؛ ملفات الجذر `render.scalable.yaml` و`render.yaml` موجودة دون
استعانة بملفات غير متتبعة. Modules/Build/materials/logs runtime متجاهلة فقط.

| الفحص على72 النظيف | ناجح / فاشل / متجاوز | زمن Runner؛ زمن الأمر Wall |
| --- | --- | --- |
| Full backend/PDF/RLS/Noor/SMS/Gate/Backup | 1318 /0 /0 | 885.16s؛893.6158s |
| Vitest،43 ملفاً | 410 /0 /0 | 227.50s؛237.049s |
| Playwright HTTPS،ست رحلات | 6 /0 /0 | 3.7m؛226.8157s |
| TypeScript | Exit0 | 57.869s |
| Strict TypeScript لـE2E/config | Exit0 | 10.096s |
| ESLint | Exit0 | 189.299s |
| Production/PWA build | Exit0،121 Precache entry | 196.108s |
| Django check | Exit0 | 61.0351s |
| makemigrations check/dry-run | Exit0،No changes | 60.8519s |
| OpenAPI generate/validate | Exit0 مع Legacy diagnostics | 61.2022s |
| Ruff Backend + scripts تحت Backend config | Exit1،9 script findings | 80.9386s؛ أصلحت وأعيدت الفحوص أدناه |
| git diff --check | Exit0 | لا أخطاء Whitespace |

إعادة التحقق السابقة منf574 النظيف بعد تعديل التخزين؛ لا تُنسب إليها نتائج72:

| الفحص | النتيجة | زمن Runner؛ زمن Wall |
| --- | --- | --- |
| Full backend/PDF/RLS/Noor/SMS/Gate/Backup | 1318 /0 /0 | 504.77s؛512.7203s wall |
| Vitest،43 ملفاً | 410 /0 /0 | 121.50s؛124.978s wall |
| TypeScript | Exit0 | 40.2614s wall |
| Strict E2E TypeScript | Exit0 | 4.744s wall |
| ESLint | Exit0،بلا warnings/errors | 46.317s wall |
| Production/PWA build | Exit0،121 precache entry | 49.375s wall |
| TLS/browser من1e2 النظيف | 6 /0 /0 | 1.8m؛108.7264s wall |
| Runtime app/worker من1e2 | Exit0 لكليهما | ~3.95s wall لكل منهما |
| DR من1e2 على المسارات الدائمة | Exit0،97/96 Tables،12 files،0 errors | 16.32s wall؛Restore10,508ms |
| Strict Ruff0.16.3،Backend وكل scripts | Exit0،All checks passed | 25.5432s wall،شامل تثبيت الأداة في الحاوية المؤقتة |
| Django system check | Exit0،0 silenced | 14.6161s wall |
| Migration check/dry-run | Exit0،No changes | 18.2004s wall |
| OpenAPI generate/validate | Exit0،نفس Legacy15/520 | 16.2859s wall |

تشغيل Candidate السابق قبل تعديلات التجهيز النهائية:1318/0/0 في347.03s؛ لا يستبدل
التشغيل النظيف. فرق الزمن يؤكد أن Wall timings المحلية ليست قياس سعة.
الزيادة84 Backend فوق1234 المرجعية: اختبارات أساس وأمان/schema/races/performance
وجميع القديم محتفظ به. Frontend/src والاعتماديات والـLockfile لم تتغير.

بيئة Backend: Docker Desktop Linux، Python3.13.16، Django5.2.18، pytest9.1.1،
PostgreSQL18.6، Redis8.0.6، WeasyPrint rendering فعلي. Backend image النهائي منdc079:
`sha256:ddea35f9d67cd06660c40974caa14691623d4257c39d731193b3804e4cd7622c`.
Frontend image TLS المبني منf574، مع تطابق الواجهة معdc079:
`sha256:023b587039ffbee3518bc639daed16a1ac0d950f807e2dbd6b88c8de36670cbd`.
Windows Node26.7.0/npm11.19.0، TS6.0.3/Vitest4.1.11/Playwright1.62.1.
لا Dependency تغيير؛ قيود Python والصور الأساسية ليست Freeze أبدي لكل إصدار
Patch، لذلك سجّل resolved versions/image IDs عند إعادة بناء لاحقة.

أوامر Full/Static من جذر Checkout النظيف؛ لا تشغل pytest على نفس Test DB
متزامناً، وخصص مالكاً واحداً لـnpm ci في دليل الواجهة:

```powershell
$vf = @('-p','xmansx-parent-release-clean-verification','-f','docker-compose.parent-verification.yml','-f','docker-compose.parent-release-verification.yml')
docker compose @vf up -d postgres redis
docker compose @vf build tests
docker compose @vf run --rm --no-deps -e GENERATED_DOCUMENTS_ROOT=/tmp/parent-verification/release-clean-full-private tests pytest --create-db --reuse-db -q -rs -o cache_dir=/tmp/parent-verification/pytest-cache
docker compose @vf run --rm --no-deps tests python manage.py check
docker compose @vf run --rm --no-deps tests python manage.py makemigrations --check --dry-run
New-Item -ItemType Directory -Force tmp | Out-Null
$evidenceRoot = (Resolve-Path tmp).Path
docker compose @vf run --rm --no-deps --volume "${evidenceRoot}:/output" tests python manage.py spectacular --file /output/release-schema.json --format openapi-json --validate
docker compose @vf run --rm --no-deps tests python -c "import subprocess,sys; subprocess.run([sys.executable,'-m','pip','install','ruff==0.16.3'],check=True); subprocess.run([sys.executable,'-m','ruff','check','--no-cache','.', '/workspace/scripts'],check=True)"
Push-Location frontend
npm ci
npm run test
npm run typecheck
npx --no-install tsc --ignoreConfig --noEmit --strict --noUnusedLocals --noUnusedParameters --skipLibCheck --module ESNext --moduleResolution bundler --target ES2023 --lib ES2023,DOM,DOM.Iterable --types node --verbatimModuleSyntax --allowImportingTsExtensions --moduleDetection force playwright.parent.config.ts e2e/parent-portal.spec.ts
npm run lint
npm run build
Pop-Location
git diff --check
git status --porcelain=v1
```

HTTPS Seed/Runtime/Browser/DR commands، حدود المفاتيح، إغلاق التسجيل، وإعداد
COMPOSE_PROJECT_NAME في Node helper موجودة في Runbook Staging المتتبع.
لا يشترط الإصدار ملف Blueprint أو Source غير متتبع. الأدلة التنفيذية المحلية
في `tmp/release-clean-full-backend.log`, `release-clean-schema.log`,
`clean-frontend-*-*.log`, `clean-staging-*.log` في Checkout النظيف؛ لا تثبت في Git.

OpenAPI الناتج55 Parent/staff-parent/recovery paths و61 operations، منها9/10
جديدة للاستعادة. لا تشخيص جديد لهذه الواجهات؛ Legacy15 warnings و520 diagnostics
(97 unique) خارجها؛ Validation exit0 **لا يعني أن Schema كله نظيف**.
تحذيرات محفوظة: HarfBuzz-Subset في WeasyPrint، glob dev dependency deprecated
وقت تثبيت سابق، وNode LocalStorage experimental في Vitest. فحص Ruff الأخير
أظهر أيضاً تحذير pip root في حاوية اختبار مؤقتة؛ خدمات Staging تعملUID65534.
رحلة المتصفح سجلت تعارضNO_COLOR/FORCE_COLOR غير المسبب للفشل. لا Test skip؛
npm audit أثناء npm ci الحصري أبلغ0 vulnerabilities؛ لم يعد فحصاً مستقلاً لاحقاً.

## 12. التغييرات المتزامنة وأعمال المستخدم

الفرع الأصلي `feature/parent-portal-20261008` بقي عندd8؛ بدأ هذا التنفيذ مع38
مساراً متسخاً، ثم52، ثم56 في جرد لاحق، وليس16 القديمة فقط. العمل جارٍ لدى المستخدم
بالتزامن؛ لا ندعي ثبات المحتوى بين لقطتين. لم نعدل أو نحذف أو نستبدل أو Stage
أي ملف في Checkout الأصلي، ولم نوقف خدمات Capacity التابعة له.

عمل الإصدار في
`C:\Users\manso\Desktop\projects\xmansx-parent-release-20261008` على فرع
`feature/parent-recovery-staging-20261008` مشتق منd8، والاختبارات في
`C:\Users\manso\Desktop\projects\xmansx-parent-release-clean-20261008`.
المواد والمفاتيح والـScreenshots/Trace/logs والـnode_modules متجاهلة؛ لا تثبت.

الدمج المستقبلي يحتاج تصريحاً منفصلاً ومراجعة تعارضات settings/base.py،
Docker/Redis/cache/client/queryClient/polling والتغييرات الأخرى الجارية، ثم
Regression كامل على SHA الناتج. لا Cherry-pick أو دمج تلقائي في هذه المهمة.
جرد56 مساراً في Checkout الأصلي؛ لقطة حالة أسماء فقط، لم تُنقل محتوياتها:

```text
.env.example
backend/.dockerignore
backend/common/cache.py
backend/common/health.py
backend/config/database.py
backend/config/gunicorn.conf.py
backend/config/settings/base.py
backend/config/settings/test.py
backend/documents/services/snapshots.py
backend/school_dashboard/cache.py
backend/school_dashboard/selectors/reports.py
backend/student_warnings/api/views.py
backend/tests/test_documents.py
backend/tests/test_performance_cache.py
backend/tests/test_scalable_blueprint.py
backend/tests/test_scaling_config.py
backend/tests/test_school_reports.py
docs/CAPACITY_BASELINE.md
docs/GENERATED_DOCUMENTS.md
docs/LOAD_TESTING.md
docs/SCALABLE_PRODUCTION_CUTOVER.md
frontend/Dockerfile
frontend/infra-nginx.conf
frontend/src/api/client.test.ts
frontend/src/api/client.ts
frontend/src/app/polling.test.ts
frontend/src/app/polling.ts
frontend/src/app/queryClient.ts
frontend/src/features/attendance/SectionQrPage.tsx
frontend/src/features/attendance/attendance.test.tsx
frontend/src/features/devices/DeviceRosterSyncPage.tsx
frontend/src/features/documents/StudentDocumentsTab.tsx
frontend/src/features/documents/api.ts
frontend/src/features/documents/documents.test.tsx
frontend/src/features/reports/ReportsPage.tsx
frontend/src/features/reports/api.ts
frontend/src/features/settings/hooks.ts
frontend/src/features/sms/AbsenceMessagesPage.tsx
frontend/src/features/staff/StaffImportWizard.tsx
frontend/src/features/students/ImportWizard.tsx
frontend/src/features/students/InactiveStudentsPage.tsx
frontend/src/styles/index.css
render.scalable.yaml
render.yaml
backend/common/throttling.py
backend/config/redis.py
backend/tests/test_pressure_limits.py
docker-compose.capacity.yml
docs/CAPACITY_HARDENING_2026_10_08.md
docs/PRINTING_AUDIT_REPORT.md
frontend/src/app/queryClient.test.ts
frontend/src/features/reports/reports-print.test.tsx
frontend/src/hooks/usePrintShortcut.ts
loadtests/capacity.py
loadtests/measure_capacity.ps1
loadtests/proxy_probe.py
```

## 13. الـCommits المحلية وجرد الملفات

Starting SHA: `d8f8de6d4365e518cff269d438c25715c31a4a7e`.
Code commit: `72cedc1cbd424294d5c21d42977adff1ce7803ea`،49 ملفاً
(23 معدلاً و26 جديداً)،6589 insertions/126 deletions، دون تغيير Dependency/Lock.
فُحصت هوية Git المحلية قبل التثبيت، والفرق والملفات المتجاهلة والأسرار المحتملة.
Commit إصلاح التخزين/Strict tooling: `f5747a0a24cd67252bec5b71fb0e2b7bc408b6a0`،
سبعة ملفات موجودة فقط،141 insertions/39 deletions. لا فرق في `backend/` أو
`frontend/` بينه وبين72. أُعيدت نسخة Checkout النظيفة إليه للتحقق السابق.
Commit تصحيح Storage alias: `1e2c9839633b1c647de1df2f82163e78541d5bf7`،
سكربتان فقط،10 insertions/2 deletions. لا فرق Backend/Frontend/E2E أو Overlay/
Infra عنf574؛ نتائج pytest/Vitest السابقة تخص Blobs التطبيق المتطابقة في1e2،
وليست ادعاءً بإعادتها بعد تعديل السكربتين وحدهما. Runtime/DR/Browser
نجحت من1e2 النظيف، وStrict Ruff0.16.3 على Backend وكل Scripts نجح في7.9927s
wall شاملاً تثبيت الأداة في الحاوية المؤقتة.
Commit إغلاق إنشاء المدارس الذاتي في Staging:
`dc079b7c102dab0c84c5b4f77c30a2f90d91fd36`، أربعة ملفات موجودة فقط،
23 insertions/3 deletions. أعيد Full Backend والفحوص وHTTPS وRuntime وDR
من هذا الـCheckout النظيف؛ هذا **SHA الكود النهائي المختبر**. شجرة frontend
كاملة متطابقة معf574. لم تُنقل إعدادات Capacity أو ملفات المستخدم غير المثبتة.
ثم يثبت هذا التقرير وحده في Commit توثيق؛
لا يمكن للتقرير تضمين SHA الـCommit الذي يحتويه ذاتياً. يطبع التسليم النهائي
Final HEAD، ويثبت التطابق في Runtime source للنسخة النظيفة.

جرد المصدر الكامل مقابلd8:50 ملفاً عند إضافة التقرير (23 معدلاً و27 جديداً).
الملفات التالية هي النطاق الخاص بهذه المهمة فقط:

```text
.gitignore
backend/accounts/admin.py
backend/config/settings/base.py
backend/config/settings/parent_staging.py
backend/config/urls.py
backend/operations/error_tracking.py
backend/parents/access.py
backend/parents/api.py
backend/parents/contact_api.py
backend/parents/management/commands/seed_parent_e2e.py
backend/parents/management/commands/seed_parent_staging.py
backend/parents/migrations/0006_review_only_account_recovery.py
backend/parents/models.py
backend/parents/purge_integration.py
backend/parents/recovery_api.py
backend/parents/recovery_models.py
backend/parents/recovery_purge.py
backend/parents/recovery_services.py
backend/parents/recovery_urls.py
backend/parents/request_api.py
backend/parents/services.py
backend/platform_team/services.py
backend/students/api/lifecycle_views.py
backend/students/services/purge.py
backend/students/tasks.py
backend/subscriptions/services/school_purge.py
backend/tests/test_parent_independent_migrations.py
backend/tests/test_parent_recovery_activation_races.py
backend/tests/test_parent_recovery_foundation_security.py
backend/tests/test_parent_recovery_independent_security.py
backend/tests/test_parent_recovery_schema.py
backend/tests/test_parent_release_performance.py
backend/tests/test_parent_release_read_scopes.py
docker-compose.parent-release-verification.yml
docker-compose.parent-staging.yml
docs/PARENT_ACCOUNT_RECOVERY_ARCHITECTURE.md
docs/PARENT_ACCOUNT_RECOVERY_OPERATIONS.md
docs/PARENT_PORTAL_OPERATIONS.md
docs/PARENT_PORTAL_RELEASE_READINESS_REPORT.md
docs/PARENT_PORTAL_STAGING_READINESS.md
frontend/e2e/parent-portal.spec.ts
frontend/playwright.parent.config.ts
infra/parent-staging-nginx.conf
scripts/generate_e2e_fixtures.py
scripts/parent_staging_acceptance.py
scripts/parent_staging_fixture_check.py
scripts/parent_staging_materials.py
scripts/parent_staging_restore_drill.py
scripts/parent_staging_schema_refresh.py
scripts/parent_staging_storage.py
```

## 14. المشكلات التي وجدت وأصلحت

بالإضافة إلى الثغرات المثبتة في القسم5: أصلح UUID FK guard الخاص بالجداول
الجديدة دون تغيير حارس BigInt القديم، وDependencies Fresh install، ومدخل
OpenAPI فارغ/OperationId جديد متصادم. لم يُعدل عشرات Legacy APIs لإخفاء التشخيصات.

تشخيص التجهيز محفوظ: أول قبول HTTPS5 pass/1 fail لأن Service worker رفض
شهادة محلية ذاتية؛ صُححت ثقة الشهادة المحددة دون Ignore عام. محاولة أخرى5/1
لأن اختبار تبديل الحساب استخدم العلاقة التي علقها اختبار سابق؛ أضيف Fixture
مستقل ولم تُعد العلاقة المسحوبة. DR script احتاج مقارنة Whole row بدلاً من
افتراض حقلid في كل جدول (Django Session مختلف). npm ci متزامن بين وكيلين
حذف executable ففشل Startup قبل أي اختبار؛ أعيد حصرياً ونجح كامل التحقق.

فحص Ruff الأول من جذر المشروع لم يطبق Backend config على scripts؛ الفحص النظيف
الأوسع كشف9 ملاحظات import/UTC/line length/temporary private roots. أصلحت
السكربتات والمسارات الدائمة في Overlay، مع قراءة إعدادات Django الفعلية وإلزام
Mount مستقل والتحقق من كل المسارات قبل Chown. لا noqa/ignore جديد لإخفائها.
هذه الأدلة التشخيصية ليست نتائج PASS، وتبقى في Logs المتجاهلة.

أول DR بعد تغيير Mounts إلىvar/lib توقف قبل إنشاء Backup أو قاعدة جديدة:
سكربتا Acceptance/DR افترضا `settings.BACKUP_STORAGE_LOCATION`، بينما التطبيق
يعرّف الموقع عبر `storages['backups']`. هذا خلل فعلي في السكربتين الجديدين،
وليس بيانات مفقودة أو خللاً في Backup service. التصحيح يقرأ FileSystemStorage
الفعلي ويثبت نوعه وموقعه المحلي، مع إبقاء شروط Mount/Path/Permissions؛ إعادة
Runtime/DR المصححة نجحت من Checkout1e2 النظيف، ثم نجحت الرحلات الست. Probe
فعلي Read-only نجح قبل القبول. تحققت قبل
الفشل سلامة ستة الملفات السابقة بعد Remount، والمفاتيح
والشهادة والـVolume identities كما هي؛ لا استبدال أو نقل بيانات.

آخر فحص إعدادات كشف فرقاً بين ParentRegistrationConfig وإتاحة إنشاء مدرسة
ذاتياً. الأول مغلق، والثاني ورث True من Base. يضبط التصحيح **علم المنصة
الموجود** False في Overlay الصناعي، ويجعل Profile/Runtime يرفضان إتاحته؛
لا تعديل Base/Production أو قواعد تسجيل المدرسة القائمة. إثبات HTTPS فعلي
بـCSRF صالح أعاد503 SELF_REGISTRATION_UNAVAILABLE قبل Serializer، مع ثبات
School/User/Session counts في حالتي القبول المؤقت والإغلاق. أول Probe غير متتبع
افترض خطأً `error.code` متداخلاً؛ العقد القديم `body.code` مسطح. صحح Probe
فقط وأعيد بنجاح؛ لم يتغير API أو اختبار المنتج، وحفظ سجل الفشل التشخيصي.
هذه مطابقة شرط البيئة المقيدة، وليست فتح ميزة جديدة.

## 15. المخاطر والعوائق والمتطلبات التشغيلية

- **عائق ملزم للإطلاق العام:** لا سياسة إثبات/استعادة معتمدة أو تنفيذ نهائي آمن.
  يجب إغلاق متطلبات الوثائق، IAM مستقل، Original-owner binding، New-number
  verification دون Recovery SMS، Personal enrollment وإبطال Sessions/Tokens
  واختبارات النجاح والتزامن قبل فتح التسجيل العام.
- لا External staging deployment أو SMS receipt أو Production load أو Production
  DR مثبت. تجهيز محلي لا يغطي Domain/HTTPS الحقيقي ومفاتيح المزود وموارد التشغيل.
- خطة SMS لاحقة فقط: مدرسة صناعية، رقم واحد مصرح، مزود Dreams أوMsegat مصرح،
  رسالة تفعيل واحدة وغياب واحدة، فحص Provider log والReceipt ومنع التكرار؛ أوقف
  عند UNKNOWN ولا تعاود بلا مراجعة المزود. الموافقة يجب أن تحدد الرقم والمزود
  والنطاق؛ لا اتصال خارجي نفذ هنا. Runbook يحدد الأدوار والحدود.
- مراجعة Privacy/Error logs قبل بيئة عامة: Access logs المحلية مختصرة بلا URI،
  لكن Error log الموروث في Proxy قد يتضمن URI عند الخطأ؛ لا ضمان Scrubbing لكل
  stdout/مسار خطأ. Sentry scrubber الحالي ليس بديلاً لسياسة سجلات عامة معتمدة.
- احتفاظ/حذف مركزي للإثبات مستقبلاً، Distinct-human IAM، مراقبة Grant/Denial/
  Conflict/Worker/Beat/Redis، Private backup+keys، وخطة Rotation منسقة لكل HMAC
  Parent hashes. لا تبديل مفاتيح قائمة بهذه المهمة.
- Legacy schema diagnostics ومعمارية Imports المباشرة المحدودة وبعض تاريخ
  السنوات الملتبس تبقى ديناً موثقاً؛ عدم المعرفة لا يتحول إلى يوم كامل.
- أوقات القياس لا تثبت السرعة المطلوبة في الإنتاج. قبل موارد عامة نفذ قياساً
  مستقلاً هادئاً وHTTP/network/concurrency أطول، وسجل CPU/RSS/locks/Redis.

## 16. القرار النهائي

الحكم العام: **PASS WITH ISSUES**.

| قرار الجاهزية | الحكم | أساس القرار وحدوده |
| --- | --- | --- |
| A. Local Technical Readiness | **PASS** | Full Regression والفحوص نجحت على إصدار محلي مثبت؛ RLS وPDF والتزامن والتخزين اختبرت فعلياً، ولا مشكلة عالية أو حرجة مثبتة بقيت دون معالجة في هذا النطاق |
| B. Restricted Staging Readiness | **PASS** | Staging محلي HTTPS مقيد ببيانات صناعية ودور قاعدة مقيد وتخزين خاص؛ ست رحلات ناجحة، والتسجيلان مغلقان افتراضياً وبعد القبول؛ لم يحدث نشر Staging خارجي |
| C. Public Production Readiness | **FAIL / BLOCKED** | لا سياسة إثبات معتمدة، ولا تحقق من صاحب الحساب الأصلي والرقم الجديد أو IAM مستقل معتمد أو إنشاء اعتماد شخصي وتنفيذ استعادة وإبطال جلسات/رموز؛ تبقى الاستعادة مغلقة والإطلاق العام محجوباً |

الإصدار قابل لإعادة الاختبار محلياً ويمكن نقله لاحقاً إلى Staging خارجي مقيد
بعد اعتماد بيئته وصلاحياته. فتح التسجيل العام يحتاج إغلاق عوائق الاستعادة
والضوابط التشغيلية الملزمة، لا موافقة شكلية أو حساباً جديداً أو Reset إدارياً.
لا Push أو Merge أو نشر إنتاجي أو تغيير DNS أو SMS حقيقي ضمن هذا التسليم.
