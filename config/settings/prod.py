"""Production settings. SECRET_KEY and ALLOWED_HOSTS are mandatory."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_int, env_list

DEBUG = False

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("The SECRET_KEY environment variable must be set in production.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("The ALLOWED_HOSTS environment variable must be set in production.")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# HTTPS hardening (SRS 22.3). These are ON by default; set USE_HTTPS=False only
# for a trial run over plain HTTP. HTTPS itself must be terminated by the web
# server / reverse proxy - see README "Deployment".
USE_HTTPS = env_bool("USE_HTTPS", True)
SECURE_SSL_REDIRECT = USE_HTTPS
SESSION_COOKIE_SECURE = USE_HTTPS
CSRF_COOKIE_SECURE = USE_HTTPS
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000) if USE_HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = USE_HTTPS
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
if env_bool("BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
