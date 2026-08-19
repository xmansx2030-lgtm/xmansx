# School Device Bridge — جسر أجهزة الحضور

خدمة محلية تعمل داخل شبكة المدرسة: تتصل بأجهزة الحضور عبر LAN، تطبع الأحداث،
تخزنها في طابور SQLite دائم، وترسلها إلى SaaS عبر HTTPS **للخارج فقط** —
لا Port Forwarding ولا كشف للجهاز على الإنترنت، ولا أي بيانات بيومترية.

- **التقنية:** Python 3.12+ قياسية بالكامل (بلا تبعيات خارجية — `urllib` + `sqlite3`)،
  متوافقة مع stack المشروع (ADR في docs/DEVICE_BRIDGE.md).
- **Headless:** ‏`python -m bridge_core run` حلقة تشغيل دائمة؛ ‏`run-once` دورة واحدة.
- **Windows Service:** التغليف عبر NSSM أو `sc create` مع Auto Start —
  موثق في docs/DEVICE_BRIDGE.md (تثبيت الخدمة الفعلي: NOT RUN في بيئة التطوير هذه؛
  المحرك مختبر مستقلًا عن غلاف الخدمة).

## الإعداد

متغيرات بيئة أو ملف `bridge.json` بجوار التشغيل:

```json
{
  "saas_url": "https://school-platform.example",
  "credential": "brg_xxxxxxxx_...",       // يظهر مرة واحدة عند التجهيز
  "queue_path": "bridge-queue.sqlite3",
  "heartbeat_seconds": 60,
  "batch_size": 200
}
```

‏`credential` يولده مدير المدرسة من: الإعدادات ← أجهزة الحضور ← إضافة جسر.
هوية المدرسة تشتق منه في الخادم — الجسر لا يرسل school_id أبدًا.

## الاختبارات

```
cd backend
.\.venv\Scripts\python.exe -m pytest ..\bridge\tests -q
```
