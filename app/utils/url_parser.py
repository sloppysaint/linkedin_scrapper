"""
url_parser.py — Extract the LinkedIn public username from a profile URL.

Handles all common LinkedIn URL formats:
  https://www.linkedin.com/in/username
  https://linkedin.com/in/username/
  http://www.linkedin.com/in/username?trk=...
  linkedin.com/in/username
"""

import re
from typing import Optional

# Matches any LinkedIn /in/<username> URL regardless of scheme, subdomain,
# trailing slash, or query parameters.
_LINKEDIN_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9_%-]+)/?",
    re.IGNORECASE,
)


def extract_username(url: str) -> Optional[str]:
    """
    Return the public identifier (username) from a LinkedIn profile URL,
    or None if the URL does not match the expected pattern.

    Examples:
        extract_username("https://www.linkedin.com/in/satyanadella/")
        → "satyanadella"

        extract_username("https://linkedin.com/in/john-doe?trk=public")
        → "john-doe"

        extract_username("https://linkedin.com/company/google")
        → None
    """
    match = _LINKEDIN_URL_RE.search(url.strip())
    return match.group(1) if match else None
