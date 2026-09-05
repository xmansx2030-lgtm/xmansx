# Phase 20 Report

## PHASE 20 — PLAN

الهدف هو تحويل ناتج المراحل 0–19 إلى مرشح إصدار قابل للنشر والاستعادة: إغلاق
تغييرات المنتج غير المثبتة، تشغيل كل البوابات على PostgreSQL وRedis حقيقيين، بناء
صور إنتاج، فحص الصحة والمراقبة والأمان، تنفيذ استعادة فعلية إلى قاعدة وvolumes
منفصلة، ثم توفير نشر بصور مرتبطة بـ SHA وإجراءات migration/rollback موثقة.

## Status

**PASS داخل المستودع وبيئة الإنتاج المحلية المعزولة.** جميع المراحل الوظيفية
0–19 منفذة، ومتطلبات المرحلة 20 البرمجية وبوابة الاستعادة الفعلية ناجحة.

**External promotion: NOT RUN.** لا يوجد Git remote مضبوط في هذا checkout، ولم
توفر بيئة خادم أو DNS/TLS أو R2 أو Sentry credentials. لذلك لا يدعي هذا التقرير
أن GitHub Actions نفذت، أو أن نسخة رفعت إلى GHCR، أو أن خادما خارجيا حدث.

## Product completion batch

أغلقت الدفعة الحالية الأعمال الموجودة غير المثبتة فوق نهاية المرحلة 19، وتشمل:

- إنشاء الطالب والموظف يدويا مع التحقق والعزل وسير كلمات المرور المؤقتة.
- تعيين فصول المرشد وتأكيد نقل ملكية الفصل، مع توجيه إحالة المعلم للمرشد النشط.
- تحسين قراءة ملفات نور والموظفين متعددة الأوراق والعناوين غير الثابتة.
- نموذج الإنذار العربي v2 مع تفاصيل الغياب/التأخر وsnapshot غير قابل للتغيير.
- تخزين R2 منفصل للملفات الخاصة والمستندات والنسخ الاحتياطية.
- مطالبة تثبيت PWA وتحسين QR والاستجابة وRTL وتجربة لوحات جميع الأدوار.
- إصلاح قفل تعيين المرشد على PostgreSQL باستخدام `FOR UPDATE OF self`.
- إلغاء طلبات المدرسة المعلقة قبل تسجيل الخروج لمنع استجابة قديمة من حذف جلسة
  دخول جديدة عند التبديل السريع بين الأدوار.
- تحديث اختبارات E2E لتطابق العقود والواجهة الحالية بلا إضعاف فحوص العزل.

## Production readiness implementation

- `docker-compose.production.yml` يستخدم Gunicorn وNginx وworker وBeat كمستخدم
  غير root، ويمرر Sentry والheartbeat والنسخ المجدول وحدود الدخول الصارمة فعليا.
- القيم الافتراضية للنشر الخارجي آمنة: HTTPS والنسخ البعيد وR2 والجدولة مفعلة؛
  الاختبار المحلي وحده يعطلها صراحة في ملف مؤقت غير متتبع.
- `.github/workflows/ci.yml` يفحص Python/npm dependencies ويختبر الجسر، ثم يشغل
  64 رحلة Playwright على الحزمة الإنتاجية قبل السماح للإصدار.
- `.github/workflows/release.yml` يبني backend/frontend من SHA كامل واحد وينشر
  SBOM وprovenance وصور GHCR بلا `latest`.
- `scripts/deploy_release.sh` يرفض صورا من SHA مختلفين، يأخذ نسخة بعيدة قبل
  migration، يشغل `check --deploy`، ولا ينجح ما لم تمر liveness/readiness.
- أضيفت قائمة تشغيل في `docs/PRODUCTION_CHECKLIST.md` وعقد النشر والتراجع في
  `docs/PRODUCTION_RELEASE.md`.

## Security and dependency corrections

كشف `pip-audit` ثغرتي `CVE-2026-73228` و`CVE-2026-73229` في
`djangorestframework 3.16.1`. رُفع القيد إلى `>=3.17.2,<3.18`، ثم اجتاز الإصدار
3.17.2 جميع اختبارات Backend. النتيجة النهائية: لا ثغرات Python أو npm معروفة في
بيئة الفحص. بقيت حزمة المشروع المحلية فقط خارج PyPI ولذلك يذكرها `pip-audit`
كحزمة لا يمكن البحث عنها، لا كثغرة.

## Executed release gates

| Gate | Result |
| --- | --- |
| Backend on production image / PostgreSQL 18 | **738/738 PASS** |
| Frontend Vitest | **213/213 PASS** |
| Bridge | **11/11 PASS** |
| Production Playwright / Chromium / eight sequential shards / zero retries | **64/64 PASS** |
| Ruff / ESLint / TypeScript | **PASS** |
| npm production build + PWA | **PASS**, 70 precache entries |
| npm audit | **0 vulnerabilities** |
| pip-audit after DRF upgrade | **0 known vulnerabilities** |
| Django check / missing migrations | **PASS / none** |
| Fresh zero-to-head migration | **PASS** |
| Liveness / readiness | **200 / 200**, database and Redis `ok` |
| Container users | backend/worker/Beat = `app` |
| Compose config / workflow YAML / deploy Bash syntax | **PASS** |

OpenAPI generation and validation exits 0، لكن drf-spectacular ما زال يبلغ
356 موضع metadata ناقصا (70 فئة فريدة) و12 تحذيرا (10 فريدة)، أغلبها APIView
بلا serializer annotation وoperationId collisions. هذا دين توثيق API موجود ولا
يؤثر في تنفيذ endpoints أو الاختبارات، لكنه ليس موصوفا كـ «نظيف» في هذا التقرير.

## Actual backup and restore drill

نفذت التجربة على مشروع Compose المعزول `xmansx-phase20` وصور الإنتاج نفسها:

| Evidence | Result |
| --- | --- |
| PostgreSQL custom backup | 622,440 bytes، 923 ms |
| SHA-256 | `dfb89359645cdf4acc6322791d59d0ac4de818080268c2483106a700ec9f00c1` |
| Separate target database | `xmansx_phase20_restore` |
| Restore | 4,271 ms؛ الإنشاء والاستعادة 9,228 ms |
| Target migrate/check/manifest verification | PASS in 13,850 ms |
| Restored manager login | HTTP 200 through the Django API view |
| Private-object backup | 29 objects، 3,385,608 bytes |
| Isolated object restore | 29 restored، 0 skipped |
| Post-restore integrity | 29 checked؛ 0 missing/mismatch/errors |

تطابقت كيانات الطالب والقيد والحضور والعذر والإنذار والمستند والإحالة والحالة
الإرشادية والجهاز، وحفظت entitlement snapshots وعددها 13 وchecksum المستند.
الدليل الآلي الكامل في `RESTORE_DRILL_RESULT.json`.

## Database and API changes included

- طبقت migration المستندات `0003`، وتعيين فصول المرشد `staff.0002`، وتفاصيل
  snapshot للإنذارات `student_warnings.0002` من قاعدة فارغة بنجاح.
- أضيفت endpoints الإنشاء اليدوي للطلاب والموظفين وإدارة فصول المرشد، ووسعت
  استجابات المستندات والإنذارات ولوحة الإدارة، مع اختبارات صلاحيات وعزل.

## Known boundaries

- النشر الخارجي ونتيجة CI الفعلية وdeployed SHA وTLS/uptime لم تختبر لغياب remote
  وبيئة هدف.
- R2/Sentry متكاملان ومختبران منطقيا، لكن لا يمكن إثبات رفع نسخة بعيدة أو ظهور
  release/event بلا credentials حقيقية.
- HSTS preload يبقى معطلا عمدا حتى اعتماد نطاقات الإنتاج وفترة المراقبة.
- قيود السعة المقاسة في المرحلة 19 ما زالت سارية: ابدأ بأقل من 50 مستخدما مختلطا
  متزامنا لكل replica ثم أعد القياس على عتاد الإنتاج.

## Exit decision

معيار الخروج الأهم للمرحلة 20 — **تجربة استعادة فعلية ناجحة قبل إعلان الجاهزية** —
محقق. المشروع **release-ready** من ناحية الكود والتشغيل المحلي، لكنه لا يصبح
**externally deployed** إلا بعد إكمال خانات البيئة الخارجية في قائمة الإنتاج
وحفظ أدلتها.
