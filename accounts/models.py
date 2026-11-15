from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from core.files import avatar_upload_to, connect_file_cleanup


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
        # New accounts must verify their e-mail address (see accounts/verification.py).
        extra.setdefault("email_verified", False)
        user = self._create(email, name, password, role=role, status=status, **extra)
        if user.status == User.Status.ACTIVE:
            from .identifiers import ensure_public_id

            ensure_public_id(user)  # students at registration; teachers when approved
        return user

    def create_superuser(self, email, name, password=None, **extra):
        extra.update(role=User.Role.ADMIN, status=User.Status.ACTIVE, is_superuser=True, email_verified=True)
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

    # --- e-mail verification and public identifier -------------------------
    email_verified = models.BooleanField(default=False)
    # Human-readable Student ID / Teacher ID, e.g. STU-000042 / TCH-000007.
    # Assigned once (students at registration, teachers on approval); never edited.
    public_id = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)

    # --- profile -----------------------------------------------------------
    profile_picture = models.ImageField(upload_to=avatar_upload_to, blank=True)
    bio = models.TextField(blank=True, max_length=1000)
    expertise = models.CharField(max_length=200, blank=True)

    # --- settings ----------------------------------------------------------
    class Theme(models.TextChoices):
        SYSTEM = "system", "System default"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    class Font(models.TextChoices):
        SANS = "sans", "Sans-serif (default)"
        SERIF = "serif", "Serif"
        MONO = "mono", "Monospace"

    theme = models.CharField(max_length=10, choices=Theme.choices, default=Theme.SYSTEM)
    font = models.CharField(max_length=10, choices=Font.choices, default=Font.SANS)
    # In-app notification preferences (no e-mail notifications are sent).
    notify_courses = models.BooleanField("Course and access updates", default=True)
    notify_assignments = models.BooleanField("Assignments, deadlines and marks", default=True)
    notify_discussion = models.BooleanField("Discussion and announcements", default=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name", "email"]
        constraints = [
            # A Student ID starts with STU-, a Teacher ID with TCH-; others have none.
            models.CheckConstraint(
                condition=models.Q(public_id__isnull=True)
                | (models.Q(role="student", public_id__startswith="STU-"))
                | (models.Q(role="teacher", public_id__startswith="TCH-")),
                name="user_public_id_matches_role",
            ),
        ]

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
        return self.status == self.Status.ACTIVE and self.email_verified

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT


connect_file_cleanup(User, "profile_picture")
