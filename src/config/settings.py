"""Centralized configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from typing import Optional, List


class Settings(BaseSettings):
    # Required in all environments
    secret_key: str = Field(
        default="dev-secret-key-change-in-production-min-32-characters-long",
        description="JWT signing secret (32+ chars)"
    )
    
    # Database - required in production, SQLite default for local dev
    database_url: str = Field(
        default="sqlite:///local.db",
        description="PostgreSQL connection string for production"
    )
    
    # External services
    resend_api_key: Optional[str] = Field(default=None, description="Resend API key for fallback emails")
    resend_from_email: str = Field(default="reminders@yourinboxhero.com", description="Default From address for Resend sends")
    ghl_api_key: Optional[str] = Field(default=None, description="GoHighLevel API key for SMS/Voice")
    ghl_location_id: Optional[str] = Field(default=None, description="GoHighLevel location ID")
    
    # Azure / Monitoring
    applicationinsights_connection_string: Optional[str] = Field(default=None)
    
    # Feature flags
    unleash_url: Optional[str] = Field(default=None, description="Unleash feature flag service URL")
    
    # Queue (legacy/unused currently)
    service_bus_connection_string: Optional[str] = Field(default=None)
    reminder_queue_name: str = Field(default="reminder-queue")
    
    # Stripe (payment/subscription processing)
    stripe_secret_key: Optional[str] = Field(default=None)
    stripe_webhook_secret: Optional[str] = Field(default=None, description="Signing secret for verifying Stripe webhook events")
    stripe_success_url: str = Field(default="http://localhost:5173/payment-success", description="Redirect after successful Checkout")
    stripe_cancel_url: str = Field(default="http://localhost:5173/", description="Redirect if Checkout is cancelled")
    
    # Environment
    environment: str = Field(default="development", description="development|staging|production")
    
    # CORS
    cors_origins: List[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        description="Allowed CORS origins"
    )
    
    # Database pool settings
    db_pool_size: int = Field(default=10, description="SQLAlchemy pool size")
    db_max_overflow: int = Field(default=20, description="SQLAlchemy max overflow")
    db_pool_recycle: int = Field(default=3600, description="Connection recycle seconds")
    db_pool_pre_ping: bool = Field(default=True, description="Validate connections before use")
    
    # Reminder settings
    reminders_enabled: bool = Field(default=True, description="Global reminder toggle")
    email_lookahead_days: int = Field(default=14, description="Days ahead to send pre-due reminders")
    email_to_sms_days: int = Field(default=15, description="Days before email→SMS escalation")
    sms_to_voice_days: int = Field(default=7, description="Days before SMS→Voice escalation")

    # Stripe Price IDs — created in the Stripe Dashboard (Products > Pricing).
    # Each must be a recurring monthly price matching the plan's advertised amount.
    stripe_price_starter: Optional[str] = Field(default=None, description="Stripe Price ID for the Starter plan ($149/mo)")
    stripe_price_growth: Optional[str] = Field(default=None, description="Stripe Price ID for the Growth plan ($299/mo)")
    stripe_price_scale: Optional[str] = Field(default=None, description="Stripe Price ID for the Scale plan ($497/mo)")

    # Comma-separated emails allowed to register without a completed Stripe
    # payment — for admin/support/test accounts only. Never expose publicly.
    admin_emails: str = Field(default="", description="Comma-separated emails exempt from the paid-plan registration gate")

    # A single shared secret that also bypasses the paid-plan registration
    # gate, for handing out to testers (managers, colleagues, QA) without
    # maintaining an allowlist of their individual emails. Unset by default
    # (empty string never matches a submitted code, even an empty one).
    test_invite_code: str = Field(default="", description="Shared invite code exempt from the paid-plan registration gate")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def is_admin_email(self, email: str) -> bool:
        admins = {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}
        return email.strip().lower() in admins

    def is_valid_invite_code(self, code: Optional[str]) -> bool:
        # No code configured, or nothing submitted, never matches — an
        # empty TEST_INVITE_CODE must not silently accept an empty string.
        if not self.test_invite_code or not code:
            return False
        import hmac
        return hmac.compare_digest(code.strip(), self.test_invite_code)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for dependency injection."""
    return Settings()


def validate_production_settings(settings: Settings) -> None:
    """Validate required settings for production deployment."""
    if settings.environment in ("production", "staging"):
        if not settings.secret_key or settings.secret_key.startswith("dev-"):
            raise RuntimeError("SECRET_KEY must be set to a secure value in production")
        if settings.database_url.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must be PostgreSQL in production")
        if not settings.resend_api_key:
            raise RuntimeError("RESEND_API_KEY required in production")
        if settings.cors_origins == ["http://localhost:5173", "http://localhost:3000"]:
            raise RuntimeError("CORS_ORIGINS must include production frontend domain")