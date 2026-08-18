# ADR-008: Polling بدل WebSockets

- **الحالة:** مقبول — 2026-08-18
- **السياق:** لوحة الوكيل تحتاج «حداثة بالدقائق» لا «لحظية بالمللي ثانية». WebSockets تضيف Channels/ASGI وطبقة تشغيل إضافية.
- **القرار:** Polling عبر TanStack Query (`refetchInterval` 30–60 ثانية للوحات، مع `staleTime` مناسب) فوق Endpoints ملخصة رخيصة (تقرأ من `DailyAttendanceSummary` وعدادات cache).
- **التبعات:** بنية أبسط ونفس القيمة العملية. لو ظهرت حاجة حقيقية للحظية تُضاف WebSockets بقرار جديد دون تغيير الـ API الحالية.
