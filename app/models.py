"""
models.py — Pydantic request/response models.

These define the exact JSON shape callers send and receive.
All fields are Optional where LinkedIn may not expose the data.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ── Request ───────────────────────────────────────────────────────────────────

class ProfileRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_linkedin_url(cls, v: str) -> str:
        if "linkedin.com/in/" not in v.lower():
            raise ValueError("URL must be a LinkedIn profile URL (linkedin.com/in/...)")
        return v.strip()


# ── Response sub-models ───────────────────────────────────────────────────────

class ExperienceItem(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None       # "YYYY-MM" or "YYYY"
    end_date: Optional[str] = None         # None means "Present"
    is_current: bool = False
    description: Optional[str] = None


class EducationItem(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class CertificationItem(BaseModel):
    name: Optional[str] = None
    authority: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    credential_url: Optional[str] = None


class LanguageItem(BaseModel):
    name: Optional[str] = None
    proficiency: Optional[str] = None      # e.g. "NATIVE_OR_BILINGUAL", "PROFESSIONAL_WORKING"


class ContactInfo(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    twitter: Optional[str] = None
    websites: list[str] = []


# ── Top-level response ────────────────────────────────────────────────────────

class ProfileResponse(BaseModel):
    username: str
    name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    about: Optional[str] = None
    profile_picture_url: Optional[str] = None
    background_image_url: Optional[str] = None
    connections: Optional[int] = None
    followers: Optional[int] = None
    open_to_work: bool = False
    experience: list[ExperienceItem] = []
    education: list[EducationItem] = []
    skills: list[str] = []
    certifications: list[CertificationItem] = []
    languages: list[LanguageItem] = []
    contact_info: ContactInfo = ContactInfo()
    scraped_at: datetime


# ── Error response ────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
