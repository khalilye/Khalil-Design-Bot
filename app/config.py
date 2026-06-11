# app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()

# لSupabase استخدم connection string بصيغة asyncpg:
# مثال:
# postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
DATABASE_URL = (os.getenv("DATABASE_URL") or "sqlite+aiosqlite:///./bot.db").strip()

OWNER_TELEGRAM_ID = int((os.getenv("OWNER_TELEGRAM_ID") or "0").strip())
STORAGE_DIR = (os.getenv("STORAGE_DIR") or "./data").strip()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# موديلات افتراضية عامة (يمكن تغييرها مستقبلاً)
DEFAULT_TEXT_MODEL = os.getenv("DEFAULT_TEXT_MODEL", "google/gemini-3-flash-preview")
DEFAULT_IMAGE_MODEL = os.getenv("DEFAULT_IMAGE_MODEL", "black-forest-labs/flux-1-dev")