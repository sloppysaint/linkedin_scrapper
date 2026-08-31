# LinkedIn Profile API

A hosted REST API that accepts a LinkedIn profile URL and returns structured JSON with all publicly available profile data — built by **reverse engineering LinkedIn's internal Voyager API**.

## Live Demo

```
POST https://<your-render-url>.onrender.com/api/profile
```
Interactive docs: `https://<your-render-url>.onrender.com/docs`

---

## Approach: Dual-Engine Architecture

LinkedIn does not offer a public API for profile data. To provide a resilient, 100% hosted solution, this API implements a **Smart Dual-Engine Architecture**:

```
Client sends Profile URL
         │
         ▼
┌────────────────────────────────────────────────────────┐
│ Engine 1: Public Guest Engine (Zero-Auth, Zero-Cookie)│
│  • Pure HTTP GET to linkedin.com/in/<username>         │
│  • Extracts embedded JSON-LD (schema.org/Person)       │
│  • Extracts OpenGraph metadata & public DOM cards      │
│  • Never expires, 0 credentials, zero maintenance      │
└────────────────────────────────────────────────────────┘
         │
         ▼ (Optional Voyager Enrichment)
┌────────────────────────────────────────────────────────┐
│ Engine 2: Voyager Internal REST Client                 │
│  • Queries LinkedIn's internal Dash API                │
│  • Enriches skills and network metrics                 │
│  • Auto-falls back to Engine 1 if cookies are expired  │
└────────────────────────────────────────────────────────┘
         │
         ▼
  Structured JSON Response
```

### Key Advantages
* **Zero Maintenance**: You don't even need to configure cookies for the API to work immediately.
* **Never Breaks on Log Out**: If an authenticated session is revoked or logs out, the engine automatically falls back to the Public Guest scraper without returning errors to the caller.
* **Pure HTTP**: Zero browser automation (no Selenium, no Playwright, no Chromium). Fast and lightweight.

### Authentication — Option B (Cookie Injection)

Rather than storing a password, we use **manual cookie injection**:

1. You log into LinkedIn once in your browser
2. Copy two cookie values (`li_at` and `JSESSIONID`) from DevTools
3. Store them as environment variables on Render

These cookies are valid for ~1 year. When they expire, repeat steps 1–3.

### How the CSRF Token Works

LinkedIn's Voyager API requires a `csrf-token` header on every request. The value is derived from the `JSESSIONID` cookie by stripping surrounding double-quotes:

```
JSESSIONID cookie:  "ajax:7482910234"
csrf-token header:   ajax:7482910234
```

This is LinkedIn's CSRF protection — they compare the header against the cookie server-side.

### Concurrent Fetching

For each profile, we make **4 API calls concurrently** using `asyncio.gather()`:

| Endpoint | Returns |
|---|---|
| `/voyager/api/identity/profiles/{id}/profileView` | Name, headline, location, about, photo, experience, education, certifications, languages |
| `/voyager/api/identity/profiles/{id}/networkInfo` | Followers & connections count |
| `/voyager/api/identity/profiles/{id}/profileContactInfo` | Email, phone, Twitter, websites (if public) |
| `/voyager/api/identity/profiles/{id}/skills?count=100` | Full skills list |

Concurrent calls reduce total latency to ~the slowest single call (~1–2 s) instead of summing all four.

---

## Setup

### Prerequisites

- Python 3.11+
- Docker (optional, for containerised local run)

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/<you>/linkedin-profile-api
cd linkedin-profile-api

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials (see "Getting Your LinkedIn Cookies" below)
cp .env.example .env
# Edit .env and fill in LI_AT and JSESSIONID

# 5. Run the server
uvicorn app.main:app --reload

# API is now live at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### Docker

```bash
cp .env.example .env   # Fill in your cookie values
docker-compose up --build
```

### Getting Your LinkedIn Cookies

1. Log into **LinkedIn** in your browser (use a secondary account if possible)
2. Open **DevTools** → Application tab → Cookies → `https://www.linkedin.com`
3. Find and copy the values for:
   - `li_at` — a long alphanumeric token
   - `JSESSIONID` — looks like `"ajax:1234567890123456789"` (include the quotes)
4. Add them to your `.env` file:
   ```
   LI_AT=AQEDATr...
   JSESSIONID="ajax:7482910234..."
   ```

> **Security**: These values never leave your environment. They are not committed to the repository (`.env` is in `.gitignore`).

---

## Deployment on Render.com

1. Push the repository to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repository
4. Set the following in **Environment** → **Secret Files / Env Vars**:

   | Key | Value |
   |---|---|
   | `LI_AT` | Your `li_at` cookie value |
   | `JSESSIONID` | Your `JSESSIONID` cookie value (with quotes) |
   | `API_KEY` | *(optional)* A bearer token to protect your API |

5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
7. Render will provide a public HTTPS URL automatically.

---

## API Documentation

### `POST /api/profile`

Scrape a LinkedIn profile and return structured JSON.

**Request:**
```http
POST /api/profile
Content-Type: application/json

{
  "url": "https://www.linkedin.com/in/satyanadella/"
}
```

**Success Response (200):**
```json
{
  "username": "satyanadella",
  "name": "Satya Nadella",
  "headline": "Chairman and CEO at Microsoft",
  "location": "Redmond, Washington, United States",
  "about": "...",
  "profile_picture_url": "https://media.linkedin.com/dms/image/...",
  "background_image_url": "https://media.linkedin.com/dms/image/...",
  "connections": 500,
  "followers": 14000000,
  "open_to_work": false,
  "experience": [
    {
      "title": "Chairman and CEO",
      "company": "Microsoft",
      "company_linkedin_url": "https://www.linkedin.com/company/microsoft",
      "location": "Redmond, WA",
      "start_date": "2014-02",
      "end_date": null,
      "is_current": true,
      "description": "..."
    }
  ],
  "education": [
    {
      "school": "University of Wisconsin-Milwaukee",
      "degree": "MS",
      "field_of_study": "Computer Science",
      "start_date": "1988",
      "end_date": "1990",
      "description": null
    }
  ],
  "skills": ["Cloud Computing", "Artificial Intelligence", "Strategy"],
  "certifications": [],
  "languages": [
    {"name": "English", "proficiency": "NATIVE_OR_BILINGUAL"}
  ],
  "contact_info": {
    "email": null,
    "phone": null,
    "twitter": null,
    "websites": []
  },
  "scraped_at": "2026-08-30T08:07:00Z"
}
```

**Error Responses:**

| Code | Meaning |
|---|---|
| `400` | Invalid or non-LinkedIn URL |
| `401` | Missing API key (if `API_KEY` is configured) |
| `403` | Invalid API key |
| `404` | Profile not found or private |
| `429` | LinkedIn is rate-limiting requests |
| `503` | LinkedIn session expired — refresh cookies |

### `GET /health`

```json
{
  "status": "ok",
  "session_configured": true,
  "api_key_required": false
}
```

### Optional: API Key Protection

If you set the `API_KEY` environment variable, all `/api/profile` requests must include:

```http
Authorization: Bearer <your_api_key>
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

Tests run fully offline — no LinkedIn credentials required.

---

## Project Structure

```
linkedin_scrapper/
├── app/
│   ├── main.py                   # FastAPI app entry point
│   ├── config.py                 # Environment variable loading
│   ├── models.py                 # Pydantic request/response models
│   ├── linkedin/
│   │   ├── session_manager.py    # Reads cookies from env vars, builds auth headers
│   │   ├── voyager_client.py     # Makes concurrent HTTP calls to Voyager API
│   │   └── profile_parser.py     # Maps raw LinkedIn JSON → clean Pydantic models
│   ├── routers/
│   │   └── profile.py            # POST /api/profile, GET /health
│   └── utils/
│       ├── url_parser.py         # Extracts username from LinkedIn URL
│       └── rate_limiter.py       # Async rate limiter
├── tests/
│   ├── test_url_parser.py
│   ├── test_profile_parser.py
│   └── test_api.py
├── .env.example                  # Credential template (no values)
├── .gitignore                    # Excludes .env, cookies, __pycache__
├── Dockerfile
├── docker-compose.yml
├── render.yaml                   # Render.com deployment config
└── requirements.txt
```

---

## Known Limitations

| Limitation | Reason |
|---|---|
| **Public profiles only** | LinkedIn only returns full data for profiles visible to your account. Private profiles return a 404. |
| **Experience may be truncated** | `profileView` returns up to ~10 positions. Profiles with many roles may be incomplete without pagination. |
| **Contact info rarely available** | LinkedIn only exposes email/phone if the member has explicitly made it public. |
| **Open to Work status** | Requires a separate endpoint not included in this version. |
| **Session expiry** | `li_at` and `JSESSIONID` expire after ~1 year. You must refresh them manually. |
| **Rate limiting** | LinkedIn may throttle or block requests from accounts making too many automated calls. Use a secondary account. |
| **ToS notice** | LinkedIn's Terms of Service prohibit scraping. This project is intended for educational / assessment purposes. |

---

## Security Notes

- Credentials are stored **only** in environment variables — never in code or the repository
- `.env` is listed in `.gitignore` and will never be committed
- Render stores secrets encrypted and injects them at runtime
- The `API_KEY` option lets you restrict access to the hosted endpoint
