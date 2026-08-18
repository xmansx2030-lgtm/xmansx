# دعوات العضوية — كما نفذت في المرحلة 5

## الحالات والانتقالات

```text
(استيراد جوال موجود عالميًا) ──► INVITED ──► accept ──► ACTIVE
                                     │
                                     └──── decline ──► DECLINED ──► reinvite (صريح) ──► INVITED
```

- الدعوة = `SchoolMembership.status=INVITED` مع الأدوار المقترحة على العضوية (TEACHER من الاستيراد).
- **القبول:** INVITED→ACTIVE — العضوية والأدوار تفعل دفعة واحدة (لا قبول لكل دور منفرد في MVP)، والمدرسة تظهر فورًا في الـ Switcher. Audit `SCHOOL_MEMBERSHIP_ACCEPTED`.
- **الرفض:** DECLINED — **لا حذف للسجل**. Audit `SCHOOL_MEMBERSHIP_DECLINED`. (Migration المرحلة 5 أضاف الحالة.)
- **إعادة الدعوة:** الاستيراد لا يعيد دعوة DECLINED بصمت (تصنيف «يتطلب إجراء») — `POST /staff/{id}/reinvite/` إجراء صريح من مدير المدرسة.
- دعوة قائمة + استيراد جديد = لا دعوة ثانية (INVITATION_PENDING).

## واجهات المستخدم المدعو

```text
GET  /api/v1/auth/invitations/               ← دعواته هو فقط
POST /api/v1/auth/invitations/{id}/accept/   ← 409: INVITATION_ALREADY_ACCEPTED
POST /api/v1/auth/invitations/{id}/decline/  ← 409: INVITATION_ALREADY_DECLINED
```

دعوات الآخرين **غير موجودة من منظوره** (404 `INVITATION_NOT_FOUND` — لا تسريب). الدعوات تظهر في `/me` وفي شاشة اختيار المدرسة («دعوات مدارس» قبل القائمة)؛ مستخدم بلا مدرسة فعالة ولديه دعوة لا يرى شاشة فارغة — يرى الدعوة ويدخل فور قبولها.

## Multi-school

سيناريو مثبت بـ E2E: معلم فعال في A، تستورده B → بعد الدخول: A متاحة + دعوة B → قبول → الـ Switcher يحوي A وB بالأدوار الصحيحة لكل مدرسة.
