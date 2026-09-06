# تقرير فحص خادم Hetzner - 2026-08-21

## النطاق

- المشروع: Hetzner Project `15433668`
- الخادم: `school-reports-prod`
- الموقع: `https://tawtheeq-ksa.com/`
- طريقة الفحص: لوحة Hetzner في Chrome، اختبارات اتصال خارجية، ومراجعة ملفات النشر المحلية.
- لم يتم تنفيذ تغييرات إنتاجية مباشرة لأن تعديل الجدار الناري أو الشبكات قد يقطع الوصول ويتطلب تأكيد عنوان إدارة آمن.

## الملخص التنفيذي

الوضع العام جيد كبنية إنتاج أولية لخادم منفرد خلف Cloudflare. الخادم يعمل، النسخ الاحتياطية اليومية مفعلة، منافذ الويب المباشرة على IP الخادم غير مكشوفة، والتطبيق المحلي يحتوي إعدادات إنتاج أمنية قوية.

أهم مخاطرة حالية هي أن منفذ SSH `22/TCP` مفتوح من الإنترنت كله عبر `Any IPv4` و`Any IPv6`. هذا يجب تضييقه فورا إلى عنوان إدارة ثابت أو VPN/Bastion. كما أن البنية تعتمد على خادم واحد بدون Load Balancer أو Floating IP أو Private Network، وهذا مقبول كبداية لكنه ليس معيارا عاليا للتوافر.

## حالة Hetzner

### الموارد

- Servers: خادم واحد.
- Load Balancers: لا يوجد.
- Primary IPs: عنوانان، IPv4 وIPv6.
- Floating IPs: لا يوجد.
- Volumes: لا يوجد.
- Networks: لا يوجد.
- Firewalls: 3 في المشروع، والمطبق فعليا على الخادم هو `school-reports-prod`.
- Storage Box: واحدة.
- DNS Zones داخل Hetzner: لا يوجد.

### الخادم

- النوع: `CPX32`
- الاسم: `school-reports-prod`
- الحالة: `ON`
- vCPU: 4
- RAM: 8 GB
- Disk: 160 GB local
- المنطقة: Germany / Nuremberg / `eu-central`
- IPv4: `178.104.163.3`
- IPv6: `2a01:4f8:c2c:b::/64`
- السعر الظاهر: `41.99/mo`

### النسخ والتعافي

- Backups مفعلة.
- توجد 7 نسخ يومية متاحة بتاريخ 2026-08-14 إلى 2026-08-20 تقريبا.
- لا توجد Snapshots محفوظة.
- تمرين الاستعادة المحلي في `RESTORE_DRILL_RESULT.json` ناجح:
  - الحالة: `PASS`
  - استعادة إلى قاعدة معزولة.
  - تسجيل دخول مدير: `200`
  - رفض النسخ الفاسدة قبل الاستعادة: نعم.
  - رفض الاستعادة فوق قاعدة حالية أو غير فارغة: نعم.

## الجدار الناري والشبكة

### القواعد المطبقة

Firewall: `school-reports-prod`

- `22/TCP`: مفتوح من `Any IPv4` و`Any IPv6`.
- `80/TCP`: مقيد بعناوين Cloudflare.
- `443/TCP`: مقيد بعناوين Cloudflare.
- `443/UDP`: مقيد بعناوين Cloudflare.
- Outbound: كل الخروج مسموح.
- الجدار مطبق على الخادم الوحيد وحالته `Fully applied`.

### اختبارات خارجية

- `https://tawtheeq-ksa.com/` يعمل في Chrome عبر Cloudflare.
- `curl` الخارجي يتلقى Cloudflare Challenge `403`, وهذا متوقع عند حماية الطلبات الآلية.
- الاتصال المباشر بـ `178.104.163.3:80` فشل.
- الاتصال المباشر بـ `178.104.163.3:443` فشل.
- الاتصال المباشر بـ `178.104.163.3:22` نجح.

## مراجعة إعدادات التطبيق المحلية

### نقاط قوية

- `config.settings.production` يفرض `DEBUG=False`.
- الأسرار الإنتاجية إلزامية ولا توجد defaults صامتة.
- `ALLOWED_HOSTS` لا يسمح بـ `*`.
- مفاتيح Fernet وHMAC إلزامية ويتم رفض مفاتيح التطوير.
- إعدادات HTTPS وSecure Cookies وCSRF موجودة.
- CSP وSecurity headers معرفة في الإعدادات.
- PostgreSQL وRedis مستخدمان في الإنتاج.
- Rate limiting لتسجيل الدخول موجود.
- التخزين الخاص للمستندات منفصل عن media العامة.
- سياسة النسخ الاحتياطي موثقة في `docs/BACKUP_POLICY.md`.

### نقاط تحتاج تحقق إنتاجي

- التأكد أن متغيرات الإنتاج على الخادم تضبط:
  - `DJANGO_SECURE_SSL_REDIRECT=true`
  - `DJANGO_CSRF_TRUSTED_ORIGINS=https://tawtheeq-ksa.com`
  - `BACKUP_REMOTE_ENABLED=true`
  - `BACKUP_REQUIRE_REMOTE=true`
  - `BACKUP_ENVIRONMENT=production`
- التأكد أن النسخ لا تعتمد فقط على Docker volume أو نفس الخادم.
- التأكد من وجود مراقبة فعلية لـ `/api/v1/health/` و`/api/v1/readiness/`.
- التأكد من ضبط Sentry أو بديل مراقبة أخطاء بإشعارات إنتاجية.

## الأولويات

### عاجل جدا

1. تضييق SSH:
   - استبدال `Any IPv4/Any IPv6` بعنوان IP إداري ثابت فقط.
   - الأفضل: VPN أو Bastion أو Tailscale/Zero Trust.
   - تعطيل password login على الخادم، والسماح بمفاتيح SSH فقط.

2. أخذ Snapshot قبل أي تغيير كبير:
   - Snapshot باسم واضح مثل `pre-firewall-hardening-2026-08-21`.
   - حذفها بعد الاستقرار إذا لم تعد مطلوبة لتقليل التكلفة.

3. اختبار عدم تجاوز Cloudflare:
   - يجب أن تبقى `80/443` المباشرة إلى IP الخادم مغلقة كما هي.
   - منع أي vhost default يعرض التطبيق عند الوصول بالـ IP.

### مهم خلال أسبوع

1. اعتماد نسخ احتياطي مستقلة:
   - R2/S3 private bucket أو Storage Box منفصل بسياسة retention.
   - تفعيل `BACKUP_REQUIRE_REMOTE=true`.
   - اختبار restore شهري موثق.

2. مراقبة وتنبيهات:
   - Uptime خارجي.
   - readiness داخلي.
   - تنبيه CPU/RAM/Disk.
   - تنبيه فشل backup.
   - تنبيه انتهاء TLS أو تغير Cloudflare mode.

3. Reverse DNS:
   - IPv4 reverse DNS الحالي هو `static...your-server.de`.
   - يفضل ضبطه إلى اسم مناسب مثل `prod-1.tawtheeq-ksa.com` إذا ستستخدمه للتشغيل والمراقبة.

### تحسينات احترافية لاحقة

1. فصل قاعدة البيانات أو إضافة خطة HA:
   - Managed PostgreSQL أو خادم DB منفصل مع نسخ PITR.
   - يقلل أثر تعطل خادم التطبيق الواحد.

2. إضافة Floating IP أو Load Balancer عند الحاجة:
   - Floating IP يسهل استبدال الخادم.
   - Load Balancer مفيد عند وجود أكثر من backend.

3. Private Network:
   - عند فصل DB/Redis/Workers، يجب نقل الاتصالات الداخلية إلى شبكة خاصة.

4. Outbound Firewall:
   - للإنتاج عالي الحساسية، قيّد الخروج إلى الوجهات الضرورية فقط:
     Cloudflare/R2/S3، Sentry، تحديثات النظام، DNS، NTP، البريد أو بوابات الرسائل.

## الخلاصة

الخادم في حالة تشغيل جيدة ومحمية جزئيا خلف Cloudflare، وملفات التطبيق تظهر مستوى نضج جيد في الأمن والتعافي. التحسين الحاسم الآن هو إغلاق SSH العام وتأكيد أن النسخ الاحتياطية خارج الخادم ومختبرة. بعدها يمكن رفع الاعتمادية بإضافة مراقبة احترافية، خطة تعافي موثقة، وفصل مكونات البنية عند نمو الاستخدام.
