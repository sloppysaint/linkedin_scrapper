"""
profile_parser.py — Maps raw LinkedIn Voyager JSON → clean Pydantic models.

LinkedIn's internal API returns deeply nested JSON with internal URNs,
polymorphic keys like "com.linkedin.common.VectorImage", and optional
fields everywhere. This module normalises all of that into our flat,
human-readable response schema.

Each section (experience, education, etc.) has its own private function
so the logic stays focused and testable.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.models import (
    CertificationItem,
    ContactInfo,
    EducationItem,
    ExperienceItem,
    LanguageItem,
    ProfileResponse,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse a nested dict. Returns default on any missing key."""
    for key in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(key, default)
        if d is default:
            return default
    return d


def _format_date(date_dict: Optional[dict]) -> Optional[str]:
    """
    Convert LinkedIn's date object to an ISO-ish string.

    LinkedIn dates look like: {"year": 2020, "month": 3}
    We produce: "2020-03"  (or "2020" when month is absent)
    """
    if not date_dict or not isinstance(date_dict, dict):
        return None
    year = date_dict.get("year")
    if not year:
        return None
    month = date_dict.get("month")
    return f"{year}-{month:02d}" if month else str(year)


def _extract_image_url(vector_image: Optional[dict]) -> Optional[str]:
    """
    Build an absolute image URL from LinkedIn's VectorImage structure.

    LinkedIn stores images as:
      {
        "rootUrl": "https://media.linkedin.com/dms/image/.../",
        "artifacts": [
          {"width": 100, "height": 100, "fileIdentifyingUrlPathSegment": "..."},
          {"width": 400, "height": 400, "fileIdentifyingUrlPathSegment": "..."},
        ]
      }

    We pick the artifact with the largest area (best quality).
    Final URL = rootUrl + fileIdentifyingUrlPathSegment
    """
    if not vector_image or not isinstance(vector_image, dict):
        return None
    root = vector_image.get("rootUrl", "")
    artifacts = vector_image.get("artifacts", [])
    if not root or not artifacts:
        return None
    # Largest area = best resolution
    best = max(artifacts, key=lambda a: a.get("width", 0) * a.get("height", 0))
    segment = best.get("fileIdentifyingUrlPathSegment", "")
    return (root + segment) if segment else None


# ── Section Parsers ───────────────────────────────────────────────────────────

def _parse_experience(position_view: dict) -> list[ExperienceItem]:
    """
    Parse the positionView section from profileView.

    Each element represents one role. LinkedIn sends:
      - title, companyName, locationName, description
      - timePeriod.startDate / timePeriod.endDate  (absence of endDate = current)
      - company.miniCompany.universalName  (for building the company LinkedIn URL)
    """
    items: list[ExperienceItem] = []
    for elem in position_view.get("elements", []):
        # Company info lives inside a nested miniCompany object
        mini_company = _safe_get(elem, "company", "miniCompany", default={})
        company_name = elem.get("companyName") or mini_company.get("name")
        company_slug = mini_company.get("universalName")
        company_url = (
            f"https://www.linkedin.com/company/{company_slug}"
            if company_slug else None
        )

        # Dates can be under "timePeriod" or "dateRange" depending on API version
        tp = elem.get("timePeriod") or elem.get("dateRange") or {}
        start_raw = tp.get("startDate") or tp.get("start")
        end_raw = tp.get("endDate") or tp.get("end")

        items.append(ExperienceItem(
            title=elem.get("title"),
            company=company_name,
            company_linkedin_url=company_url,
            location=elem.get("locationName"),
            start_date=_format_date(start_raw),
            end_date=_format_date(end_raw),
            is_current=(end_raw is None),   # No end date → currently working there
            description=elem.get("description"),
        ))
    return items


def _parse_education(education_view: dict) -> list[EducationItem]:
    """
    Parse the educationView section from profileView.

    Fields: schoolName, degreeName, fieldOfStudy, timePeriod, description
    """
    items: list[EducationItem] = []
    for elem in education_view.get("elements", []):
        tp = elem.get("timePeriod") or {}
        items.append(EducationItem(
            school=elem.get("schoolName"),
            degree=elem.get("degreeName"),
            field_of_study=elem.get("fieldOfStudy"),
            start_date=_format_date(tp.get("startDate")),
            end_date=_format_date(tp.get("endDate")),
            description=elem.get("description"),
        ))
    return items


def _parse_certifications(cert_view: dict) -> list[CertificationItem]:
    """
    Parse the certificationView section from profileView.

    Fields: name, authority, timePeriod (startDate = issued, endDate = expiry), url
    """
    items: list[CertificationItem] = []
    for elem in cert_view.get("elements", []):
        tp = elem.get("timePeriod") or {}
        items.append(CertificationItem(
            name=elem.get("name"),
            authority=elem.get("authority"),
            issued_date=_format_date(tp.get("startDate")),
            expiry_date=_format_date(tp.get("endDate")),
            credential_url=elem.get("url"),
        ))
    return items


def _parse_languages(lang_view: dict) -> list[LanguageItem]:
    """
    Parse the languageView section from profileView.

    Proficiency values LinkedIn returns:
      NATIVE_OR_BILINGUAL, FULL_PROFESSIONAL, PROFESSIONAL_WORKING,
      LIMITED_WORKING, ELEMENTARY
    """
    return [
        LanguageItem(
            name=elem.get("name"),
            proficiency=elem.get("proficiency"),
        )
        for elem in lang_view.get("elements", [])
    ]


def _parse_skills(skills_data: dict) -> list[str]:
    """
    Parse the skills endpoint response into a plain list of skill names.

    profileView.skillView only returns "featured" skills (up to 3).
    The dedicated skills endpoint returns the full list (up to 100).
    """
    return [
        elem["name"]
        for elem in skills_data.get("elements", [])
        if elem.get("name")
    ]


def _parse_contact_info(contact_data: dict) -> ContactInfo:
    """
    Parse the profileContactInfo endpoint response.

    LinkedIn only exposes contact info the member has made public:
      emailAddress, phoneNumbers[], twitterHandles[], websites[]
    """
    websites = [
        w["url"]
        for w in contact_data.get("websites", [])
        if w.get("url")
    ]
    twitter_handles = [
        t["name"]
        for t in contact_data.get("twitterHandles", [])
        if t.get("name")
    ]
    phone_numbers = [
        p["number"]
        for p in contact_data.get("phoneNumbers", [])
        if p.get("number")
    ]
    return ContactInfo(
        email=contact_data.get("emailAddress"),
        phone=phone_numbers[0] if phone_numbers else None,
        twitter=twitter_handles[0] if twitter_handles else None,
        websites=websites,
    )


# ── Dash Entity Extractor ───────────────────────────────────────────────────

def _extract_from_dash_included(included: list[dict], username: str) -> Optional[ProfileResponse]:
    """
    Parse LinkedIn's modern Dash FullProfileWithEntities response.
    The response places all normalized entities in an 'included' array.
    """
    if not isinstance(included, list) or not included:
        return None

    # Find the primary Profile object
    profile_obj = None
    for item in included:
        t = item.get("$type", "")
        if "identity.profile.Profile" in t or (
            "fsd_profile:" in item.get("entityUrn", "") and "firstName" in item
        ):
            profile_obj = item
            break

    if not profile_obj:
        # Fallback: check any item with firstName
        profile_obj = next((item for item in included if "firstName" in item), {})

    # Name
    first = profile_obj.get("firstName", "")
    last = profile_obj.get("lastName", "")
    name = f"{first} {last}".strip() or None

    # Headline & About
    headline = profile_obj.get("headline")
    about = profile_obj.get("summary")

    # Location
    location = profile_obj.get("locationName")
    if not location and isinstance(profile_obj.get("location"), dict):
        basic = _safe_get(profile_obj, "location", "basicLocation", default={})
        city = basic.get("city")
        country = basic.get("country")
        if city and country:
            location = f"{city}, {country}"
        elif city or country:
            location = city or country

    # Images
    pic_vec = (
        _safe_get(profile_obj, "profilePicture", "displayImageReference", "vectorImage")
        or _safe_get(profile_obj, "picture", "com.linkedin.common.VectorImage")
    )
    bg_vec = (
        _safe_get(profile_obj, "backgroundPicture", "displayImageReference", "vectorImage")
        or _safe_get(profile_obj, "backgroundImage", "com.linkedin.common.VectorImage")
    )
    profile_pic_url = _extract_image_url(pic_vec)
    bg_pic_url = _extract_image_url(bg_vec)

    # Collections from included
    experiences: list[ExperienceItem] = []
    educations: list[EducationItem] = []
    skills: list[str] = []
    certifications: list[CertificationItem] = []
    languages: list[LanguageItem] = []

    for item in included:
        t = item.get("$type", "")

        # Positions / Experience
        if "identity.profile.Position" in t or ("title" in item and "companyName" in item):
            dr = item.get("dateRange") or item.get("timePeriod") or {}
            start_raw = dr.get("start") or dr.get("startDate")
            end_raw = dr.get("end") or dr.get("endDate")
            company_url = None
            company_slug = _safe_get(item, "company", "miniCompany", "universalName")
            if company_slug:
                company_url = f"https://www.linkedin.com/company/{company_slug}"

            experiences.append(
                ExperienceItem(
                    title=item.get("title"),
                    company=item.get("companyName"),
                    company_linkedin_url=company_url,
                    location=item.get("locationName"),
                    start_date=_format_date(start_raw),
                    end_date=_format_date(end_raw),
                    is_current=(end_raw is None),
                    description=item.get("description"),
                )
            )

        # Education
        elif "identity.profile.Education" in t or "schoolName" in item:
            dr = item.get("dateRange") or item.get("timePeriod") or {}
            educations.append(
                EducationItem(
                    school=item.get("schoolName"),
                    degree=item.get("degreeName"),
                    field_of_study=item.get("fieldOfStudy"),
                    start_date=_format_date(dr.get("start") or dr.get("startDate")),
                    end_date=_format_date(dr.get("end") or dr.get("endDate")),
                    description=item.get("description"),
                )
            )

        # Skills
        elif "identity.profile.Skill" in t or ("name" in item and "Skill" in item.get("entityUrn", "")):
            skill_name = item.get("name")
            if skill_name and skill_name not in skills:
                skills.append(skill_name)

        # Certifications
        elif "identity.profile.Certification" in t or ("name" in item and "authority" in item):
            dr = item.get("dateRange") or item.get("timePeriod") or {}
            certifications.append(
                CertificationItem(
                    name=item.get("name"),
                    authority=item.get("authority"),
                    issued_date=_format_date(dr.get("start") or dr.get("startDate")),
                    expiry_date=_format_date(dr.get("end") or dr.get("endDate")),
                    credential_url=item.get("url") or item.get("credentialUrl"),
                )
            )

        # Languages
        elif "identity.profile.Language" in t or ("name" in item and "proficiency" in item):
            languages.append(
                LanguageItem(
                    name=item.get("name"),
                    proficiency=item.get("proficiency"),
                )
            )

    return ProfileResponse(
        username=username,
        name=name,
        headline=headline,
        location=location,
        about=about,
        profile_picture_url=profile_pic_url,
        background_image_url=bg_pic_url,
        connections=None,
        followers=None,
        open_to_work=False,
        experience=experiences,
        education=educations,
        skills=skills,
        certifications=certifications,
        languages=languages,
        contact_info=ContactInfo(),
        scraped_at=datetime.now(timezone.utc),
    )


# ── Main Parser ───────────────────────────────────────────────────────────────

def parse_profile(raw: dict[str, Any], username: str) -> ProfileResponse:
    """
    Entry point. Accepts the dict returned by VoyagerClient.fetch_profile()
    and returns a fully populated ProfileResponse.

    Supports both modern Dash schemas and legacy schemas.
    """
    dash_data = raw.get("dash_profile") or raw.get("profile_view", {})

    # Check if modern Dash format with 'included' array is present
    if isinstance(dash_data, dict) and "included" in dash_data:
        dash_parsed = _extract_from_dash_included(dash_data.get("included", []), username)
        if dash_parsed:
            # Merge supplementary network & contact info if available
            network = raw.get("network_info", {})
            if isinstance(network, dict):
                dash_parsed.connections = network.get("connectionsCount") or dash_parsed.connections
                dash_parsed.followers = (
                    network.get("followersCount")
                    or _safe_get(network, "followingInfo", "followerCount")
                    or dash_parsed.followers
                )

            contact = raw.get("contact_info", {})
            if isinstance(contact, dict) and contact:
                dash_parsed.contact_info = _parse_contact_info(contact)

            supp_skills = _parse_skills(raw.get("skills", {}))
            for sk in supp_skills:
                if sk not in dash_parsed.skills:
                    dash_parsed.skills.append(sk)

            return dash_parsed

    # Fallback to legacy nested format
    pv = raw.get("profile_view", {})
    profile = pv.get("profile", {})
    mini = profile.get("miniProfile", {})

    first = profile.get("firstName") or mini.get("firstName", "")
    last = profile.get("lastName") or mini.get("lastName", "")
    name = f"{first} {last}".strip() or None

    picture_vector = _safe_get(mini, "picture", "com.linkedin.common.VectorImage")
    bg_vector = _safe_get(mini, "backgroundImage", "com.linkedin.common.VectorImage")

    network = raw.get("network_info", {})
    connections = network.get("connectionsCount") if isinstance(network, dict) else None
    followers = (
        (network.get("followersCount") or _safe_get(network, "followingInfo", "followerCount"))
        if isinstance(network, dict)
        else None
    )

    skills_data = raw.get("skills", {})
    if not skills_data.get("elements"):
        skills_data = pv.get("skillView", {})

    return ProfileResponse(
        username=username,
        name=name,
        headline=profile.get("headline") or mini.get("occupation"),
        location=profile.get("locationName"),
        about=profile.get("summary"),
        profile_picture_url=_extract_image_url(picture_vector),
        background_image_url=_extract_image_url(bg_vector),
        connections=connections,
        followers=followers,
        open_to_work=False,
        experience=_parse_experience(pv.get("positionView", {})),
        education=_parse_education(pv.get("educationView", {})),
        skills=_parse_skills(skills_data),
        certifications=_parse_certifications(pv.get("certificationView", {})),
        languages=_parse_languages(pv.get("languageView", {})),
        contact_info=_parse_contact_info(raw.get("contact_info", {})),
        scraped_at=datetime.now(timezone.utc),
    )
