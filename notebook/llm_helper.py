"""
llm_helper.py
-------------
Turns a raw inbound WhatsApp message into structured lead data using
Groq's free, ultra-fast LLM inference API (OpenAI-compatible endpoint).

Get a free key in 60 seconds: https://console.groq.com  (no card needed)
Put it in .env as GROQ_API_KEY=gsk_...

Fallback: if no GROQ_API_KEY is set, a lightweight regex/keyword
extractor is used instead, so the whole pipeline (and the notebook
demo) still runs end-to-end with zero API cost while you're wiring
things up.
"""

from __future__ import annotations

import json
import re
from typing import TypedDict

import config

SYSTEM_PROMPT = """You are a lead-extraction engine for a WhatsApp sales bot.
Given one inbound customer message, extract structured info and reply with
ONLY a raw JSON object (no markdown fences, no commentary) matching exactly:

{
  "name": "<string, empty if unknown>",
  "email": "<string, empty if unknown>",
  "interest": "<short 2-6 word summary of what they want, e.g. 'pricing for CRM plan'>",
  "status": "<one of: New, Contacted, Qualified, Converted, Lost>",
  "sentiment": "<one of: positive, neutral, negative>"
}

Status guide:
- "New": first-time generic inquiry, greeting, or asking what the business offers.
- "Contacted": they replied to a follow-up but haven't shown buying intent yet.
- "Qualified": they're asking about pricing, demos, features, or timelines - clear buying intent.
- "Converted": they explicitly confirm they want to purchase / sign up / proceed.
- "Lost": they say not interested, stop messaging, or explicitly decline.
"""


class LeadExtraction(TypedDict):
    name: str
    email: str
    interest: str
    status: str
    sentiment: str


def _has_any(text: str, keywords: list[str]) -> bool:
    """
    Word/phrase-boundary keyword match - avoids false positives like
    'hi' matching inside 'this', 'which', 'shipping', etc. Multi-word
    phrases (e.g. 'sign up') are matched literally with boundaries on
    each end; single words are matched as whole words only.
    """
    for kw in keywords:
        pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
        if re.search(pattern, text):
            return True
    return False


def _fallback_extract(message: str) -> LeadExtraction:
    """Zero-dependency, zero-cost extractor used when no GROQ_API_KEY is set."""
    text = message.lower()

    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", message)
    email = email_match.group(0) if email_match else ""

    name_match = re.search(r"\b(?:my name is|i am|i'm|this is)\s+([A-Z][a-zA-Z]+)", message, re.I)
    name = name_match.group(1) if name_match else ""

    if _has_any(text, ["not interested", "stop", "unsubscribe", "no thanks", "remove my number"]):
        status, sentiment, interest = "Lost", "negative", "opted out"
    elif _has_any(text, ["buy", "purchase", "sign up", "signup", "proceed", "confirm", "go ahead",
                         "ready to sign", "let's proceed", "book a call", "sounds good"]):
        status, sentiment, interest = "Converted", "positive", "ready to purchase"
    elif _has_any(text, ["price", "pricing", "cost", "demo", "quote", "plan", "feature",
                         "package", "packages", "timeline", "quotation"]):
        status, sentiment, interest = "Qualified", "positive", "pricing / demo inquiry"
    elif _has_any(text, ["hi", "hello", "hey", "salam", "assalam", "info", "information", "tell me about"]):
        status, sentiment, interest = "New", "neutral", "general inquiry"
    else:
        status, sentiment, interest = "Contacted", "neutral", "general follow-up"

    return {
        "name": name,
        "email": email,
        "interest": interest,
        "status": status,
        "sentiment": sentiment,
    }


def extract_lead_info(message: str) -> LeadExtraction:
    """
    Main entry point used by app.py and the notebook. Tries Groq first
    (if configured), falls back to the regex extractor on any error so
    the bot never crashes because the LLM call failed or quota ran out.
    """
    if not config.GROQ_API_KEY:
        return _fallback_extract(message)

    try:
        from groq import Groq

        client = Groq(api_key=config.GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content
        data = json.loads(raw)

        return {
            "name": data.get("name", "") or "",
            "email": data.get("email", "") or "",
            "interest": data.get("interest", "") or "",
            "status": data.get("status") if data.get("status") in config.LEAD_STATUSES else "New",
            "sentiment": data.get("sentiment", "neutral"),
        }
    except Exception as exc:  # noqa: BLE001 - we want any failure to fall back, not crash the bot
        print(f"[llm_helper] Groq call failed, using fallback extractor: {exc}")
        return _fallback_extract(message)


def generate_auto_reply(message: str, extraction: LeadExtraction) -> str:
    """
    Small bonus: generates the WhatsApp bot's auto-reply text so this
    module can slot in next to Group 53's 'message-parsing' /
    'auto-reply' modules without duplicating their work - this function
    is optional and only used by the standalone demo route/notebook.
    """
    templates = {
        "New": "Thanks for reaching out to SafeX Solutions! 👋 Could you tell us a bit more about what you're looking for so we can help?",
        "Contacted": "Thanks for the update! One of our team members will follow up with you shortly.",
        "Qualified": "Great, we'd love to walk you through pricing and a quick demo. What's the best time to call you?",
        "Converted": "Awesome, welcome aboard! 🎉 Our onboarding team will reach out within 24 hours to get you set up.",
        "Lost": "No worries at all, thanks for letting us know. Feel free to reach back out anytime!",
    }
    return templates.get(extraction["status"], templates["New"])
