# ADR-007: PWA Online-First بدون Offline Attendance

- **الحالة:** مقبول — 2026-08-18
- **السياق:** Offline Attendance كامل يتطلب مزامنة ثنائية الاتجاه وحل تعارضات (فصل حُضّر Offline وOnline معًا) — تعقيد لا يناسب MVP.
- **القرار:** PWA قابلة للتثبيت: Manifest + Icons + Service Worker (Workbox) مع App Shell caching وصفحة Offline وتدفق تحديث إصدار واضح. العمليات الكتابية تتطلب اتصالًا؛ الانقطاع المؤقت يُعالج بإعادة المحاولة (TanStack Query) وعدم فقدان حالة النموذج في الذاكرة.
- **التبعات:** تجربة تثبيت أصلية على Android/iOS/Desktop دون مخاطر تعارض البيانات. Offline Attendance مرشح لإصدار لاحق فوق قيد Unique الموجود أصلًا (يمنع ازدواج المزامنة).
