# ADR-011: تثبيت Custom User قبل أي Models أعمال — مع إعادة إنشاء قاعدة التطوير

- **الحالة:** مقبول — 2026-08-18
- **السياق:** المرحلة 1 طبّقت migrations إطار العمل فقط (auth/contenttypes/sessions) على `auth.User` الافتراضي. تغيير `AUTH_USER_MODEL` بعد وجود FKs إليه من جداول أعمال عمليةٌ خطرة وموثقة الصعوبة في Django. فُحصت القاعدة فعليًا قبل القرار: **0 صفوف** في `auth_user` و`django_session`، و9 جداول كلها framework — لا بيانات أعمال ولا بيئة Production أصلًا.
- **القرار:**
  1. إنشاء `accounts.User` مخصص (`AbstractUser` بإزالة `username`، `USERNAME_FIELD="mobile"`) **قبل** أي Model أعمال آخر.
  2. `AUTH_USER_MODEL = "accounts.User"` من أول migration لتطبيق accounts.
  3. إعادة إنشاء قاعدة **التطوير** (`DROP DATABASE xmansx; CREATE DATABASE xmansx;` داخل حاوية postgres) ثم `migrate` من الصفر — مسموح حصرًا لأن البيئة local/test بلا أي بيانات.
  4. إثبات إلزامي: `migrate` على قاعدة فارغة جديدة كليًا + `makemigrations --check` — موثق في PHASE_2_REPORT.
- **التبعات:** لا حاجة لأي migration تحويلي هش؛ كل FKs المستقبلية (Membership, Attendance, …) تولد على المستخدم المخصص مباشرة. أي تغيير لاحق على هوية المستخدم يكون migration عاديًا. **ممنوع** تكرار إعادة الإنشاء هذه بعد وجود بيانات — كانت مشروعة لهذه اللحظة الفريدة فقط.
