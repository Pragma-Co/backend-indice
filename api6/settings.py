"""
Django settings for the API-6 project.

All sensitive values are read from environment variables (see .env),
so no credential is ever hard-coded in the repository (LGPD).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-placeholder-only-for-local-tooling"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

# Browser origins allowed to call this API directly (the Vue.js frontend).
# Restricted to the local dev server by default — never use a wildcard (LGPD).
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "api6.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "api6.wsgi.application"

# Relational database: PostgreSQL

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "api6"),
        "USER": os.environ.get("POSTGRES_USER", "api6_admin"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5433"),
        # Connection pool (psycopg 3). Connections are reused instead of being
        # opened per request. CONN_MAX_AGE must stay at its default of 0:
        # Django refuses to combine pooling with persistent connections.
        "OPTIONS": {
            "pool": {
                "min_size": int(os.environ.get("POSTGRES_POOL_MIN_SIZE", "2")),
                "max_size": int(os.environ.get("POSTGRES_POOL_MAX_SIZE", "10")),
                # Seconds a query waits for a free connection before failing
                "timeout": float(os.environ.get("POSTGRES_POOL_TIMEOUT", "10")),
            }
        },
    }
}

# Non-relational database: MongoDB (accessed through pymongo, see core/mongo.py).
# Kept as individual settings instead of an assembled URI: Django's debug-page
# filter masks any setting whose name contains PASS, but would show a full URI.

MONGO_DB_NAME = os.environ.get("MONGO_DB", "api6")
MONGO_USER = os.environ.get("MONGO_USER", "api6_admin")
MONGO_PASSWORD = os.environ.get("MONGO_PASSWORD", "")
MONGO_HOST = os.environ.get("MONGO_HOST", "localhost")
MONGO_PORT = os.environ.get("MONGO_PORT", "27018")

# Authentication: the application's own user model (table `app_user`), which
# logs in by email instead of username. Staff/superuser status is derived from
# the user's role — see core/models/organization.py.

AUTH_USER_MODEL = "core.User"
MAX_UPLOAD_SIZE_BYTES = int(
    os.environ.get("MAX_UPLOAD_SIZE_BYTES", 100 * 1024 * 1024)
)
TEMP_UPLOAD_DIR = Path(
    os.environ.get("TEMP_UPLOAD_DIR", BASE_DIR / "tmp_uploads")
)

# Password validation (also part of a healthy LGPD posture)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
