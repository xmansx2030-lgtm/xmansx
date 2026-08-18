# خطة التنفيذ — المراحل 0–20

> قواعد ملزمة لكل مرحلة:
> 1. تبدأ بـ `PHASE X — PLAN` (الهدف، الملفات، Models، APIs، UI، Migrations، Tests، الأمان).
> 2. لا انتقال قبل: اكتمال المرحلة، نجاح الاختبارات، الفحص الأمني/المنطقي، نجاح البناء، كتابة `PHASE_X_REPORT.md`.
> 3. «تم» بلا دليل تنفيذ فعلي = مخالفة. Build PASS يعني أن البناء شُغّل فعلًا.
> 4. لكل endpoint مدرسي جديد: اختبار عزل مستأجرين إلزامي ضمن تعريف Done.

## جدول المراحل

| # | المرحلة | المخرجات الأساسية | معيار الخروج الأهم |
|---|---|---|---|
| 0 | Discovery & Architecture | docs/ (هذه الوثائق) | الوثائق الخمس + ADRs + تقرير |
| 1 | Foundation | Django+DRF, React+Vite+TS+Tailwind, Postgres, Redis, Docker Compose, `.env.example`, health endpoints, structured logging, معالجة أخطاء أساسية، pytest/Vitest/Playwright جاهزة، CI | `tests + lint + typecheck + build + django checks` كلها خضراء على هيكل فارغ |
| 2 | Accounts + Multi-Tenancy | User, School, SchoolMembership, MembershipRole؛ دخول بالجوال (Argon2, rate limit)، خروج، اختيار/تبديل المدرسة، Middleware العزل، Base permissions، Audit للدخول والتبديل | اختبارات العزل الصارمة + متعدد المدارس بلا اختلاط |
| 3 | School Settings | SchoolSettings, AcademicYear, Semester, SchoolDay, BellSchedule(+Periods)؛ واجهة الإعدادات كاملة | جدول نشط واحد، validation الأوقات، صلاحية MANAGER فقط |
| 4 | Student Import | Student(هوية مشفرة+hash), StudentEnrollment, Grade, Section؛ مسار Upload→Validate→Preview→Approve→Import عبر Celery؛ التحديث بالمطابقة وعرض الفروقات | ملفات صحيحة/خاطئة/مكررة؛ لا حذف تاريخ؛ Idempotency |
| 5 | Staff Import | استيراد اسم+جوال؛ إعادة استخدام User العالمي؛ إنشاء Membership+TEACHER | معلم بمدرستين = User واحد وعضويتان |
| 6 | Teacher Attendance | شاشة المعلم Mobile-First؛ استنتاج الحصة الحالية؛ AttendanceSession+AttendanceMark؛ منع التكرار؛ late_minutes؛ نافذة التعديل | قيد Unique تحت التزامن؛ حساب التأخر؛ Audit |
| 7 | Monitoring Dashboard | لوحة الوكيل: حالة الحصة الحالية لكل فصل، مؤشرات اليوم؛ Celery Beat لتنبيه `unprepared_period_alert_minutes` | الفصول غير المحضرة تظهر بعد المهلة فقط |
| 8 | Attendance Analytics | فلترة غائب بحصة/عدة حصص/كلها (AND)؛ غياب جزئي/كامل؛ INCOMPLETE؛ DailyAttendanceSummary | حصة غير محضرة تمنع FULL_DAY وتستثني الفصل من فلتر «كل الحصص» |
| 9 | Student Profile | بحث بالهوية (hash) والاسم؛ ملف الطالب الكامل بمؤشراته | تقنيع الهوية؛ صلاحيات العرض حسب الدور |
| 10 | Excuses | Excuse+Coverage+Attachments؛ UNEXCUSED→EXCUSED مع سجل تغيير؛ تحديث العدادات | لا حذف الحالة الأصلية؛ Signed URLs؛ اعتماد Idempotent |
| 11 | Warning Rules | WarningRule (غياب/تأخر × 3 مستويات، first<second<third)؛ StudentWarning بـ Snapshots | الإنذار القديم لا يتغير بعد تعديل الغياب؛ لا إصدار مزدوج |
| 12 | Actions + Documents | StudentAction؛ GeneratedDocument؛ PDF عربي RTL (إنذارات، تعهد، كشف غياب، تقرير طالب، سجل إجراءات) | المستند من Snapshot لا من البيانات الحية |
| 13 | Referrals | StudentReferral (وكيل→مرشد، معلم→مرشد) بفئات وأسباب وحالات؛ كشف التكرار + إضافة ملاحظة بديلة | معلم يرى إحالاته فقط؛ تنبيه الملف المفتوح |
| 14 | Counselor Portal | لوحة المرشد؛ تفاصيل الإحالة؛ CounselorAction؛ FollowUpPlan؛ طلب متابعة المعلم ورده؛ إغلاق الحالة | المرشد لا يعدل الحضور الأصلي (اختبار صريح) |
| 15 | Manager Dashboard | KPIs الحضور/الغياب/التأخر/الإنذارات/الإحالات/الفصول غير المحضرة؛ إدارة المستخدمين | قراءات من Summary لا حسابات حية ثقيلة |
| 16 | Platform Admin | إدارة المدارس والخطط والاشتراكات (TRIAL/ACTIVE/PAST_DUE/EXPIRED/SUSPENDED) والاستخدام | لا وصول لبيانات الطلاب (اختبار صريح)؛ الإيقاف = قراءة فقط |
| 17 | PWA | Manifest, Icons, SW (Workbox), Offline shell, تدفق التحديث | قابلية التثبيت على Chrome/Android/iOS؛ بلا Offline Attendance |
| 18 | Hardening | مراجعة: RBAC, العزل, IDOR, CSRF, XSS, SQLi, Rate limiting, الملفات, السجلات الحساسة, CSP, HSTS, Cookies | تقرير فحص أمني ببنود SECURITY.md كاملة |
| 19 | Performance | حمل 100/500/1000 مدرسة ببيانات معقولة؛ قياس: التحضير، اللوحات، البحث، الفلترة، الإنذارات، التقارير | فهارس حسب القياس لا التخمين؛ أهداف زمن استجابة موثقة |
| 20 | Production Readiness | Checklist، نسخ احتياطي/استعادة، نشر، Monitoring، Sentry، Health/Readiness، إجراءات Migration/Rollback | تجربة استعادة فعلية ناجحة قبل إعلان الجاهزية |

## تسلسل الاعتماديات

```text
1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15
                                          (16, 17 بعد 2 و15 عمليًا)
16 → 18 → 19 → 20
```

- المرحلة 6 تعتمد على 3 (BellSchedule لاستنتاج الحصة) و4 (الطلاب والفصول) و5 (المعلمون).
- المرحلة 8 تعتمد على 6 (العلامات) وتُغذي 9 و11 و15.
- المرحلة 11 تعتمد على 8 (العدادات) وتُغذي 12.

## تقرير كل مرحلة — `PHASE_X_REPORT.md`

```text
Status | What was implemented | Files changed | Database changes | API changes
UI changes | Security checks | Tests executed | Tests results
Known limitations | Remaining work | Risks
```

## أوامر الفحص الدنيا بعد كل مرحلة

```text
Backend:  pytest، ruff check، mypy (إن فُعّل)، python manage.py check --deploy، makemigrations --check
Frontend: vitest run، tsc --noEmit، eslint، vite build
E2E:      playwright (للمراحل ذات UI مكتمل)
```
