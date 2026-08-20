# UX وAccessibility Baseline

## Responsive وRTL

الواجهة عربية `dir=rtl`. تمت مراجعة الأحجام:

```text
360x800, 390x844, 768x1024, 1024x768, 1366x768, 1440x900
```

أقل من 1280px يستخدم shell قائمة تنقل مضغوطة قابلة للتمرير. على الشاشات الواسعة
يلتف navigation إلى صف ثان بدل قص الروابط. الجداول الكبيرة تبقى داخل scroll
container مقصود، والـpurge dialog له max-height وتمرير وأزرار قابلة للوصول.

## لوحة المفاتيح والدلالات

- skip link إلى `main`, وتركيز واضح بـ`focus-visible`.
- عناصر التنقل روابط فعلية، والأزرار ذات الأيقونة لها accessible name وtooltip
  عند الحاجة. Menu يعلن `aria-expanded` و`aria-controls`.
- inputs تحمل labels، ورسائل validation/errors تستخدم role مناسبًا، وعمليات
  submit تعطل التكرار وتعرض loading state.
- الحالات لا تعتمد على اللون وحده؛ تعرض نصًا مثل غائب، متأخر، منتهي، ومعلق.

## رحلات الأدوار

تمت مراجعة screenshots فعلية للمعلم على الجوال، الوكيل والمرشد على tablet، المدير
ومدير المنصة على desktop. Playwright الكامل يغطي dashboard/monitoring/profile/
excuses/warnings/referrals/counseling/devices/subscription/platform، ويثبت عزل
الأدوار والمدارس. لا يوجد horizontal page overflow في المقاسات المعتمدة.

