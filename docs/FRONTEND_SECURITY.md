# أمان الواجهة

## CSP والرؤوس

سياسة nginx الإنتاجية:

```text
default-src 'self'
script-src 'self'
style-src 'self'
img-src 'self' data:
connect-src 'self'
manifest-src 'self'
worker-src 'self'
object-src 'none'
base-uri 'self'
frame-ancestors 'none'
form-action 'self'
```

لا تستخدم `unsafe-inline` أو `unsafe-eval`. أزيلت inline styles الثابتة، وتستخدم
الواجهة React escaping ولا تستخدم `dangerouslySetInnerHTML`.

## المصادقة وحدود البيانات

- المصادقة Session Cookie فقط؛ لا JWT أو token في LocalStorage.
- كل كتابة تمر عبر CSRF bootstrap ثم `X-CSRFToken` وsame-origin credentials.
- backend هو مصدر RBAC وtenant/subscription enforcement. إخفاء الرابط مجرد UX.
- Platform Admin يوجه مباشرة إلى `/platform` ولا يحتاج active school. console
  المنصة يعرض SaaS metadata والأعداد فقط ولا يعرض قوائم الطلاب أو الملاحظات.
- عند school switch تلغى الطلبات الجارية وتمسح كل queries عدا `/me` قبل تثبيت
  المدرسة الجديدة، ما يمنع stale tenant flashes والـrace في A -> B -> A.

## التخزين المؤقت والأخطاء

- استجابات API تحمل `private, no-store, max-age=0`, `Pragma: no-cache` و`Expires: 0`.
- service worker لا يخزن API أو private downloads. login/logout/user switch تمسح
  caches القديمة أيضًا.
- أخطاء API تعرض code/message الآمنين؛ لا تعرض traceback أو raw exception.
- route chunks تحمل hashes وتحمّل lazy لكل feature، ويخدم nginx `index.html`
  و`sw.js` بلا تخزين دائم حتى لا تختلط نسخ النشر.

