"""
voyager_client.py — Pure HTTP client for LinkedIn's internal Voyager API.

How this works (the reverse-engineering explained):
─────────────────────────────────────────────────────────────────────────────
LinkedIn's web frontend talks to its own backend via a private REST API
nicknamed "Voyager". We discovered the endpoints and required headers by:

  1. Opening LinkedIn in Chrome → DevTools (F12) → Network tab
  2. Navigating to a profile page
  3. Filtering XHR/Fetch requests — calls to /voyager/api/identity/profiles/...
  4. Inspecting the request headers sent by the browser

We replicate those exact HTTP calls from our server using httpx.
LinkedIn's servers see a valid authenticated session (because we send the
real li_at + JSESSIONID cookies) and return the profile JSON.

No browser is launched. This is pure HTTP.
─────────────────────────────────────────────────────────────────────────────

Endpoints we call concurrently for each profile:

  /voyager/api/identity/profiles/{username}/profileView
      → name, headline, location, about, photo, experience, education,
        certifications, languages (all in one response)

  /voyager/api/identity/profiles/{username}/networkInfo
      → follower count, connection count

  /voyager/api/identity/profiles/{username}/profileContactInfo
      → email, phone, Twitter, websites (if the user made them public)

  /voyager/api/identity/profiles/{username}/skills?count=100
      → full skills list (profileView only returns featured skills)
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.config import settings
from app.linkedin.session_manager import session_manager

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_VOYAGER_BASE = "https://www.linkedin.com/voyager/api"

# These headers are required for LinkedIn to accept the request as coming
# from an authenticated browser session. They were captured from real browser
# traffic via DevTools.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

# ── Custom Exceptions ─────────────────────────────────────────────────────────

class LinkedInSessionExpiredError(Exception):
    """Raised when LinkedIn returns 401 — cookies are expired."""


class LinkedInAccessDeniedError(Exception):
    """Raised when LinkedIn returns 403 — profile is private or blocked."""


class LinkedInProfileNotFoundError(Exception):
    """Raised when LinkedIn returns 404 — profile does not exist."""


class LinkedInRateLimitError(Exception):
    """Raised when LinkedIn returns 429 or 999 — we are being throttled."""


class LinkedInAPIError(Exception):
    """Generic LinkedIn API error for unexpected status codes."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


# ── Voyager Client ────────────────────────────────────────────────────────────

class VoyagerClient:
    """
    Makes authenticated HTTP requests to LinkedIn's private Voyager REST API.

    Uses LinkedIn's modern Dash endpoints (which replaced the deprecated profileView)
    with backward-compatible fallbacks.
    """

    def _build_headers(self) -> dict[str, str]:
        """
        Merge base headers with session-specific authentication headers.
        """
        ua = settings.user_agent.strip() if settings.user_agent else _DEFAULT_USER_AGENT
        csrf = session_manager.get_csrf_token()
        cookies = session_manager.get_cookie_header()

        headers = {
            "User-Agent": ua,
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "Accept-Language": "en-US,en;q=0.9",
            "x-li-lang": "en_US",
            "x-restli-protocol-version": "2.0.0",
            "Referer": "https://www.linkedin.com/feed/",
            "Origin": "https://www.linkedin.com",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

        if csrf:
            headers["csrf-token"] = csrf
        if cookies:
            headers["Cookie"] = cookies

        return headers

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Perform a single GET request to the Voyager API and return parsed JSON.
        """
        url = f"{_VOYAGER_BASE}{path}"
        logger.debug("GET %s params=%s", url, params)

        response = await client.get(url, params=params)
        status = response.status_code

        logger.debug("Response %s from %s", status, url)

        if status == 200:
            return response.json()

        # LinkedIn's Voyager API uses 999 as a custom "bot detected" code
        if status in (429, 999):
            raise LinkedInRateLimitError(
                f"LinkedIn is rate-limiting requests (HTTP {status}). "
                "Wait a few minutes and try again."
            )
        if status == 401:
            raise LinkedInSessionExpiredError(
                "LinkedIn session expired (HTTP 401). "
                "Update LI_AT and JSESSIONID in your environment variables."
            )
        if status == 403:
            raise LinkedInAccessDeniedError(
                "Access denied (HTTP 403). Profile may be private."
            )
        if status in (404, 410):
            raise LinkedInProfileNotFoundError(
                f"Profile or endpoint not found (HTTP {status})."
            )

        raise LinkedInAPIError(status, f"Unexpected LinkedIn API response: HTTP {status}")

    async def _fetch_dash_profile(
        self, client: httpx.AsyncClient, username: str
    ) -> dict[str, Any]:
        """
        Fetch the full profile using modern Dash decorations.
        Tries modern FullProfileWithEntities decorations in order.
        """
        decorations = [
            "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-35",
            "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-89",
            "com.linkedin.voyager.dash.deco.identity.profile.WebTopCardCore-19",
        ]
        last_error = None
        for deco in decorations:
            try:
                data = await self._get(
                    client,
                    "/identity/dash/profiles",
                    params={
                        "q": "memberIdentity",
                        "memberIdentity": username,
                        "decorationId": deco,
                    },
                )
                if data:
                    return data
            except (LinkedInProfileNotFoundError, LinkedInAPIError) as exc:
                last_error = exc
                continue

        # Fallback to legacy endpoint if dash decorations failed
        try:
            return await self._get(client, f"/identity/profiles/{username}/profileView")
        except Exception:
            if last_error:
                raise last_error
            raise LinkedInProfileNotFoundError(f"Could not load profile for '{username}'.")

    async def fetch_profile(self, username: str) -> dict[str, Any]:
        """
        Fetch all available profile data by calling Voyager endpoints concurrently.

        Args:
            username: LinkedIn public identifier (e.g. "satyanadella")

        Returns:
            dict with keys: dash_profile, network_info, contact_info, skills
        """
        async with httpx.AsyncClient(
            timeout=settings.request_timeout,
            follow_redirects=True,
        ) as client:
            headers = self._build_headers()
            client.headers.update(headers)

            # Fire supplementary calls concurrently alongside main profile
            results = await asyncio.gather(
                # 1. Main profile (Dash with FullProfileWithEntities)
                self._fetch_dash_profile(client, username),

                # 2. networkInfo — follower + connection counts
                self._get(client, f"/identity/profiles/{username}/networkInfo"),

                # 3. profileContactInfo — email, phone, Twitter, websites
                self._get(client, f"/identity/profiles/{username}/profileContactInfo"),

                # 4. skills endpoint
                self._get(
                    client,
                    f"/identity/profiles/{username}/skills",
                    params={"count": 100, "start": 0},
                ),

                return_exceptions=True,
            )

        dash_profile, network_info, contact_info, skills = results

        # Main profile must succeed
        if isinstance(dash_profile, Exception):
            raise dash_profile

        # Tolerable failures for supplementary endpoints
        for name, result in [
            ("networkInfo", network_info),
            ("contactInfo", contact_info),
            ("skills", skills),
        ]:
            if isinstance(result, Exception):
                logger.warning("Optional endpoint %s failed: %s", name, result)

        return {
            "dash_profile": dash_profile,
            "profile_view": dash_profile,  # backwards compatibility
            "network_info": network_info if not isinstance(network_info, Exception) else {},
            "contact_info": contact_info if not isinstance(contact_info, Exception) else {},
            "skills": skills if not isinstance(skills, Exception) else {},
        }


# Singleton
voyager_client = VoyagerClient()
