"""Environment-driven configuration. Nothing secret is hardcoded for production."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # backend/.env for local runs; real environments inject variables directly

_DEV_SECRET = "dev-insecure-secret-change-me"


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _db_url(url: str) -> str:
    """Managed hosts (Render, Heroku...) hand out postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg3 driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Config:
    ENV = os.environ.get("APP_ENV", "development")
    DEBUG = ENV == "development"
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
    JWT_SECRET = os.environ.get("JWT_SECRET", _DEV_SECRET + "-jwt")
    ADMIN_JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", _DEV_SECRET + "-admin-jwt")
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")  # urlsafe base64 32 bytes (Fernet)

    SQLALCHEMY_DATABASE_URI = _db_url(os.environ.get("DATABASE_URL", "postgresql+psycopg://crm_app:crm_app_dev@localhost:5432/crm"))
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", REDIS_URL)
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "600 per minute")

    WEB_ORIGIN = os.environ.get("WEB_ORIGIN", "http://localhost:3000")
    ADMIN_ORIGIN = os.environ.get("ADMIN_ORIGIN", "http://localhost:3001")
    API_ORIGIN = os.environ.get("API_ORIGIN", "http://localhost:5000")

    # Auth
    ACCESS_TOKEN_MINUTES = _int("ACCESS_TOKEN_MINUTES", 15)
    REFRESH_TOKEN_DAYS = _int("REFRESH_TOKEN_DAYS", 30)
    ADMIN_ACCESS_TOKEN_MINUTES = _int("ADMIN_ACCESS_TOKEN_MINUTES", 10)
    ADMIN_SESSION_HOURS = _int("ADMIN_SESSION_HOURS", 8)
    COOKIE_SECURE = _bool("COOKIE_SECURE", False)
    COOKIE_DOMAIN = os.environ.get("COOKIE_DOMAIN") or None
    REQUIRE_EMAIL_VERIFICATION = _bool("REQUIRE_EMAIL_VERIFICATION", False)
    ADMIN_REQUIRE_2FA = _bool("ADMIN_REQUIRE_2FA", False)
    # Reverse proxies in front of the API whose X-Forwarded-* headers to trust (client IPs drive rate limits and the admin allow-list).
    # 1 = a load balancer in front of the API. 2 = load balancer + the Next.js apps that proxy /api (e.g. Render with a private API).
    TRUSTED_PROXY_HOPS = _int("TRUSTED_PROXY_HOPS", 1)
    ADMIN_ALLOWED_IPS = [i for i in os.environ.get("ADMIN_ALLOWED_IPS", "").split(",") if i]
    MAX_FAILED_LOGINS = _int("MAX_FAILED_LOGINS", 5)
    LOCKOUT_MINUTES = _int("LOCKOUT_MINUTES", 15)
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # Providers (all swappable behind service interfaces)
    BILLING_PROVIDER = os.environ.get("BILLING_PROVIDER", "mock")  # mock | stripe | razorpay
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    AI_PROVIDER = os.environ.get("AI_PROVIDER", "mock")  # mock | anthropic | openai
    AI_MODEL = os.environ.get("AI_MODEL", "")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "console")  # console | smtp | resend
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "CRM Wala <no-reply@crmwala.local>")
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = _int("SMTP_PORT", 587)
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")

    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")  # local | s3
    STORAGE_LOCAL_DIR = os.environ.get("STORAGE_LOCAL_DIR", os.path.join(os.getcwd(), "uploads"))
    S3_BUCKET = os.environ.get("S3_BUCKET", "")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL") or None
    S3_REGION = os.environ.get("S3_REGION", "auto")
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 25)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    ALLOWED_UPLOAD_MIME = {
        "application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp", "text/plain", "text/csv",
        "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }

    JOBS_TOKEN = os.environ.get("JOBS_TOKEN", "")  # enables POST /api/v1/internal/run-jobs for external schedulers
    CELERY_ALWAYS_EAGER = _bool("CELERY_ALWAYS_EAGER", False)
    SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    DEMO_SEED_ENABLED = _bool("DEMO_SEED_ENABLED", ENV != "production")

    @classmethod
    def validate_for_production(cls) -> None:
        problems = []
        for name in ("SECRET_KEY", "JWT_SECRET", "ADMIN_JWT_SECRET"):
            if _DEV_SECRET in getattr(cls, name) or len(getattr(cls, name)) < 32:
                problems.append(f"{name} must be set to a strong random value")
        if not cls.ENCRYPTION_KEY:
            problems.append("ENCRYPTION_KEY must be set (Fernet key)")
        if not cls.COOKIE_SECURE:
            problems.append("COOKIE_SECURE must be true")
        if not cls.ADMIN_REQUIRE_2FA:
            problems.append("ADMIN_REQUIRE_2FA must be true")
        if cls.BILLING_PROVIDER == "mock":
            problems.append("BILLING_PROVIDER=mock is not allowed in production")
        if problems:
            raise RuntimeError("Unsafe production configuration:\n - " + "\n - ".join(problems))


class TestConfig(Config):
    ENV = "test"
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://crm_app:crm_app_dev@localhost:5432/crm_test"
    )
    RATELIMIT_ENABLED = False
    CELERY_ALWAYS_EAGER = True
    REQUIRE_EMAIL_VERIFICATION = False
    BILLING_PROVIDER = "mock"
    EMAIL_PROVIDER = "console"
    SERVER_NAME = None
    ENCRYPTION_KEY = "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMzItYnl0ZXM="
