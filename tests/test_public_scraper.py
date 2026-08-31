"""
test_public_scraper.py — Unit tests for the Public Guest Scraper engine.
"""

from app.linkedin.public_scraper import public_scraper


MOCK_PUBLIC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Satya Nadella - Microsoft | LinkedIn">
    <meta property="profile:first_name" content="Satya">
    <meta property="profile:last_name" content="Nadella">
    <meta property="og:description" content="As chairman and CEO of Microsoft... · Experience: Microsoft · Location: Redmond · 500+ connections on LinkedIn.">
    <meta property="og:image" content="https://media.licdn.com/dms/image/satya.jpg">
    <script type="application/ld+json">
    {
        "@type": "Person",
        "name": "Satya Nadella",
        "jobTitle": "Chairman and CEO",
        "address": {
            "addressLocality": "Redmond",
            "addressRegion": "Washington",
            "addressCountry": "US"
        },
        "description": "About Satya Nadella.",
        "image": "https://media.licdn.com/dms/image/satya.jpg",
        "worksFor": [
            {"@type": "Organization", "name": "Microsoft"}
        ],
        "alumniOf": [
            {"@type": "EducationalOrganization", "name": "The University of Chicago"}
        ]
    }
    </script>
</head>
<body>
</body>
</html>
"""


def test_public_scraper_parsing():
    profile = public_scraper.parse_profile(MOCK_PUBLIC_HTML, "satyanadella")
    assert profile.username == "satyanadella"
    assert profile.name == "Satya Nadella"
    assert profile.headline == "Microsoft" or profile.headline == "Chairman and CEO"
    assert "Redmond" in (profile.location or "")
    assert profile.profile_picture_url == "https://media.licdn.com/dms/image/satya.jpg"
    assert profile.connections == 500
    assert len(profile.experience) >= 1
    assert profile.experience[0].company == "Microsoft"
    assert len(profile.education) >= 1
    assert "Chicago" in (profile.education[0].school or "")
