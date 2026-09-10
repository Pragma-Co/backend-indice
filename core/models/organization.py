"""Areas and users — the organizational backbone of the document library."""

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Now

from core.models.choices import Role


class Area(models.Model):
    """An engineering area (department). Owns users and classifies documents."""

    acronym = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=120, unique=True)
    manager = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_area",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    class Meta:
        db_table = "area"
        ordering = ["acronym"]

    def __str__(self):
        return f"{self.acronym} — {self.name}"


class UserManager(BaseUserManager):
    """Manager for the email-as-login user model."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("A user requires an email address.")
        if not extra_fields.get("area") and not extra_fields.get("area_id"):
            raise ValueError("A user requires an area.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        # set_password hashes with the configured Django hasher; the plain
        # password never reaches the database (LGPD)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        if extra_fields["role"] != Role.ADMIN:
            raise ValueError("A superuser must have role ADMIN.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    """Application user. Table is `app_user`: `user` is reserved in PostgreSQL.

    Staff/superuser status is derived from `role` instead of being stored, so
    the table carries no permission column beyond the role itself.
    """

    # Inherited from AbstractBaseUser, re-declared only to name the column
    # `password_hash` — the value is always a Django hash, never a password.
    password = models.CharField(max_length=128, db_column="password_hash")
    # Django's auth app skips the "update last login" receiver when the user
    # model has no such field, so dropping it keeps the table as modelled.
    last_login = None

    email = models.EmailField(max_length=254, unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.VIEWER)
    # RESTRICT: an area with members cannot be deleted
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="members")
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    # Users are deactivated, never deleted, so authorship and audit stay intact
    is_active = models.BooleanField(default=True, db_column="active")
    created_at = models.DateTimeField(db_default=Now(), editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name", "area"]

    class Meta:
        db_table = "app_user"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                # equivalent to position('@' in email) > 1
                condition=models.Q(email__contains="@") & ~models.Q(email__startswith="@"),
                name="ck_app_user_email_has_at",
            ),
            models.CheckConstraint(
                # equivalent to length(btrim(name)) > 0
                condition=models.Q(name__regex=r"\S"),
                name="ck_app_user_name_not_blank",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=Role.values),
                name="ck_app_user_role",
            ),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    @property
    def is_staff(self):
        """Access to the Django admin."""
        return self.role == Role.ADMIN

    @property
    def is_superuser(self):
        return self.role == Role.ADMIN

    def has_perm(self, perm, obj=None):
        return self.is_active and self.role == Role.ADMIN

    def has_module_perms(self, app_label):
        return self.is_active and self.role == Role.ADMIN
