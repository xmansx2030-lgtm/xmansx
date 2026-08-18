# ADR-004: Session Cookies + Argon2 بدل JWT

- **الحالة:** مقبول — 2026-08-18
- **السياق:** العميل الوحيد في MVP هو الويب/PWA على نفس النطاق؛ JWT في LocalStorage معرض لـ XSS وممنوع بنص المتطلبات.
- **القرار:** Django Sessions (تخزين DB مع cache) عبر Cookies: `HttpOnly`, `Secure`, `SameSite=Lax` + حماية CSRF قياسية. كلمات المرور بـ **Argon2id** (`argon2-cffi`) كـ Hasher أول. `active_school_id` يعيش في الجلسة. Rate limiting على الدخول (جوال + IP) عبر Redis.
- **التبعات:** إبطال الجلسات فوري من الخادم؛ لو احتجنا عملاء API خارجيين مستقبلًا نضيف Token Auth منفصلًا بقرار جديد دون المساس بمصادقة الويب.
