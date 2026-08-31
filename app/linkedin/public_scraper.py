"""
public_scraper.py — Scrapes public LinkedIn profile pages without authentication.

How it works (Pure HTTP Reverse Engineering):
─────────────────────────────────────────────────────────────────────────────
When you visit a public LinkedIn profile (e.g. from Google search or in
an incognito browser), LinkedIn renders a public HTML page containing:

1. JSON-LD structured data (<script type="application/ld+json">):
   - schema.org/Person or schema.org/ProfilePage
   - name, headline/jobTitle, current company (worksFor), education (alumniOf),
     profile picture, location (address), summary/description.

2. OpenGraph and Twitter Meta Tags:
   - og:title, og:description, og:image, og:url

3. Public HTML structured DOM:
   - Experience items list
   - Education items list
   - Volunteer experience, languages, etc.

This scraper requires ZERO credentials, ZERO cookies, and NEVER expires.
─────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import unquote

import httpx

from app.models import (
    ContactInfo,
    EducationItem,
    ExperienceItem,
    LanguageItem,
    ProfileResponse,
)

logger = logging.getLogger(__name__)

# Headers mimicking a standard search-engine / guest browser visit
_GUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


class PublicLinkedInScraper:
    """
    Pure HTTP scraper for public LinkedIn profile pages.
    Requires no login credentials.
    """

    async def fetch_html(self, username: str) -> Optional[str]:
        """Fetch raw HTML for a public LinkedIn profile."""
        url = f"https://www.linkedin.com/in/{username}"
        logger.info("Fetching public profile HTML for: %s", username)

        async with httpx.AsyncClient(
            timeout=20.0,
            headers=_GUEST_HEADERS,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.text
            logger.warning(
                "Public profile request returned HTTP %s for %s",
                response.status_code,
                username,
            )
            return None

    def _extract_json_ld(self, html: str) -> list[dict[str, Any]]:
        """Extract all JSON-LD blocks from HTML."""
        json_ld_blocks: list[dict[str, Any]] = []
        pattern = re.compile(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(html):
            content = match.group(1).strip()
            if not content:
                continue
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    json_ld_blocks.extend(data)
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        json_ld_blocks.extend(data["@graph"])
                    else:
                        json_ld_blocks.append(data)
            except Exception as e:
                logger.debug("Failed to parse JSON-LD block: %s", e)
        return json_ld_blocks

    def _extract_meta(self, html: str, name_or_prop: str) -> Optional[str]:
        """Extract content from meta tags."""
        patterns = [
            rf'<meta\s+property=["\']{re.escape(name_or_prop)}["\']\s+content=["\'](.*?)["\']',
            rf'<meta\s+name=["\']{re.escape(name_or_prop)}["\']\s+content=["\'](.*?)["\']',
            rf'<meta\s+content=["\'](.*?)["\']\s+property=["\']{re.escape(name_or_prop)}["\']',
            rf'<meta\s+content=["\'](.*?)["\']\s+name=["\']{re.escape(name_or_prop)}["\']',
        ]
        for p in patterns:
            match = re.search(p, html, re.IGNORECASE | re.DOTALL)
            if match:
                val = match.group(1).strip()
                # Clean HTML entities
                val = val.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
                return val
        return None

    def _extract_connections(self, html: str) -> Optional[int]:
        """Extract connections count from meta description."""
        match = re.search(r'([0-9,]+)\+?\s+connections\b', html, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                pass
        return None

    def _parse_html_cards(self, html: str) -> tuple[list[ExperienceItem], list[EducationItem]]:
        """Extract experience and education cards from public HTML structure."""
        experiences: list[ExperienceItem] = []
        educations: list[EducationItem] = []

        items = re.findall(
            r'<li[^>]*class=["\'][^"\']*profile-section[^"\']*["\'][^>]*>(.*?)</li>',
            html,
            re.DOTALL | re.IGNORECASE,
        )

        for item_html in items:
            # Check for company logo / name in data-delayed-url
            slug_match = re.search(r'company-logo_[^/]+/([^/?&]+)_logo', item_html)
            raw_slug = slug_match.group(1) if slug_match else ""
            clean_company = raw_slug.replace("_", " ").title() if raw_slug else None

            # Extract text lines
            lines = [
                re.sub(r'<[^>]+>', ' ', line).strip()
                for line in item_html.split('\n')
            ]
            clean_lines = [
                l for l in lines
                if l and not l.startswith('<!--') and not l.startswith('*') and not l.startswith('<div')
            ]

            # Look for date patterns (e.g. "1994 - 1996" or "Feb 2014 - Present")
            date_m = re.search(
                r'([A-Za-z]{3}\s+\d{4}|\d{4})\s*-\s*([A-Za-z]{3}\s+\d{4}|\d{4}|Present)',
                item_html,
                re.IGNORECASE,
            )
            start_d = date_m.group(1) if date_m else None
            end_d = date_m.group(2) if date_m else None
            if end_d and end_d.lower() == "present":
                end_d = None

            # Extract clean company / school title
            h3_m = re.search(r'<h3[^>]*>(.*?)</h3>', item_html, re.DOTALL)
            h3_text = None
            if h3_m:
                raw_h3 = re.sub(r'<[^>]+>', ' ', h3_m.group(1))
                # Remove CSS fragments like text-[18px] or font-semibold">
                raw_h3 = re.sub(r'[a-zA-Z0-9_\-\[\]:*]+(?:">|[\s]+)', ' ', raw_h3)
                raw_h3 = ' '.join(raw_h3.split()).strip()
                if raw_h3 and not raw_h3.startswith('*'):
                    h3_text = raw_h3

            display_company = clean_company or h3_text
            if not display_company and h3_m:
                raw_txt = re.sub(r'<[^>]+>', ' ', h3_m.group(1))
                display_company = ' '.join(raw_txt.split()).strip()

            if display_company and not display_company.startswith('*'):
                is_edu = any(k in display_company.lower() for k in ["school", "university", "college", "institute", "academy", "booth"])
                if is_edu:
                    educations.append(
                        EducationItem(school=display_company, start_date=start_d, end_date=end_d)
                    )
                else:
                    experiences.append(
                        ExperienceItem(
                            company=display_company,
                            start_date=start_d,
                            end_date=end_d,
                            is_current=(end_d is None),
                        )
                    )

        return experiences, educations

    def parse_profile(self, html: str, username: str) -> ProfileResponse:
        """
        Parse public HTML into a clean ProfileResponse model.
        """
        json_lds = self._extract_json_ld(html)
        person_obj: dict[str, Any] = {}

        for block in json_lds:
            t = block.get("@type", "")
            if t == "Person" or "Person" in str(t):
                person_obj = block
                break

        if not person_obj:
            for block in json_lds:
                if block.get("@type") == "ProfilePage" and isinstance(
                    block.get("mainEntity"), dict
                ):
                    person_obj = block["mainEntity"]
                    break

        # ── Name ──
        first_meta = self._extract_meta(html, "profile:first_name")
        last_meta = self._extract_meta(html, "profile:last_name")
        if first_meta and last_meta:
            name = f"{first_meta} {last_meta}".strip()
        else:
            name = person_obj.get("name")
            if isinstance(name, list):
                name = " ".join(str(x) for x in name if x)
            if not name:
                og_title = self._extract_meta(html, "og:title")
                if og_title and " | LinkedIn" in og_title:
                    name = og_title.split(" | LinkedIn")[0].strip()
                    if " - " in name:
                        name = name.split(" - ")[0].strip()
                elif og_title:
                    name = og_title

        # ── Headline / Job Title ──
        headline = None
        og_title = self._extract_meta(html, "og:title")
        if og_title and " | LinkedIn" in og_title:
            cleaned = og_title.split(" | LinkedIn")[0].strip()
            if " - " in cleaned:
                # "Satya Nadella - Microsoft" -> "Microsoft"
                headline = cleaned.split(" - ", 1)[1].strip()

        if not headline:
            job = person_obj.get("jobTitle")
            if isinstance(job, str) and "*" not in job:
                headline = job
            elif isinstance(job, list):
                clean_jobs = [j for j in job if isinstance(j, str) and "*" not in j]
                if clean_jobs:
                    headline = " · ".join(clean_jobs)

        if not headline:
            og_desc = self._extract_meta(html, "og:description") or self._extract_meta(
                html, "description"
            )
            if og_desc:
                headline = og_desc.split(" · ")[0].strip() if " · " in og_desc else og_desc

        # ── Location ──
        location = None
        addr = person_obj.get("address")
        if isinstance(addr, dict):
            locality = addr.get("addressLocality")
            region = addr.get("addressRegion")
            country = addr.get("addressCountry")
            parts = [p for p in [locality, region, country] if p]
            if parts:
                location = ", ".join(parts)
        elif isinstance(addr, str):
            location = addr

        if not location:
            loc_m = re.search(r'Location:\s*([^·]+)', html, re.IGNORECASE)
            if loc_m:
                location = loc_m.group(1).strip()

        # ── About Summary ──
        about = person_obj.get("description")
        if isinstance(about, list):
            about = " ".join(str(a) for a in about if a)
        if not about:
            og_desc = self._extract_meta(html, "og:description")
            if og_desc and "View " in og_desc:
                about = og_desc.split("View ")[0].strip()

        # ── Profile Picture ──
        picture_url = None
        img = person_obj.get("image")
        if isinstance(img, dict):
            picture_url = img.get("contentUrl") or img.get("url")
        elif isinstance(img, str):
            picture_url = img

        if not picture_url:
            picture_url = self._extract_meta(html, "og:image")

        # ── Experience & Education ──
        experiences, educations = self._parse_html_cards(html)

        # Fallback to JSON-LD worksFor / alumniOf if HTML cards were empty
        if not experiences:
            works_for = person_obj.get("worksFor")
            if isinstance(works_for, list):
                for wf in works_for:
                    if isinstance(wf, dict) and wf.get("name") and "*" not in wf["name"]:
                        experiences.append(
                            ExperienceItem(company=wf.get("name"), is_current=True)
                        )
            elif isinstance(works_for, dict) and works_for.get("name") and "*" not in works_for["name"]:
                experiences.append(
                    ExperienceItem(company=works_for.get("name"), is_current=True)
                )

        if not educations:
            alumni_of = person_obj.get("alumniOf")
            if isinstance(alumni_of, list):
                for al in alumni_of:
                    if isinstance(al, dict) and al.get("name"):
                        educations.append(EducationItem(school=al.get("name")))
            elif isinstance(alumni_of, dict) and alumni_of.get("name"):
                educations.append(EducationItem(school=alumni_of.get("name")))

        # ── Connections ──
        connections = self._extract_connections(html)

        return ProfileResponse(
            username=username,
            name=name,
            headline=headline,
            location=location,
            about=about,
            profile_picture_url=picture_url,
            background_image_url=None,
            connections=connections,
            followers=None,
            open_to_work=False,
            experience=experiences,
            education=educations,
            skills=[],
            certifications=[],
            languages=[],
            contact_info=ContactInfo(),
            scraped_at=datetime.now(timezone.utc),
        )


public_scraper = PublicLinkedInScraper()
