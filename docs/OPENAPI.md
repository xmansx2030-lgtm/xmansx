# OpenAPI — نفذ في بداية المرحلة 5 (سداد دين المرحلتين 3–4)

## التنفيذ

- **drf-spectacular 0.30** (متوافق فعليًا مع Django 5.2 + DRF 3.16 — مثبت بالتشغيل).
- `GET /api/v1/schema/` (OpenAPI 3) و`GET /api/v1/docs/` (Swagger UI).
- **الحماية:** ‏`SERVE_PERMISSIONS = IsAdminUser` افتراضيًا (الإنتاج) — التطوير يفتحها (local.py). الـ wrappers في config/urls تقرأ الإعداد **وقت الطلب** (تفادي التقاط import-time) — مغطى باختبارات (anonymous → 403 افتراضيًا).
- التغطية: كل الـ 48 مسارًا الحالية (Auth/Session/Settings/Academics/Students/Imports/Staff/Invitations) تظهر في الـ Schema — مثبت باختبار يتحقق من المسارات العشرة الأساسية.
- **CI:** خطوة `spectacular --file --validate` — أي كسر للتوليد يفشل الـ build.

## حدود معروفة (موثقة بصدق)

التوليد يصدر 48 تحذير «unable to guess serializer» — كل الـ views الحالية APIView يدوية بلا `serializer_class` للاستجابات، فمخططات الاستجابة generic. غير حرج (المسارات والـ methods والـ request bodies حيث توجد serializers موثقة).

## قرار Types للواجهة (البند 3)

- **الآن:** الأنواع اليدوية في `frontend/src/types` و`features/*/api.ts` تبقى المصدر — مطابقة ومغطاة باختبارات تكامل E2E حقيقية؛ توليد types من schema فقير الاستجابات سينتج `unknown` في كل مكان ويضر أكثر مما ينفع.
- **القاعدة الملزمة من المرحلة 6:** أي API جديد يعرف **Response Serializers** كاملة (serializer-first)، وعندها يفعل توليد TypeScript (openapi-typescript) للمسارات الجديدة تدريجيًا، مع فحص CI يمنع تقادم الـ schema بصمت.
- ترقية الـ views القائمة إلى serializers مسجلة كدين تقني تدريجي (ليست refactor دفعة واحدة).
