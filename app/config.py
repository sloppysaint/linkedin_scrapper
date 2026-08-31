"""
config.py — Application settings loaded from environment variables.

Credentials are NEVER hard-coded here; they live in environment variables
set via Render's secret store (production) or a local .env file (development).
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LinkedIn session cookies (Optional) ──────────────────────────────────
    # Option 1: Individual tokens
    li_at: str | None = Field(None, description="LinkedIn li_at session cookie value")
    jsessionid: str | None = Field(None, description="LinkedIn JSESSIONID cookie value")
    bcookie: str | None = Field(None, description="LinkedIn bcookie browser tracking cookie")

    # Option 2: Full Cookie header copied directly from DevTools Network tab
    cookie_header: str | None = Field(None, description="Full raw Cookie header from browser")

    # ── Browser Fingerprint matching ──────────────────────────────────────────
    # Using the matching User-Agent prevents LinkedIn from flagging session hijacking
    user_agent: str | None = Field(
        None,
        description="Browser User-Agent that created the session",
    )

    # ── Optional API protection ───────────────────────────────────────────────
    # If set, callers must include: Authorization: Bearer <api_key>
    api_key: str | None = Field(None, description="Bearer token to protect this API")

    # ── Scraper behaviour ─────────────────────────────────────────────────────
    request_timeout: float = Field(30.0, description="HTTP timeout in seconds for LinkedIn calls")


settings = Settings()
