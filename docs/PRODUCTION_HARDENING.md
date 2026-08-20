# تقوية بيئة الإنتاج

## إعدادات التشغيل

الإنتاج يستخدم `config.settings.production` ويفرض `DEBUG=False`. يبدأ التطبيق فقط
عند توفير القيم التالية صراحة:

```text
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_HOST
REDIS_URL
FIELD_ENCRYPTION_KEYS
NATIONAL_ID_HMAC_KEY
```

يرفض startup المفتاح القصير أو الافتراضي، `ALLOWED_HOSTS=*`، host يحوي scheme أو
path، مفتاح Fernet التطويري، ومفتاح HMAC الضعيف. لا تطبع رسائل التحقق قيمة أي سر.

## HTTPS وHSTS

- `SECURE_SSL_REDIRECT=True` افتراضيًا مع
  `SECURE_PROXY_SSL_HEADER=(HTTP_X_FORWARDED_PROTO, https)` خلف reverse proxy.
- HSTS يبدأ بـ30 يومًا مع `includeSubDomains`; يبقى `preload=False` حتى اعتماد
  النطاقات واستكمال فترة المراقبة. لا يفعل preload أثناء local verification.
- stack المحلية الإنتاجية وحدها تضبط redirect إلى `False` وتقبل origins محلية
  صريحة حتى يعمل HTTP على loopback. هذا الاستثناء غير صالح لنطاق خارجي.

## الجلسات وCSRF

- `SESSION_COOKIE_SECURE=True`, `HttpOnly=True`, `SameSite=Lax`.
- `CSRF_COOKIE_SECURE=True`, `SameSite=Lax`. الكعكة ليست HttpOnly لأن SPA تقرأها
  وترسلها في `X-CSRFToken`; الخادم يبقى جهة التحقق.
- العمر 12 ساعة، يتجدد مع النشاط (`SESSION_SAVE_EVERY_REQUEST=True`) ولا ينتهي
  بمجرد إغلاق المتصفح. يمكن تغييره عبر `DJANGO_SESSION_COOKIE_AGE` الموجب.
- logout يمسح الجلسة خادميًا. تغيير كلمة المرور يدور session key ويحفظ الجلسة
  الحالية فقط؛ بقية الجلسات تفشل عند مقارنة auth hash الجديد.

## الرؤوس والتخزين والسجلات

- nginx يفرض CSP وHSTS-compatible headers على SPA، وDjango يضيف no-store لكل
  `/api/**` إضافة إلى Permissions Policy وCOOP/CORP.
- المرفقات والمستندات في volumes خاصة مشتركة بين backend وworker، وليست static
  أو media عامة. مفاتيح التخزين تولد من school id وUUID ولا تستخدم اسم المستخدم.
- السجلات JSON تحمل request id والطريق والحالة والمدة وschool id الآمن. يمنع
  تسجيل كلمات المرور والهوية الصريحة وAuthorization والمفاتيح ومحتوى الملفات.
- `/api/v1/health/` للحيوية و`/api/v1/readiness/` لفحص PostgreSQL وRedis.

## بوابة محلية إنتاجية

`docker-compose.production.yml` overlay فوق compose الأساسي ويشغل gunicorn،
worker، beat، PostgreSQL، Redis، وnginx production build. المتغيرات الحساسة
مطلوبة من shell ولا توجد لها قيم سرية ثابتة في الملف.

