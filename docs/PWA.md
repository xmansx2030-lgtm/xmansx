# PWA

## الهوية والتثبيت

يبني `vite-plugin-pwa` manifest عربيًا RTL باسم المنصة الحالي، `start_url=/`،
`scope=/`، و`display=standalone`. الأيقونات الفعلية متوفرة بمقاسات 192 و512
وmaskable 512 داخل `frontend/public/icons/`.

## سياسة Service Worker

التطبيق online-first ولا يقدم Offline Attendance:

| المورد | السياسة |
|---|---|
| ملفات build ذات hash | precache عبر Workbox |
| SPA navigation shell | static shell فقط |
| `/api/**` | `NetworkOnly` ولا يكتب في Cache Storage |
| المرفقات والمستندات الخاصة | network فقط، ليست ضمن precache |
| عمليات الكتابة | لا background sync ولا optimistic success دائم |

عند بدء التطبيق، `purgeSensitiveBrowserCaches` يحذف أي API/media/private request
بقي من service worker قديم. login وlogout وتبديل المدرسة يلغون استعلامات TanStack
الحالية ويمسحون البيانات الحساسة قبل الانتقال إلى هوية أو مستأجر آخر.

## الانقطاع والتحديث

- يعرض التطبيق حالة offline واضحة. فشل إرسال الحضور لا يظهر نجاحًا ولا يخزن
  العملية محليًا.
- بعد logout لا يمكن فتح أسماء الطلاب أو شاشات الحضور من cache عند قطع الشبكة.
- `registerType=prompt`: تنزيل نسخة جديدة لا يفرض reload أثناء إدخال حضور. يظهر
  «يتوفر تحديث جديد» ويختار المستخدم «تحديث الآن».
- عند الاختيار يرسل التطبيق `SKIP_WAITING` للنسخة المنتظرة ثم يعيد التحميل بعد
  `controlling`. اختبار الإصدار يثبت انتقال `phase17-v1` إلى `phase17-v2` مع
  بقاء جلسة Platform Admin ودون white screen أو stale chunk.

## تحقق الإنتاج

Playwright يختبر manifest والأيقونات وregistration وSPA fallback وغياب API من
Cache Storage وlogout offline وتبديل المدرسة السريع. الاختبار يعمل ضد nginx build
وليس Vite dev server.

