"""
conftest.py — Shared pytest configuration and fixtures.

Sets dummy LinkedIn cookie env vars so pydantic-settings can
instantiate Settings() during tests without a real .env file.
"""

import os

# These must be set before any app module is imported.
# pytest loads conftest.py before collecting tests, so this is the right place.
os.environ.setdefault("LI_AT", "test_li_at_value")
os.environ.setdefault("JSESSIONID", '"ajax:test_jsessionid"')
