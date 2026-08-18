# PHASE 2 REPORT — Accounts + Multi-Tenancy

**التاريخ:** 2026-08-18

## Status

`COMPLETE` — كل معايير القبول (البند 78) تحققت بتشغيل فعلي موثق أدناه.

## Custom User migration decision

- فُحصت الحالة قبل التنفيذ: `AUTH_USER_MODEL = auth.User`، migrations إطار العمل فقط مطبقة، و**0 صفوف** في `auth_user` و`django_session` (9 جداول كلها framework).
- القرار (موثق في [ADR-011](docs/adr/ADR-011-custom-user-before-domain-data.md)): تثبيت `accounts.User` الآن قبل أي Model أعمال، مع إعادة إنشاء قاعدة التطوير.

## Database reset/recreation details

- **why:** تغيير AUTH_USER_MODEL بعد تطبيق migrations على auth.User لا يتم تحويليًا بأمان؛ المشروع بلا أي بيانات.
- **what database:** `xmansx` على حاوية postgres التطويرية فقط (لا Production أصلًا).
- **confirmation:** إخراج موثق قبل الحذف: `auth_user rows: 0`, `sessions rows: 0`.
- **commands:** `docker compose exec postgres psql -U xmansx -d postgres -c "DROP DATABASE xmansx WITH (FORCE);" -c "CREATE DATABASE xmansx OWNER xmansx;"` ثم `manage.py migrate` (كل الـ migrations OK).

## Models implemented

| Model | الأبرز |
|---|---|
| `accounts.User` | AbstractUser بلا username، `mobile` unique عالميًا (USERNAME_FIELD)، Argon2id، `is_platform_admin = is_superuser` |
| `schools.School` | name, slug (unique), status (ACTIVE/SUSPENDED/ARCHIVED) |
| `memberships.SchoolMembership` | user×school، status (ACTIVE/INVITED/SUSPENDED/LEFT)، joined_at |
| `memberships.SchoolMembershipRole` | membership×role (4 أدوار مدرسية enum) |
| `audit.AuditLog` | append-only، Admin قراءة فقط، metadata بحارس ضد الحقول الحساسة |
| `common.TimestampedModel` | created_at/updated_at لكل الكيانات |

## Constraints

- `UNIQUE(user.mobile)` — عالمي.
- `UNIQUE(user, school)` على SchoolMembership — **مثبت باختبار IntegrityError عبر bulk_create يتجاوز الـ validation**.
- `UNIQUE(membership, role)` — مثبت باختبار مماثل.
- `UNIQUE(school.slug)`.

## Indexes

`school(status)`, `membership(school, status)`, `audit(school, created_at)`, `audit(action)` — بلا فهارس مكررة فوق قيود UNIQUE.

## Authentication flow

csrf bootstrap → login (تطبيع → rate limit → authenticate → تدوير الجلسة → اختيار تلقائي للمدرسة الوحيدة) → me/schools → switch → logout (flush). التفصيل في [docs/AUTHENTICATION.md](docs/AUTHENTICATION.md).

## Mobile normalization

مركزي في `accounts/mobile.py` (يشمل الأرقام العربية والفواصل وكل الصيغ الشائعة) — 20 اختبار حالات صحيحة/خاطئة. `mask_mobile` للسجلات.

## Session + CSRF

Django sessions (cookies HttpOnly/SameSite، Secure في الإنتاج). تدوير المفتاح عند الدخول وعند التبديل. CSRF مفروض حتى على login (`csrf_protect`) — اختبار بـ `enforce_csrf_checks=True` يثبت الرفض بلا token والنجاح معه.

## Rate limiting

Redis cache: IP = 20/5د (كل المحاولات)، جوال = 5/5د فاشلة (sha256 في المفاتيح، تصفير عند النجاح). اختبارات فعلية: الوصول لـ 429، وحجب حتى كلمة المرور الصحيحة داخل النافذة، والتصفير بعد النجاح.

## School membership / Role architecture

User → SchoolMembership → SchoolMembershipRole (تعدد مدارس وتعدد أدوار). ممنوع `User.school_id`/`User.role`. PLATFORM_ADMIN صلاحية منصة بلا عضوية. التفصيل في [docs/MULTI_TENANCY.md](docs/MULTI_TENANCY.md).

## Active school flow

`active_school_id` في الجلسة فقط؛ `TenantContextMiddleware` يعيد التحقق كل طلب ويثبت `request.school/membership/school_roles`؛ السياق الفاسد يزال فورًا ويحمل رمزًا دقيقًا. عضوية واحدة فعالة → اختيار تلقائي؛ أكثر → شاشة الاختيار.

## Tenant isolation

طبقة Permissions مركزية (`ActiveSchoolRequired`, `school_role_required`, `has/require_school_role`) + الثوابت الخمسة موثقة في MULTI_TENANCY.md. اختبارات اختراق فعلية (انظر Tests).

## Frontend screens

Login عربية RTL (تحقق، أخطاء API، rate-limit، إظهار/إخفاء كلمة المرور) — «اختر المدرسة» (بطاقات باسم المدرسة والأدوار) — App Shell (اسم المستخدم، المدرسة، الأدوار، Switcher، خروج) — حراس مسارات (RequireAuth/RequireActiveSchool) — التبديل يزيل كل cache غير `["me"]` ومفاتيح البيانات المدرسية المستقبلية `["school", activeSchoolId, ...]`.

## API endpoints

`GET /api/v1/auth/csrf/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/`, `GET /auth/schools/`, `POST /session/active-school/` + رموز الأخطاء: INVALID_CREDENTIALS, LOGIN_RATE_LIMITED, AUTHENTICATION_REQUIRED, ACTIVE_SCHOOL_REQUIRED, INVALID_SCHOOL_MEMBERSHIP, MEMBERSHIP_SUSPENDED, SCHOOL_SUSPENDED, PERMISSION_DENIED.

## Security review (البند 67 — كلها مغطاة باختبارات فعلية)

| البند | الإثبات |
|---|---|
| Session fixation | اختبار تغير session_key بعد login |
| CSRF | اختبار enforce_csrf_checks: رفض بلا token، نجاح معه |
| Brute force | اختباران: 429 + تصفير بعد النجاح |
| User enumeration | ردّا «رقم خاطئ» و«كلمة مرور خاطئة» متطابقان بالبايت |
| Tenant selection | switch لمدرسة أجنبية/غير موجودة → نفس 403 |
| Role leakage | أدوار B لا تظهر في A؛ التبديل لا يمنح صلاحيات (اختباران) |
| Cache leakage | اختبار يزرع بيانات مدرسة قديمة ويتحقق من زوالها بعد التبديل |
| IDOR | switch بمعرف أجنبي + /auth/schools/ لا تقبل معرف مستخدم |
| Inactive membership | stale session تنظف؛ SUSPENDED/LEFT محجوبة |
| Suspended school | SCHOOL_SUSPENDED عند التبديل وفي stale session |

كلمات المرور: لا تظهر في الاستجابات/السجلات (اختبار)، وLOGIN_FAILED يسجل جوالًا مقنعًا فقط (اختبار).

## Tests executed / results

- **Backend: `pytest` → 76/76 PASS** (20 تطبيع + 7 مستخدم + 13 مصادقة/rate-limit + 16 عزل وtenant + 7 صلاحيات + 1 عدد استعلامات + 12 أساس المرحلة 1).
- **Frontend: Vitest → 19/19 PASS** (login/validation/أخطاء/rate-limit/التدفقات/الحراس/التبديل/الخروج/cache/CSRF header/404/RTL).
- Query count: `/me` بأربع مدارس ≤ 6 استعلامات (django_assert_max_num_queries) — لا N+1.

## E2E results

**Playwright → 3/3 PASS** ضد النظام الحقيقي في Docker مع بيانات seed_dev:
1. smoke (RTL + login + backend reachable).
2. المعلم بمدرستين: دخول → «اختر المدرسة» → الأندلس → Shell → تبديل للرواد (الأدوار تتغير لمعلم+مرشد) → خروج → عودة للدخول.
3. العزل: مستخدم مدرسة C فقط — قائمته لا تحوي الأندلس، ومحاولة switch لمعرف الأندلس عبر API → 403 INVALID_SCHOOL_MEMBERSHIP ومدرسته النشطة لم تتغير.

## Migration / Fresh database results

- `makemigrations accounts schools memberships audit` → 4 ملفات initial.
- إعادة إنشاء `xmansx` + `migrate` من الصفر → PASS.
- **قاعدة جديدة كليًا `xmansx_fresh` + `migrate` → PASS (exit 0)** ثم حذفت.
- `makemigrations --check --dry-run` → "No changes detected" PASS.
- `createsuperuser --noinput --mobile 0559999999` → نجح؛ تحقق فعلي: mobile مطبّع `+966559999999`، hash يبدأ `argon2$argon2id$`، `check_password=True`.

## Docker result

الخدمات الست بعد إعادة البناء: backend **healthy**، worker **healthy**، postgres **healthy**، redis **healthy**، beat Up، frontend Up — وseed_dev نفذ داخل الحاوية، وE2E عمل عبر frontend الحاوية (منفذ postgres على الجهاز 5433 لتفادي تعارض محلي).

## Performance observations

`/me` و`/auth/schools/` عبر selector واحد بـ select_related+prefetch_related (استعلامان للعضويات مهما تعدد المدارس) محروس باختبار عدد استعلامات. لا فهارس إضافية بلا قياس.

## Known limitations

- Platform Admin بلا واجهات بعد (المرحلة 16) — التمثيل والحدود فقط.
- إدارة العضويات (إنشاء/تعطيل) عبر Django Admin وseed فقط حتى مراحل الاستيراد.
- رسالة السياق الفاسد تظهر للمستخدم عند الطلب التالي (polling لاحقًا قد يحسن الفورية).

## Technical debt

- اختبار `test_mobile_unique_globally` تأكيده النهائي ضعيف (يكتفي بحدوث الاستثناء) — يكفي عمليًا لوجود اختبار DB-level منفصل.
- `seed_dev` يبحث عن المستخدم بـ `mobile__endswith` — يصلح لبيئة التطوير فقط (موثق).

## Risks

| الخطر | التخفيف |
|---|---|
| endpoint مدرسي مستقبلي ينسى ActiveSchoolRequired | Base ViewSet مدرسي إلزامي يبنى مع أول endpoint أعمال (مرحلة 3) + اختبار عزل لكل endpoint |
| نمو أخطاء تزامن العضويات | القيود في DB أصلًا؛ transactions مطبقة في seed وستطبق في الاستيراد |

## Files changed

- **Backend جديد:** accounts/ (models, managers, mobile, rate_limit, admin, api/, management/), schools/, memberships/ (models, middleware, permissions, selectors, admin, urls), audit/ (models, services, admin), common/models.py + 4 migrations initial.
- **Backend معدل:** settings (apps/middleware/hashers/caches/rate-limit/AUTH_USER_MODEL)، config/urls، common/errors (ApiError + AUTHENTICATION_REQUIRED)، pyproject (argon2-cffi).
- **Frontend جديد:** features/auth/ (LoginPage, SelectSchoolPage, SchoolSwitcher, guards, useMe + 3 ملفات اختبار), components/PasswordInput, api/auth, types/auth, utils/roles, test/ (mockApi, renderApp), e2e/auth.spec.
- **Frontend معدل:** api/client (CSRF)، AppShell، HomePage، routes، App.test، client.test، smoke.spec.
- **Docs:** AUTHENTICATION.md، MULTI_TENANCY.md، ADR-011، ملحق RLS في ADR-002، تحديثات ERD/ARCHITECTURE.

## Commits

انظر نهاية المحادثة — commit واحد شامل: `feat: add accounts and multi-tenant foundation`. لا push (لا remote مصرح).

## Ready for Phase 3?

**نعم.** أساس الهوية والعضوية والعزل مكتمل ومختبر اختراقيًا. المرحلة 3 (School Settings) تبني فوقه مباشرة: أول endpoints مدرسية ستستخدم `ActiveSchoolRequired` + `school_role_required("SCHOOL_MANAGER")` الجاهزة، مع Base pattern للـ ViewSets المدرسية.
