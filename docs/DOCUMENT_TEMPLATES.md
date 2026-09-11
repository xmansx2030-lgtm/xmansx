# قوالب المستندات (المرحلة 12)

القوالب في `backend/documents/templates/documents/` ومسجلة في
`documents/templates_registry.py` — لا HTML داخل الـviews.

## السجل

| المفتاح | الإصدار | النوع | القالب |
|---|---|---|---|
| `warning_level_1` | v1 | الإنذار الأول | `warning.html` |
| `warning_level_2` | v1 | الإنذار الثاني | `warning.html` |
| `warning_level_3` | v1 | الإنذار الثالث | `warning.html` |
| `attendance_commitment` | v1 | تعهد الالتزام بالحضور | `commitment.html` |
| `absence_detail_report` | v1 | كشف تفصيلي للغياب | `absence_report.html` |
| `morning_late_report` | v1 | كشف التأخر الصباحي | `morning_late_report.html` |
| `student_attendance_report` | v1 | تقرير مواظبة الطالب | `attendance_report.html` |

## الإصدارات

كل مستند يخزن `template_key` و`template_version` وقت إصداره. تعديل التصميم لاحقًا
**يضيف** `v2` بمدخل جديد ولا يعدل `v1`، فيبقى المستند القديم مفهومًا ومطابقًا لما
صدر. إصدار غير موجود في السجل ⇒ `DOCUMENT_TEMPLATE_VERSION_UNAVAILABLE` (409)،
ونوع بلا قالب ⇒ `DOCUMENT_TEMPLATE_NOT_FOUND` (404).

## سياسة النماذج الرسمية

كل قوالب MVP `source_type = INTERNAL` — صياغة داخلية للمنصة. **ممنوع** وصف أي قالب
بأنه «نموذج وزاري معتمد» ما لم يُسجَّل مصدره داخل النظام:

```
source_type      = OFFICIAL
source_reference = مرجع التعميم/الدليل
source_version   = إصداره
effective_date   = تاريخ سريانه
```

النماذج الرسمية تتغير، فاعتمادها يكون بمدخل جديد يحمل مرجعه وإصداره — لا إعادة
تسمية لقالب داخلي ولا تثبيت نموذج قديم في الكود.

**ولا يُعدَّل نموذج رسمي لإضافة تفاصيل**: إذا لم يحتوِ التعهد جدول تواريخ، فالتفصيل
يصدر ككشف مستقل يُرفق — لا جدول يُحشر داخله مع ادعاء المطابقة.

## البنية والتنسيق

`base.html` يوفر لكل المستندات:

- `<html lang="ar" dir="rtl">` و`@page { size: A4 }` وهوامش وترقيم «صفحة N من M».
- خط `Noto Naskh Arabic` من النظام (حزمة `fonts-noto-core`, رخصة OFL) —
  **لا ملفات خطوط داخل المستودع**. التشكيل والاتجاه عبر Pango/HarfBuzz/FriBidi.
- ترويسة المدرسة (الاسم/المدينة/الرقم الوزاري) وجدول بيانات الطالب.
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
