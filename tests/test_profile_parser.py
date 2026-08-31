"""
test_profile_parser.py — Unit tests for the profile parser.

We build mock LinkedIn API responses and verify the parser maps them correctly.
No real LinkedIn calls are made — all data is synthetic.
"""

import pytest
from datetime import datetime, timezone

from app.linkedin.profile_parser import (
    _format_date,
    _extract_image_url,
    _parse_experience,
    _parse_education,
    _parse_certifications,
    _parse_languages,
    _parse_skills,
    _parse_contact_info,
    parse_profile,
)


class TestFormatDate:
    def test_year_and_month(self):
        assert _format_date({"year": 2020, "month": 3}) == "2020-03"

    def test_year_only(self):
        assert _format_date({"year": 2015}) == "2015"

    def test_month_padding(self):
        assert _format_date({"year": 2022, "month": 1}) == "2022-01"

    def test_none_returns_none(self):
        assert _format_date(None) is None

    def test_empty_dict_returns_none(self):
        assert _format_date({}) is None


class TestExtractImageUrl:
    def test_picks_largest_artifact(self):
        vector = {
            "rootUrl": "https://media.linkedin.com/dms/image/",
            "artifacts": [
                {"width": 100, "height": 100, "fileIdentifyingUrlPathSegment": "small.jpg"},
                {"width": 400, "height": 400, "fileIdentifyingUrlPathSegment": "large.jpg"},
                {"width": 200, "height": 200, "fileIdentifyingUrlPathSegment": "medium.jpg"},
            ],
        }
        result = _extract_image_url(vector)
        assert result == "https://media.linkedin.com/dms/image/large.jpg"

    def test_none_returns_none(self):
        assert _extract_image_url(None) is None

    def test_missing_artifacts_returns_none(self):
        assert _extract_image_url({"rootUrl": "https://example.com/", "artifacts": []}) is None


class TestParseExperience:
    def test_basic_experience(self):
        position_view = {
            "elements": [{
                "title": "Software Engineer",
                "companyName": "Google",
                "locationName": "Mountain View, CA",
                "description": "Built things.",
                "timePeriod": {
                    "startDate": {"year": 2020, "month": 3},
                    "endDate": None,
                },
                "company": {
                    "miniCompany": {"universalName": "google", "name": "Google"}
                },
            }]
        }
        result = _parse_experience(position_view)
        assert len(result) == 1
        exp = result[0]
        assert exp.title == "Software Engineer"
        assert exp.company == "Google"
        assert exp.start_date == "2020-03"
        assert exp.end_date is None
        assert exp.is_current is True
        assert exp.company_linkedin_url == "https://www.linkedin.com/company/google"

    def test_past_experience(self):
        position_view = {
            "elements": [{
                "title": "Intern",
                "companyName": "Startup",
                "timePeriod": {
                    "startDate": {"year": 2018, "month": 6},
                    "endDate": {"year": 2018, "month": 9},
                },
                "company": {"miniCompany": {}},
            }]
        }
        result = _parse_experience(position_view)
        assert result[0].is_current is False
        assert result[0].end_date == "2018-09"

    def test_empty_returns_empty_list(self):
        assert _parse_experience({}) == []


class TestParseEducation:
    def test_basic_education(self):
        edu_view = {
            "elements": [{
                "schoolName": "MIT",
                "degreeName": "Bachelor of Science",
                "fieldOfStudy": "Computer Science",
                "timePeriod": {
                    "startDate": {"year": 2014},
                    "endDate": {"year": 2018},
                },
            }]
        }
        result = _parse_education(edu_view)
        assert len(result) == 1
        edu = result[0]
        assert edu.school == "MIT"
        assert edu.degree == "Bachelor of Science"
        assert edu.start_date == "2014"
        assert edu.end_date == "2018"


class TestParseSkills:
    def test_extracts_skill_names(self):
        skills = {
            "elements": [
                {"name": "Python"},
                {"name": "Machine Learning"},
                {"name": ""},        # empty name should be excluded
                {"endorsementCount": 5},  # no name key
            ]
        }
        result = _parse_skills(skills)
        assert result == ["Python", "Machine Learning"]

    def test_empty_returns_empty_list(self):
        assert _parse_skills({}) == []


class TestParseContactInfo:
    def test_full_contact(self):
        contact = {
            "emailAddress": "john@example.com",
            "phoneNumbers": [{"number": "+1-555-0100"}],
            "twitterHandles": [{"name": "johnhandle"}],
            "websites": [{"url": "https://johndoe.com"}, {"url": "https://blog.johndoe.com"}],
        }
        result = _parse_contact_info(contact)
        assert result.email == "john@example.com"
        assert result.phone == "+1-555-0100"
        assert result.twitter == "johnhandle"
        assert result.websites == ["https://johndoe.com", "https://blog.johndoe.com"]

    def test_empty_contact(self):
        result = _parse_contact_info({})
        assert result.email is None
        assert result.phone is None
        assert result.websites == []


class TestParseProfile:
    def _make_raw(self) -> dict:
        return {
            "profile_view": {
                "profile": {
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "headline": "Senior Engineer at ACME",
                    "locationName": "London, United Kingdom",
                    "summary": "About Jane.",
                    "miniProfile": {
                        "publicIdentifier": "janedoe",
                        "picture": {
                            "com.linkedin.common.VectorImage": {
                                "rootUrl": "https://media.linkedin.com/",
                                "artifacts": [
                                    {"width": 200, "height": 200, "fileIdentifyingUrlPathSegment": "pic.jpg"}
                                ],
                            }
                        },
                    },
                },
                "positionView": {"elements": []},
                "educationView": {"elements": []},
                "certificationView": {"elements": []},
                "languageView": {"elements": []},
                "skillView": {"elements": []},
            },
            "network_info": {"connectionsCount": 450, "followersCount": 1200},
            "contact_info": {},
            "skills": {"elements": [{"name": "Go"}, {"name": "Kubernetes"}]},
        }

    def test_basic_parse(self):
        raw = self._make_raw()
        result = parse_profile(raw, "janedoe")
        assert result.username == "janedoe"
        assert result.name == "Jane Doe"
        assert result.headline == "Senior Engineer at ACME"
        assert result.location == "London, United Kingdom"
        assert result.about == "About Jane."
        assert result.connections == 450
        assert result.followers == 1200
        assert result.skills == ["Go", "Kubernetes"]
        assert isinstance(result.scraped_at, datetime)

    def test_profile_picture_url(self):
        raw = self._make_raw()
        result = parse_profile(raw, "janedoe")
        assert result.profile_picture_url == "https://media.linkedin.com/pic.jpg"


class TestParseDashProfile:
    def _make_dash_raw(self) -> dict:
        return {
            "dash_profile": {
                "included": [
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
                        "entityUrn": "urn:li:fsd_profile:ACoAAAB_XYZ",
                        "firstName": "Satya",
                        "lastName": "Nadella",
                        "headline": "Chairman and CEO at Microsoft",
                        "summary": "About Satya.",
                        "locationName": "Redmond, Washington, United States",
                    },
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Position",
                        "title": "Chairman and CEO",
                        "companyName": "Microsoft",
                        "locationName": "Redmond, WA",
                        "dateRange": {
                            "start": {"year": 2014, "month": 2},
                            "end": None,
                        },
                        "company": {
                            "miniCompany": {"universalName": "microsoft", "name": "Microsoft"}
                        },
                    },
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Education",
                        "schoolName": "University of Chicago",
                        "degreeName": "MBA",
                        "dateRange": {"start": {"year": 1997}},
                    },
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Skill",
                        "name": "Cloud Computing",
                    },
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Skill",
                        "name": "Strategy",
                    },
                    {
                        "$type": "com.linkedin.voyager.dash.identity.profile.Language",
                        "name": "English",
                        "proficiency": "NATIVE_OR_BILINGUAL",
                    },
                ]
            },
            "network_info": {"connectionsCount": 500, "followersCount": 14000000},
            "contact_info": {"emailAddress": None, "websites": []},
            "skills": {},
        }

    def test_dash_profile_extraction(self):
        raw = self._make_dash_raw()
        result = parse_profile(raw, "satyanadella")
        assert result.username == "satyanadella"
        assert result.name == "Satya Nadella"
        assert result.headline == "Chairman and CEO at Microsoft"
        assert result.location == "Redmond, Washington, United States"
        assert result.about == "About Satya."
        assert len(result.experience) == 1
        assert result.experience[0].title == "Chairman and CEO"
        assert result.experience[0].company == "Microsoft"
        assert result.experience[0].is_current is True
        assert len(result.education) == 1
        assert result.education[0].school == "University of Chicago"
        assert "Cloud Computing" in result.skills
        assert "Strategy" in result.skills
        assert len(result.languages) == 1
        assert result.connections == 500
        assert result.followers == 14000000

