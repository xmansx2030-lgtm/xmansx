# النشر على Render

يعرّف `render.yaml` بنية الإنتاج الكاملة في Frankfurt:

- `xmansx-web`: واجهة Nginx العامة، وتحوّل `/api/` إلى الشبكة الخاصة.
- `xmansx-core`: Django/Gunicorn مع Celery worker وCelery beat في نسخة واحدة.
- `xmansx-postgres`: PostgreSQL 18 مُدار وغير مكشوف للعامة.
- `xmansx-cache`: Render Key Value دائم وغير مكشوف للعامة.
- قرص 5 GB عند `/app/storage` للمرفقات والمستندات والنسخ الاحتياطية المحلية.

## لماذا تعمل عمليات الخلفية داخل خدمة النواة؟

قرص Render الدائم لا يمكن مشاركته بين خدمتين. بعض مهام Celery تقرأ ملفات رفعها
Django، لذلك تشغيل الويب والعامل والمجدول داخل الخدمة ذاتها هو الضمان الصحيح
لهذه البنية أحادية النسخة. التوسع الأفقي لاحقًا يتطلب تفعيل R2 للتخزين المشترك،
وفصل العامل والمجدول إلى خدمات مستقلة.

## إنشاء Blueprint

1. اربط المستودع `xmansx2030-lgtm/xmansx` والفرع `main` في Render Blueprints.
2. استخدم ملف Blueprint الافتراضي `render.yaml`.
3. أدخل `INITIAL_ADMIN_MOBILE` و`INITIAL_ADMIN_PASSWORD` عند الإنشاء فقط.
4. راجع التكلفة ثم طبّق Blueprint. الأسرار التطبيقية الأخرى يولدها Render.
5. انتظر نجاح فحوص GitHub والبناء والترحيلات، ثم إنشاء المشرف وأول نسخة قاعدة بيانات.

عنوان المنصة الافتراضي هو `https://xmansx-web.onrender.com`. إذا غُيّر اسم الخدمة
أو أضيف نطاق خاص، يجب تحديث `DJANGO_ALLOWED_HOSTS` و
`DJANGO_CSRF_TRUSTED_ORIGINS` ثم إعادة النشر.

## التحقق بعد النشر

```text
GET https://xmansx-web.onrender.com/api/v1/health/
GET https://xmansx-web.onrender.com/api/v1/readiness/
```

يجب أن يعيدا HTTP 200. بعد ذلك يسجل مشرف المنصة الدخول برقم الجوال وكلمة المرور
اللذين أُدخلا وقت إنشاء Blueprint.

## النسخ الاحتياطي وحدود الاستعادة

التهيئة الافتراضية تشغّل نسخة قاعدة بيانات محلية يومية على القرص الدائم، بينما
ينشئ Render لقطات دورية للقرص. هذه بداية تشغيلية وليست نسخة خارج مزود الخدمة.
للتعافي من تعطل مزود كامل يجب إنشاء حاويتي R2 منفصلتين (ملفات خاصة ونسخ قاعدة
البيانات)، ثم ضبط متغيرات R2 وتفعيل `BACKUP_REMOTE_ENABLED` و
`BACKUP_REQUIRE_REMOTE` وفق `docs/BACKUP_POLICY.md`.
