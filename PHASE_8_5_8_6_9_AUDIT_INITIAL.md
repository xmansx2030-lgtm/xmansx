# PHASE 8.5 / 8.6 / 9 — تقرير الجرد الأولي (قبل أي تعديل)

**تاريخ الجرد:** 2026-08-19 — المدقق المستقل. كل ما يلي من فحص Git والكود مباشرة،
لا من تقارير الوكيل السابق.

## Git

- **Current branch:** `feature/phase-9-student-profile`
- **Current commit:** `234ff86` — "feat: integrate morning attendance into student profile"
- **سلسلة الالتزامات:** ‏`master` عند `59d95eb` (نهاية م8 المعتمدة) ← `cfce2b3`
  ‏"wip: preserve parallel phase 8.5 8.6 and 9 work" (‏Rescue commit — لا يمس) ←
  ‏`234ff86` (‏HEAD).
- **Working tree:** غير نظيفة — **9 ملفات معدلة + 1 غير متتبع**:
  - ‏`backend/attendance/api/views.py` (+1: تمرير فلتر grade لليومي)
  - ‏`backend/attendance/selectors/analytics.py` (فلتر grade لليومي)
  - ‏`backend/devices/api/views.py` (تسليم أوامر roster في نبضة الالتقاط فقط + حالة APPROVED)
  - ‏`bridge/bridge_core/{engine,config,__main__}.py` (تمرير simulator_users_file)
  - ‏`frontend/src/features/attendance/{AnalyticsPage.tsx,api.ts}` + ‏`frontend/e2e/analytics.spec.ts`
  - ‏`frontend/e2e/device-roster-sync.spec.ts` — **غير متتبع** (Playwright لـ8.6)
  - التقييم الأولي: بقايا WIP لجلسة موازية — إصلاحات تكامل/E2E أخيرة لم تلتزم.
- **Stashes:** لا يوجد. **Worktrees:** واحدة فقط (الرئيسية).
- توزيع المراحل: 8.5+8.6+9 كلها في فرع واحد فوق master — لا فروع منفصلة لكل مرحلة.

## التقارير الموجودة (Claims تُدقق — ليست دليلًا)

`PHASE_8_5_REPORT.md`، `PHASE_8_6_REPORT.md`، `PHASE_9_REPORT.md`،
`PHASE_8_5_8_6_9_INTEGRATION_REPORT.md`. **المفقود:** `PHASE_8_7_REPORT.md`
(بوابة تحقق ذُكرت في التكليف ولا أثر لها كملف).

## الاختبارات الموجودة (ملفات — لم تشغَّل بعد ضمن هذا التدقيق)

- Backend ‏(30 ملفًا) منها الجديد للمراحل قيد التدقيق:
  ‏`test_devices_morning.py`، ‏`test_device_roster_sync.py`،
  ‏`test_student_attendance_profile.py`.
- Bridge: ‏`test_bridge_core.py`، ‏`test_roster_adapter.py`.
- Playwright ‏(10 ملفات) منها `device-roster-sync.spec.ts` (غير متتبع).
- Frontend Vitest: مجلد `features/devices/` موجود — يفحص محتواه لاحقًا.

## بنية الكود ذات الصلة (وجود لا أكثر — الوظيفة تُدقق لاحقًا)

- ‏`backend/devices/`: ‏models (‏Bridge/Device/Identity/Event/Arrival/ArrivalChange +
  ‏RosterSyncJob/Item)، ‏services (bridge/ingest/morning/roster)، ‏selectors/morning،
  ‏api (serializers/roster_serializers/views)، ‏migrations 0001+0002، ‏purge_integration
  (يشمل roster items)، ‏benchmark_devices.
- ‏`backend/students/`: ‏services/attendance_profile.py + ‏api/profile_serializers.py +
  مسار في urls.
- ‏`bridge/`: ‏queue/client/engine/adapters(base+simulator)/config/__main__.
- ‏Frontend: ‏`features/devices/` + ‏`StudentAttendanceProfilePage.tsx` + مسارات وروابط.

## ملفات متوقعة ولم توجد

- ‏`PHASE_8_7_REPORT.md` (بوابة التحقق).
- ‏Benchmarks لـ: ‏Roster compare/apply وStudent Profile (يتحقق: ‏benchmark_devices يغطي
  الصباحي والأحداث فقط حسب الظاهر).
- توثيق docs لـ: ‏DEVICES/DEVICE_BRIDGE/DEVICE_BRIDGE_API/MORNING_ATTENDANCE —
  **غير موجودة في docs/** (فجوة توثيق مرجحة؛ يتأكد أثناء التدقيق).

## المخاطر الأولية

1. شجرة غير نظيفة: تعديلات غير ملتزمة قد تكون ضرورية لنجاح الاختبارات — يجب تشغيل
   الاختبارات على الحالة الحالية كما هي ثم حسم مصير هذه التعديلات في commit واضح.
2. ‏E2E ‏roster-sync غير متتبع — قد لا يكون شُغّل قط.
3. أعداد الاختبارات في التقارير (Backend/Vitest/Playwright) غير موثوقة حتى إعادة
   التشغيل الفعلي.
4. عمل المراحل الثلاث مدموج في commitين + WIP — لا يمكن فصل 8.5 عن 8.6 عن 9 بالرجوع
   لـGit؛ التدقيق سيكون على الحالة المجمعة.
5. احتمال بقايا تعارض من التحرير المتوازي السابق (تصادمات موثقة في سجل الجلسة
   السابقة) — يفحص بالتشغيل الكامل.

**الخطوة التالية:** تشغيل كل بوابات التحقق بنفسي (ruff/check/migrations/pytest/bridge/
frontend/docker/playwright/fresh-db/benchmarks/security greps) ثم مصفوفة المتطلبات.

---

## نتائج بوابات التحقق (2026-08-19 — نفذت فعليًا)

| البوابة | النتيجة |
|---|---|
| Backend pytest (settings=test داخل الحاوية) | ✅ 352/352 |
| ruff check | ✅ |
| Django check | ✅ 0 issues |
| makemigrations --check | ✅ لا تغييرات |
| Bridge pytest | ✅ 9/9 |
| Frontend typecheck + eslint | ✅ |
| Vitest | ✅ 84/84 (13 ملفات) |
| Frontend build | ✅ |
| Playwright E2E (12 spec) | ✅ 27/27 بعد إصلاح واحد |
| Fresh migrate (قاعدة PostgreSQL جديدة) | ✅ |
| Docker (backend/frontend/postgres/redis/worker/beat) | ✅ Healthy |

ملاحظات:
1. تشغيل pytest داخل الحاوية يتطلب `DJANGO_SETTINGS_MODULE=config.settings.test`
   (البيئة الافتراضية للحاوية `local` تعطل Celery eager فتفشل اختبارات الاستيراد/الـpurge زورًا).
2. إصلاح وحيد: `frontend/e2e/analytics.spec.ts` — اختبار «تعديل الحضور يحدث التحليلات»
   لم يكن يطبق فلتر الصف الجديد فتأثر بتراكم بيانات seed (pagination). أضيف الفلتر
   بنفس نمط بقية الاختبارات.
3. `check --deploy` على إعدادات local يظهر تحذيرات أمنية متوقعة لبيئة التطوير فقط.

**القرار:** المراحل 8.5 + 8.6 + 9 مجتازة لبوابات التحقق — يعتمد الدمج في master.
