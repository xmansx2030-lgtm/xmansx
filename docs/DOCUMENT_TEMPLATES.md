# قوالب المستندات (المرحلة 12)

القوالب في `backend/documents/templates/documents/` ومسجلة في
`documents/templates_registry.py` — لا HTML داخل الـviews.

## السجل

| المفتاح | الإصدار | النوع | القالب |
|---|---|---|---|
| `warning_level_1` | v1 | الإنذار الأول | `warning.html` |
| `warning_level_1` | v2 | الإنذار الأول (تاريخي) | `warning_v2.html` |
| `warning_level_1` | v3 | الإنذار الأول | `warning_v3.html` |
| `warning_level_2` | v1 | الإنذار الثاني | `warning.html` |
| `warning_level_2` | v2 | الإنذار الثاني (تاريخي) | `warning_v2.html` |
| `warning_level_2` | v3 | الإنذار الثاني | `warning_v3.html` |
| `warning_level_3` | v1 | الإنذار الثالث | `warning.html` |
| `warning_level_3` | v2 | الإنذار الثالث (تاريخي) | `warning_v2.html` |
| `warning_level_3` | v3 | الإنذار الثالث | `warning_v3.html` |
| `attendance_commitment` | v1 | تعهد الالتزام بالحضور | `commitment.html` |
| `attendance_commitment` | v2 | تعهد الالتزام بالحضور | `commitment_v2.html` |
| `absence_detail_report` | v1 | كشف تفصيلي للغياب | `absence_report.html` |
| `absence_detail_report` | v2 | كشف تفصيلي للغياب | `absence_report_v2.html` |
| `morning_late_report` | v1 | كشف التأخر الصباحي | `morning_late_report.html` |
| `morning_late_report` | v2 | كشف التأخر الصباحي | `morning_late_report_v2.html` |
| `student_attendance_report` | v1 | تقرير مواظبة الطالب | `attendance_report.html` |
| `student_attendance_report` | v2 | تقرير مواظبة الطالب | `attendance_report_v2.html` |

## الإصدارات

كل مستند يخزن `template_key` و`template_version` وقت إصداره. تصميم v1 والقالب
التاريخي v2 للإنذارات محفوظان دون تعديل؛ أحدث تصميم للإنذارات v3، ولأنواع
التعهد والكشوف v2. تبقى الإصدارات القديمة متاحة لإعادة الإصدار التاريخي. إصدار
غير موجود في السجل ⇒ `DOCUMENT_TEMPLATE_VERSION_UNAVAILABLE` (409)، ونوع بلا قالب
⇒ `DOCUMENT_TEMPLATE_NOT_FOUND` (404).

## سياسة النماذج الرسمية

كل قوالب السجل `source_type = INTERNAL` — صياغة داخلية للمنصة. **ممنوع** وصف أي
قالب بأنه «نموذج وزاري معتمد» ما لم يُسجَّل مصدره داخل النظام:

```
source_type      = OFFICIAL
source_reference = مرجع التعميم/الدليل
source_version   = إصداره
effective_date   = تاريخ سريانه
```

النماذج الرسمية تتغير، فاعتمادها يكون بمدخل جديد يحمل مرجعه وإصداره — لا إعادة
تسمية لقالب داخلي ولا تثبيت نموذج قديم في الكود. لا تستخدم التصاميم الجديدة
شعارًا أو أصولًا خارجية، ولا تدعي اعتمادًا وزاريًا. الإصدارات التاريخية تبقى
لإعادة الطباعة كما صدرت ولا يُستدل من شكلها على الاعتماد.

**ولا يُعدَّل نموذج رسمي لإضافة تفاصيل**: إذا لم يحتوِ التعهد جدول تواريخ، فالتفصيل
يصدر ككشف مستقل يُرفق — لا جدول يُحشر داخله مع ادعاء المطابقة.

## البنية والتنسيق

`base.html` محفوظ للإصدارات التاريخية. `base_v2.html` يوفر للتصاميم الجديدة:

- `<html lang="ar" dir="rtl">` و`@page { size: A4 }` وهوامش وترقيم «صفحة N من M».
- خط `Noto Naskh Arabic` من النظام (حزمة `fonts-noto-core`, رخصة OFL) —
  **لا ملفات خطوط داخل المستودع**. التشكيل والاتجاه عبر Pango/HarfBuzz/FriBidi.
- ترويسة مدرسية (الاسم/المدينة/الرقم الوزاري) وجدول بيانات الطالب.
- أماكن توقيع: الطالب، ولي الأمر، مدير المدرسة. يؤخذ الاسم الرسمي من إعدادات
  المدرسة، وعند تركه فارغاً يستخدم اسم صاحب دور مدير المدرسة ذي العضوية الفعالة
  (لا اسم المستخدم الحالي). لا توقيع رقمي ولا ختم في MVP.
- جداول الكشوف: `thead { display: table-header-group }` لتكرار رؤوس الأعمدة على كل
  صفحة، و`tr { page-break-inside: avoid }` لمنع قطع الصفوف. مثبت بمستند 120 صفًا
  متعدد الصفحات.

## الأمان

التهريب التلقائي في قوالب Django مفعّل: أي ملاحظة أو اسم يحوي `<script>` يخرج كنص
(‏`&lt;script&gt;`) — مثبت باختبار. والرسم يتم بـ`base_url=None` فلا يستطيع القالب
جلب أي مورد خارجي أو قراءة ملف من النظام (‏path traversal).

## المحرك

WeasyPrint (‏HTML+CSS → PDF) لأنه يشكّل العربية ويطبق CSS الطباعة الحقيقي ويعمل
داخل الحاوية. مكتبات النظام مثبتة في `backend/Dockerfile`
(‏Pango/HarfBuzz/FriBidi/Cairo). على مضيف تطوير بلا هذه المكتبات يبقى الاستيراد
كسولًا فلا ينكسر بقية النظام، وتشغيل اختبارات المستندات المعتمد **داخل الحاوية**:

```
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings.test backend python -m pytest
```

معاينة الطباعة في المتصفح ممكنة للمستخدم، لكن **النسخة الرسمية المحفوظة تولد في
الخادم** دائمًا.
