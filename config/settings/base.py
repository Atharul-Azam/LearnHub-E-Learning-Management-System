"""Settings shared by every environment. See dev.py / prod.py for overrides."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

try:  # python-dotenv is optional; plain environment variables also work.
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "accounts",
    "courses",
    "materials",
    "assignments",
    "progress",
    "dashboards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# Database (SQLite, as required by the Detailed Design Document)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboards:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# SRS 22.2: at least 8 characters, combining letters and numbers.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "accounts.validators.LetterAndNumberValidator"},
]

# --------------------------------------------------------------------------
# Sessions (SRS 21.5: configurable inactivity timeout)
# SESSION_SAVE_EVERY_REQUEST renews the expiry on every request, so the
# session ends only after SESSION_COOKIE_AGE seconds without any request.
# --------------------------------------------------------------------------
CSRF_FAILURE_VIEW = "core.views.csrf_failure"
SESSION_COOKIE_AGE = env_int("SESSION_INACTIVITY_TIMEOUT_SECONDS", 30 * 60)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Dhaka")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static and media files
# Media files are NEVER mapped to a public URL: they are served only through
# the permission-checked views in core/files.py.
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"  # required by Django's storage API; intentionally not routed
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

# --------------------------------------------------------------------------
# Upload rules (SRS 9.2, 10.3, 19.2, 22.5) - configurable via environment.
# --------------------------------------------------------------------------
MB = 1024 * 1024
_DOCUMENT_TYPES = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "txt", "zip"}
_IMAGE_TYPES = {"jpg", "jpeg", "png"}

UPLOAD_RULES = {
    "thumbnail": {
        "extensions": {"jpg", "jpeg", "png", "gif", "webp"},
        "max_bytes": env_int("MAX_THUMBNAIL_MB", 2) * MB,
    },
    "material": {
        "extensions": _DOCUMENT_TYPES | {"mp4"},
        "max_bytes": env_int("MAX_MATERIAL_MB", 50) * MB,
    },
    "attachment": {
        "extensions": _DOCUMENT_TYPES | _IMAGE_TYPES,
        "max_bytes": env_int("MAX_ATTACHMENT_MB", 20) * MB,
    },
    "submission": {
        "extensions": _DOCUMENT_TYPES | _IMAGE_TYPES,
        "max_bytes": env_int("MAX_SUBMISSION_MB", 20) * MB,
    },
}
# Extensions a browser may display inline. Everything else is always downloaded.
INLINE_EXTENSIONS = {"pdf", "txt", "png", "jpg", "jpeg", "gif", "webp", "mp4"}

PAGE_SIZE = env_int("PAGE_SIZE", 12)

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "learnhub": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
        "django.request": {"handlers": ["console"], "level": "WARNING"},
    },
}

ADMINS = []
