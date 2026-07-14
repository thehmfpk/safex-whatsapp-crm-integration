"""
config.py
---------
Central configuration for the SafeX Solutions WhatsApp Auto-Reply Bot
- CRM Integration module.

All values are read from environment variables (see .env.example).
Nothing sensitive is hard-coded here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from a .env file if present (local dev / Colab friendly)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Groq (LLM) settings
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# llama-3.1-8b-instant -> fastest, most generous free-tier quota, great for
# quick structured-extraction tasks like this one.
# llama-3.3-70b-versatile -> higher quality, use if you need better accuracy
# and don't mind a lower free daily quota.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# ---------------------------------------------------------------------------
# CRM storage backend
# ---------------------------------------------------------------------------
# "csv"      -> local data/leads.csv  (default, zero setup, works offline)
# "airtable" -> pushes/reads leads from an Airtable base (needs API creds)
CRM_BACKEND = os.getenv("CRM_BACKEND", "csv").lower()

CSV_PATH = BASE_DIR / "data" / "leads.csv"

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Leads")

# ---------------------------------------------------------------------------
# Twilio / WhatsApp Business API settings (sandbox-friendly)
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# Shared secret so /webhook can't be spammed by randoms while demoing publicly
WEBHOOK_VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN", "safex-demo-token")

# ---------------------------------------------------------------------------
# Lead status pipeline (used for tagging + dashboard pipeline view)
# ---------------------------------------------------------------------------
LEAD_STATUSES = ["New", "Contacted", "Qualified", "Converted", "Lost"]

# Flask
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
PORT = int(os.getenv("PORT", "5000"))
DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
