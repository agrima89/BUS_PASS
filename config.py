"""Application configuration.

All secrets come from environment variables (or a local .env file that is
never committed). Nothing sensitive is hardcoded here.
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    # If SECRET_KEY is missing we generate a throwaway key so development
    # still works; sessions will reset on every restart. Set it in production.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SECRET_KEY_FROM_ENV = bool(os.environ.get("SECRET_KEY"))

    DATABASE = os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "university_pass.db"))
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB cap; the browser shrinks photos before upload anyway

    # Key used to sign offline QR payloads. Falls back to SECRET_KEY.
    QR_SIGNING_KEY = os.environ.get("QR_SIGNING_KEY") or SECRET_KEY
    # Public address encoded in online QR codes, e.g. https://pass.example.edu
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    PASS_PREFIX = os.environ.get("PASS_PREFIX", "DU")
    # "random" -> DU-2026-K7Q2XZ (not guessable)   "sequential" -> DU-2026-00001
    PASS_NUMBER_STYLE = os.environ.get("PASS_NUMBER_STYLE", "random")
    # 0 = leave the "Buggy Pass No." space blank on the card (filled in by hand)
    # Create the pass + unique QR automatically when a complete student record is saved.
    AUTO_ISSUE_PASS = os.environ.get("AUTO_ISSUE_PASS", "1") == "1"
    PRINT_PASS_NUMBER = os.environ.get("PRINT_PASS_NUMBER", "0") == "1"
    # Fields that must be filled before a pass can be issued (comma-separated).
    # Choices: photo, guardian_name, pickup_point, emergency_contact, address, valid_until,
    #          department, year_of_study, blood_group
    REQUIRED_FOR_PASS = tuple(f.strip() for f in os.environ.get(
        "REQUIRED_FOR_PASS", "photo,guardian_name,pickup_point,emergency_contact,address,valid_until"
    ).split(",") if f.strip())

    # Placeholder branding until official assets are supplied.
    UNIVERSITY_NAME = os.environ.get("UNIVERSITY_NAME", "Demo University")
    UNIVERSITY_SHORT = os.environ.get("UNIVERSITY_SHORT", "DU")

    # Single-PC use by the transport office: no login screen. Turn on (1) before the
    # app is reachable from any other computer; serve.py enforces this.
    REQUIRE_LOGIN = os.environ.get("REQUIRE_LOGIN", "0") == "1"

    TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only-key"
    QR_SIGNING_KEY = "test-only-qr-key"
    REQUIRE_LOGIN = True  # existing tests cover the login-protected mode
    # Tests must not depend on the local .env branding.
    PASS_PREFIX = "DU"
    UNIVERSITY_NAME = "Demo University"
    UNIVERSITY_SHORT = "DU"
    PASS_NUMBER_STYLE = "random"
    PRINT_PASS_NUMBER = False
    REQUIRED_FOR_PASS = ()
    AUTO_ISSUE_PASS = False  # older tests issue passes explicitly; auto-issue has its own tests
