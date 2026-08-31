"""
test_api.py — Integration tests for the FastAPI endpoints.

Uses FastAPI's TestClient to test the HTTP layer without real LinkedIn calls.
LinkedIn calls are mocked so tests run offline.

NOTE: We set dummy env vars BEFORE importing app modules so pydantic-settings
can instantiate Settings() without a real .env file during CI / local testing.
"""

import os

# Must be set before any app module is imported (pydantic-settings reads env at import time)
os.environ.setdefault("LI_AT", "test_li_at_value")
os.environ.setdefault("JSESSIONID", '"ajax:test_jsessionid"')

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.models import ContactInfo, ProfileResponse

client = TestClient(app)


def _mock_profile() -> ProfileResponse:
    return ProfileResponse(
        username="testuser",
        name="Test User",
        headline="Engineer",
        location="San Francisco, CA",
        about="About me.",
        profile_picture_url="https://media.linkedin.com/pic.jpg",
        background_image_url=None,
        connections=300,
        followers=1000,
        open_to_work=False,
        experience=[],
        education=[],
        skills=["Python", "FastAPI"],
        certifications=[],
        languages=[],
        contact_info=ContactInfo(),
        scraped_at=datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "session_configured" in data


class TestRootEndpoint:
    def test_root_returns_info(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()


class TestProfileEndpoint:
    def test_invalid_url_returns_400(self):
        response = client.post("/api/profile", json={"url": "https://google.com"})
        assert response.status_code == 422  # Pydantic validation error

    def test_non_linkedin_url_returns_422(self):
        response = client.post("/api/profile", json={"url": "not a url at all"})
        assert response.status_code == 422

    @patch("app.routers.profile.voyager_client")
    @patch("app.routers.profile.rate_limiter")
    def test_valid_profile_url(self, mock_rate_limiter, mock_voyager):
        mock_rate_limiter.wait = AsyncMock(return_value=None)
        mock_voyager.fetch_profile = AsyncMock(return_value={
            "profile_view": {
                "profile": {
                    "firstName": "Test",
                    "lastName": "User",
                    "headline": "Engineer",
                    "locationName": "SF",
                    "summary": "About.",
                    "miniProfile": {"publicIdentifier": "testuser"},
                },
                "positionView": {"elements": []},
                "educationView": {"elements": []},
                "certificationView": {"elements": []},
                "languageView": {"elements": []},
                "skillView": {"elements": []},
            },
            "network_info": {},
            "contact_info": {},
            "skills": {"elements": []},
        })

        response = client.post(
            "/api/profile",
            json={"url": "https://www.linkedin.com/in/testuser"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["name"] == "Test User"
