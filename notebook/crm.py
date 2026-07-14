"""
crm.py
------
The "CRM Integration" module for Group 53's WhatsApp Auto-Reply Bot.

Responsibilities (per the assignment scope):
    1. Take a captured lead (from the message-parsing / bot module).
    2. De-duplicate against existing records (matched on phone number,
       the one field guaranteed to be present and stable per WhatsApp
       contact).
    3. Tag / update the lead's pipeline status.
    4. Persist to a "simple CRM sheet" (CSV by default) or an Airtable
       base if configured.

This module is intentionally storage-agnostic: `CRMClient` exposes the
same public API (`add_or_update_lead`, `get_all_leads`, `get_lead`,
`update_status`) no matter which backend is active, so the Flask app
(app.py) and the other group members' modules don't need to know or
care which storage is behind it.
"""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

CSV_FIELDS = [
    "lead_id",
    "name",
    "phone",
    "email",
    "interest",
    "last_message",
    "status",
    "source",
    "first_contact",
    "last_contact",
    "message_count",
    "notes",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def normalize_phone(phone: str) -> str:
    """
    Normalize WhatsApp / Twilio phone strings so the same human always
    de-duplicates to the same key, e.g.:
        'whatsapp:+92 300 1234567' -> '+923001234567'
        '0300-1234567'             -> '+923001234567' (assumes PK default)
    """
    if not phone:
        return ""
    phone = phone.replace("whatsapp:", "").strip()
    digits = re.sub(r"[^\d+]", "", phone)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        # Best-effort default country code (Pakistan) for local-format
        # numbers like 03xx-xxxxxxx. Adjust DEFAULT_COUNTRY_CODE as needed.
        if digits.startswith("0"):
            digits = "+92" + digits[1:]
        else:
            digits = "+" + digits
    return digits


@dataclass
class Lead:
    lead_id: str
    name: str
    phone: str
    email: str
    interest: str
    last_message: str
    status: str
    source: str
    first_contact: str
    last_contact: str
    message_count: int
    notes: str = ""

    def to_row(self) -> dict:
        return asdict(self)


class CRMClient:
    """Storage-agnostic CRM client. Backend chosen via config.CRM_BACKEND."""

    def __init__(self, backend: Optional[str] = None):
        self.backend = (backend or config.CRM_BACKEND).lower()
        if self.backend == "airtable":
            from airtable_backend import AirtableStore  # local import: optional dep
            self._store = AirtableStore()
        else:
            self._store = CSVStore(config.CSV_PATH)

    # ------------------------------------------------------------------
    # Public API used by app.py / the LLM helper / the notebook demo
    # ------------------------------------------------------------------
    def add_or_update_lead(
        self,
        phone: str,
        message_text: str,
        name: str = "",
        email: str = "",
        interest: str = "",
        status: Optional[str] = None,
        source: str = "whatsapp",
    ) -> tuple[Lead, bool]:
        """
        Core de-duplication + tagging logic.

        Returns (lead, is_new_lead).
        De-dup key = normalized phone number. If a lead with that phone
        already exists we UPDATE it in place (bump message_count, refresh
        last_contact/last_message, fill in any newly-known fields, and
        only escalate status forward through the pipeline, never
        downgrade a Converted lead back to New on a follow-up message).
        """
        phone_key = normalize_phone(phone)
        existing = self._store.find_by_phone(phone_key)

        if existing:
            existing.name = name or existing.name
            existing.email = email or existing.email
            existing.interest = interest or existing.interest
            existing.last_message = message_text
            existing.last_contact = _now()
            existing.message_count = int(existing.message_count) + 1
            if status:
                existing.status = self._resolve_status_transition(existing.status, status)
            self._store.upsert(existing)
            return existing, False

        new_lead = Lead(
            lead_id=str(uuid.uuid4())[:8],
            name=name or "Unknown",
            phone=phone_key,
            email=email,
            interest=interest,
            last_message=message_text,
            status=status or "New",
            source=source,
            first_contact=_now(),
            last_contact=_now(),
            message_count=1,
        )
        self._store.upsert(new_lead)
        return new_lead, True

    def update_status(self, lead_id: str, new_status: str) -> Optional[Lead]:
        if new_status not in config.LEAD_STATUSES:
            raise ValueError(f"Unknown status '{new_status}'. Must be one of {config.LEAD_STATUSES}")
        lead = self._store.find_by_id(lead_id)
        if not lead:
            return None
        lead.status = new_status
        lead.last_contact = _now()
        self._store.upsert(lead)
        return lead

    def get_all_leads(self) -> list[Lead]:
        return self._store.all()

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        return self._store.find_by_id(lead_id)

    def stats(self) -> dict:
        leads = self.get_all_leads()
        out = {"total": len(leads)}
        for s in config.LEAD_STATUSES:
            out[s.lower()] = sum(1 for l in leads if l.status == s)
        return out

    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_status_transition(current: str, proposed: str) -> str:
        """Never silently downgrade Converted/Lost leads from a stray inbound message."""
        order = config.LEAD_STATUSES
        if current in ("Converted", "Lost"):
            return current
        try:
            if order.index(proposed) < order.index(current):
                return current
        except ValueError:
            return current
        return proposed


# ==========================================================================
# CSV backend  ("simple CRM sheet")
# ==========================================================================
class CSVStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()

    def _read_all(self) -> list[dict]:
        with open(self.path, "r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _write_all(self, rows: list[dict]):
        with open(self.path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def all(self) -> list[Lead]:
        return [Lead(**row) for row in self._read_all()]

    def find_by_phone(self, phone_key: str) -> Optional[Lead]:
        for row in self._read_all():
            if row["phone"] == phone_key:
                return Lead(**row)
        return None

    def find_by_id(self, lead_id: str) -> Optional[Lead]:
        for row in self._read_all():
            if row["lead_id"] == lead_id:
                return Lead(**row)
        return None

    def upsert(self, lead: Lead):
        rows = self._read_all()
        for i, row in enumerate(rows):
            if row["lead_id"] == lead.lead_id:
                rows[i] = lead.to_row()
                self._write_all(rows)
                return
        rows.append(lead.to_row())
        self._write_all(rows)
