# School Device Bridge — جسر أجهزة الحضور

خدمة محلية تعمل داخل شبكة المدرسة: تتصل بأجهزة الحضور عبر LAN، تطبع الأحداث،
تخزنها في طابور SQLite دائم، وترسلها إلى SaaS عبر HTTPS **للخارج فقط** —
لا Port Forwarding ولا كشف للجهاز على الإنترنت، ولا أي بيانات بيومترية.

- **القلب:** Python 3.12+ قياسي (`urllib` + `sqlite3`). موصل ZKTeco LAN تبعية
  اختيارية مستقلة حتى لا تتأثر بيئات المحاكي.
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

## تفعيل ZKTeco MB2000 عبر LAN

على جهاز Windows الموجود داخل شبكة المدرسة:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-zkteco.txt
.\.venv\Scripts\python.exe -m bridge_core run-once --config bridge.json
```

ثم من لوحة المدير: **أجهزة الحضور ← إضافة جهاز**، واختر `ZKTeco` و`MB2000`
وأدخل IP ثابتًا، والمنفذ `4370`، ونوع الاتصال `TCP`، وComm Key المطابق للجهاز.
القيمة `0` تعني عدم وجود كلمة مرور اتصال وفق إعداد الجهاز.

مهم: الحزمة الاختيارية `pyzk` غير رسمية وترخيصها GPL-2.0. يجب مراجعة التزامات
ترخيص توزيع جسر Windows قبل شحنه تجاريًا. بديل المؤسسات هو تركيب Standalone SDK
الرسمي من ZKTeco خلف نفس عقد Adapter بعد استلامه من المورد.

## الاختبارات

```
cd backend
.\.venv\Scripts\python.exe -m pytest ..\bridge\tests -q
```
