import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    UPLOAD_FOLDER = str(BASE_DIR / "app" / "uploads")
    OUTPUT_FOLDER = str(BASE_DIR / "app" / "outputs")
    AUDIT_LOG_FOLDER = str(BASE_DIR / "app" / "logs" / "oe_test")
    SETTINGS_FILE = str(BASE_DIR / "app" / "data" / "settings.json")
    # If set, the admin screen requires this password (HTTP basic auth); otherwise it is localhost-only.
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB total upload cap

    UNIFIED_API_ENV = os.getenv("UNIFIED_API_ENV", "staging")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
