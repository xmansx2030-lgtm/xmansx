from django.contrib.auth.models import BaseUserManager

from accounts.mobile import normalize_mobile


class UserManager(BaseUserManager):
    """مدير المستخدم المخصص — الجوال هو المعرف، ويطبّع دائمًا قبل الحفظ."""

    use_in_migrations = True

    def _create_user(self, mobile: str, password: str | None, **extra_fields):
        if not mobile:
            raise ValueError("رقم الجوال مطلوب")
        mobile = normalize_mobile(mobile)
        user = self.model(mobile=mobile, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, mobile: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(mobile, password, **extra_fields)

    def create_superuser(self, mobile: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(mobile, password, **extra_fields)

    def get_by_natural_key(self, username: str):
        # يسمح بتسجيل الدخول بأي صيغة إدخال — التطبيع قبل البحث
        return self.get(mobile=normalize_mobile(username))
