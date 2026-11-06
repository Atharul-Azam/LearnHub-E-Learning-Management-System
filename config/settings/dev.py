"""Development settings (default for manage.py)."""
from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_list

DEBUG = env_bool("DEBUG", True)
SECRET_KEY = env("SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production")
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
