"""
session_manager.py — Manages LinkedIn authentication cookies.

Option B (Manual Cookie Injection):
  Cookies are read directly from environment variables (LI_AT, JSESSIONID).
  The user logs in once in their browser, copies the values, and sets them
  as env vars on Render. They are valid for ~1 year.

No browser is launched. No password is stored.
"""

import re
from app.config import settings


class SessionManager:
    """Wraps the LinkedIn session cookies loaded from environment variables."""

    def get_cookie_header(self) -> str:
        """
        Build the Cookie header string for HTTP requests to LinkedIn.
        """
        # If the user provided a full raw Cookie header from DevTools, use it directly
        if settings.cookie_header:
            return settings.cookie_header.strip()

        parts = []
        if settings.li_at:
            parts.append(f"li_at={settings.li_at.strip()}")
        if settings.jsessionid:
            js = settings.jsessionid.strip()
            # Ensure JSESSIONID is enclosed in quotes if not already
            if not js.startswith('"'):
                js = f'"{js}"'
            parts.append(f"JSESSIONID={js}")
        if settings.bcookie:
            parts.append(f"bcookie={settings.bcookie.strip()}")

        return "; ".join(parts)

    def get_csrf_token(self) -> str:
        """
        Derive the CSRF token from JSESSIONID.
        """
        if settings.jsessionid:
            return settings.jsessionid.strip('"').strip()

        # If full cookie_header was provided, extract JSESSIONID via regex
        if settings.cookie_header:
            match = re.search(r'JSESSIONID="?([^";]+)"?', settings.cookie_header)
            if match:
                return match.group(1).strip()

        return ""

    def is_configured(self) -> bool:
        """Return True if session cookies are present."""
        if settings.cookie_header and "li_at=" in settings.cookie_header:
            return True
        return bool(settings.li_at and settings.jsessionid)


# Singleton — one shared instance across the app lifecycle
session_manager = SessionManager()
