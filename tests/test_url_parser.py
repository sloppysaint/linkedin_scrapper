"""
test_url_parser.py — Unit tests for the URL parser utility.
"""

import pytest
from app.utils.url_parser import extract_username


class TestExtractUsername:
    def test_standard_https_url(self):
        assert extract_username("https://www.linkedin.com/in/satyanadella") == "satyanadella"

    def test_trailing_slash(self):
        assert extract_username("https://www.linkedin.com/in/satyanadella/") == "satyanadella"

    def test_no_www(self):
        assert extract_username("https://linkedin.com/in/john-doe") == "john-doe"

    def test_http(self):
        assert extract_username("http://www.linkedin.com/in/username123") == "username123"

    def test_with_query_params(self):
        assert extract_username("https://www.linkedin.com/in/user?trk=public_profile") == "user"

    def test_no_scheme(self):
        assert extract_username("linkedin.com/in/noscheme") == "noscheme"

    def test_username_with_hyphens(self):
        assert extract_username("https://www.linkedin.com/in/first-last-123") == "first-last-123"

    def test_company_url_returns_none(self):
        assert extract_username("https://www.linkedin.com/company/google") is None

    def test_empty_string_returns_none(self):
        assert extract_username("") is None

    def test_random_url_returns_none(self):
        assert extract_username("https://google.com") is None

    def test_jobs_url_returns_none(self):
        assert extract_username("https://www.linkedin.com/jobs/view/123456") is None
