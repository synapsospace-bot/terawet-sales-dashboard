import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Lightweight built-in .env parser
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

# LLM Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# ==========================================
# Google Sheet Live Source
# ==========================================
DATA_SOURCE = os.getenv("DATA_SOURCE", "google_sheets").lower()
GOOGLE_SHEET_URL = os.getenv(
    "GOOGLE_SHEET_URL", 
    "https://docs.google.com/spreadsheets/d/1E5w61jpITa3DgnmnhbJBmLhllTVLabUYYZMlke4CljY/edit?usp=sharing"
)
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "")
CSV_FILE_PATH = os.getenv("CSV_FILE_PATH", str(BASE_DIR / "leads_sample.csv"))

# ==========================================
# Email / Gmail Configuration
# ==========================================
EMAIL_USER = os.getenv("EMAIL_USER", "synapso.space@gmail.com")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "")

GMAIL_ENABLED = os.getenv("GMAIL_ENABLED", "false").lower() in ("true", "1", "yes")
GMAIL_CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json"))
GMAIL_TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", str(BASE_DIR / "token.pickle"))

LOCAL_DRAFTS_DIR = os.getenv("LOCAL_DRAFTS_DIR", str(BASE_DIR / "drafts_preview"))

# ==========================================
# Sender & Website Information (from tera-wet.com)
# ==========================================
SENDER_NAME = os.getenv("SENDER_NAME", "Dmytro Bendyk | TERAWET-ORIGINAL")
SENDER_COMPANY = os.getenv("SENDER_COMPANY", "TERAWET-ORIGINAL / ВАНКО 97 ЕООД")
SENDER_PHONE = os.getenv("SENDER_PHONE", "+359 888 516501")
SENDER_WEBSITE = os.getenv("SENDER_WEBSITE", "https://tera-wet.com")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "terawet.original@gmail.com")

KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"
