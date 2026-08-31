"""
profile.py — API routes for profile scraping and health check.

Endpoints:
  POST /api/profile   — Scrape a LinkedIn profile, return structured JSON
  GET  /health        — Liveness check (also shows if cookies are configured)
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import settings
from app.linkedin.profile_parser import parse_profile
from app.linkedin.session_manager import session_manager
from app.linkedin.voyager_client import (
    LinkedInAccessDeniedError,
    LinkedInAPIError,
    LinkedInProfileNotFoundError,
    LinkedInRateLimitError,
    LinkedInSessionExpiredError,
    voyager_client,
)
from app.models import ErrorResponse, ProfileRequest, ProfileResponse
from app.utils.rate_limiter import rate_limiter
from app.utils.url_parser import extract_username

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Optional API key auth ─────────────────────────────────────────────────────

async def verify_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    Dependency: validate bearer token if API_KEY is configured.

    If API_KEY env var is not set, the API is open (no auth required).
    If it is set, all /api/profile requests must include:
      Authorization: Bearer <api_key>
    """
    if not settings.api_key:
        return  # API_KEY not configured → open access

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required (Bearer token).",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )


# ── Routes ────────────────────────────────────────────────────────────────────

from app.linkedin.public_scraper import public_scraper


@router.post(
    "/api/profile",
    response_model=ProfileResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid LinkedIn URL"},
        401: {"model": ErrorResponse, "description": "Missing API key"},
        403: {"model": ErrorResponse, "description": "Invalid API key"},
        404: {"model": ErrorResponse, "description": "Profile not found or private"},
        429: {"model": ErrorResponse, "description": "Rate limited by LinkedIn"},
    },
    summary="Scrape a LinkedIn profile",
    description=(
        "Accepts a LinkedIn profile URL and returns structured JSON containing "
        "all publicly available profile data: name, headline, location, about, "
        "experience, education, skills, certifications, languages, and images."
    ),
)
async def get_profile(
    body: ProfileRequest,
    _: None = Depends(verify_api_key),
) -> ProfileResponse:
    # ── 1. Extract username from URL ──────────────────────────────────────────
    username = extract_username(body.url)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract a LinkedIn username from the provided URL. "
                   "Expected format: https://www.linkedin.com/in/<username>",
        )

    logger.info("Scraping profile: %s", username)

    # ── 2. Throttle requests to avoid hammering LinkedIn ──────────────────────
    await rate_limiter.wait()

    # ── 3. Attempt Voyager API (if cookies configured) ───────────────────────
    if session_manager.is_configured():
        try:
            logger.info("Attempting Voyager API fetch for %s", username)
            raw_data = await voyager_client.fetch_profile(username)
            profile = parse_profile(raw_data, username)
            logger.info("Successfully scraped profile via Voyager: %s", username)
            return profile
        except (LinkedInSessionExpiredError, LinkedInAccessDeniedError, LinkedInAPIError) as exc:
            logger.warning(
                "Voyager API failed (%s), falling back to Public Guest Scraper for %s",
                exc,
                username,
            )
        except LinkedInRateLimitError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
            )
        except LinkedInProfileNotFoundError:
            pass  # Try public scraper as fallback

    # ── 4. Fallback: Public Guest Scraper (0 cookies required) ───────────────
    logger.info("Fetching profile via Public Guest Scraper for %s", username)
    html = await public_scraper.fetch_html(username)
    if html:
        profile = public_scraper.parse_profile(html, username)
        if profile.name:
            logger.info("Successfully scraped profile via Public Guest Engine: %s", username)
            return profile

    # ── 5. Profile not accessible ─────────────────────────────────────────────
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"LinkedIn profile '{username}' was not found or is private.",
    )


@router.get(
    "/health",
    summary="Health check",
    description="Returns service status and whether LinkedIn cookies are configured.",
)
async def health_check() -> dict:
    return {
        "status": "ok",
        "session_configured": session_manager.is_configured(),
        "api_key_required": bool(settings.api_key),
    }
