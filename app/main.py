"""
main.py — FastAPI application entry point.

Creates the app, registers routers, and configures logging.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.profile import router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="LinkedIn Profile API",
    description=(
        "Reverse-engineered LinkedIn Profile API. "
        "Accepts a LinkedIn profile URL and returns structured JSON "
        "with all publicly available profile data.\n\n"
        "**Authentication**: Set `LI_AT` and `JSESSIONID` environment variables "
        "with cookie values from a logged-in LinkedIn browser session."
    ),
    version="1.0.0",
    contact={
        "name": "API Support",
    },
    license_info={
        "name": "MIT",
    },
)

# Allow cross-origin requests (useful for testing from browser / Postman)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "message": "LinkedIn Profile API is running.",
        "docs": "/docs",
        "health": "/health",
        "usage": "POST /api/profile with body: {\"url\": \"https://linkedin.com/in/<username>\"}",
    }
