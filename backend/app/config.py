"""App settings, read from backend/.env (see .env.example)."""
import json
import secrets
import shutil
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BASE_DIR / "data"
KB_DIR = BASE_DIR / "knowledge_base"
STORAGE_DIR = BASE_DIR / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
KEYS_FILE = STORAGE_DIR / "keys.json"

STORAGE_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(STORAGE_DIR / 'healthcare.db').as_posix()}"
    secret_key: str = ""
    fernet_key: str = ""
    token_minutes: int = 60

    # auto = Gemini if its key is set, else Groq, else offline rules
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_fallback_models: str = "gemini-3-flash-preview,gemini-3.5-flash-lite"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout: int = 60

    tesseract_cmd: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    price_cache_hours: int = 24
    live_prices: bool = True


def _load_or_create_keys() -> dict:
    """Signing + encryption keys are generated once and kept in storage/keys.json."""
    if KEYS_FILE.exists():
        return json.loads(KEYS_FILE.read_text())
    keys = {"secret_key": secrets.token_urlsafe(48), "fernet_key": Fernet.generate_key().decode()}
    KEYS_FILE.write_text(json.dumps(keys))
    return keys


def _find_tesseract() -> str:
    found = shutil.which("tesseract")
    if found:
        return found
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if Path(p).exists():
            return p
    return ""


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.secret_key or not s.fernet_key:
        keys = _load_or_create_keys()
        s.secret_key = s.secret_key or keys["secret_key"]
        s.fernet_key = s.fernet_key or keys["fernet_key"]
    if not s.tesseract_cmd:
        s.tesseract_cmd = _find_tesseract()
    return s
