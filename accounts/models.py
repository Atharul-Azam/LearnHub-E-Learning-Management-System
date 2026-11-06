from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, name, password, **extra):
        if not email:
            raise ValueError("An e-mail address is required.")
        user = self.model(email=self.normalize_email(email).lower(), name=name, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, name, password=None, role="student", status=None, **extra):
        if status is None:
            # DD 6.1: students become Active, teachers wait as Pending.
            status = User.Status.PENDING if role == User.Role.TEACHER else User.Status.ACTIVE
        return self._create(email, name, password, role=role, status=status, **extra)

    def create_superuser(self, email, name, password=None, **extra):
        extra.update(role=User.Role.ADMIN, status=User.Status.ACTIVE, is_superuser=True)
        return self._create(email, name, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Single user table covering the Admin, Teacher and Student roles (DD Fig-19)."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Administrator"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        REJECTED = "rejected", "Rejected"
        DEACTIVATED = "deactivated", "Deactivated"

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, db_index=True)
    date_joined = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="decisions_made"
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name", "email"]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    # Only Active accounts may authenticate (DD 6.1). Django's ModelBackend and
    # session loading honour this property, so deactivating an account also
    # ends that user's existing sessions on their next request.
    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT
