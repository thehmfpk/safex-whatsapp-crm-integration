"""
airtable_backend.py
--------------------
Optional Airtable-backed storage for CRMClient. Only imported when
CRM_BACKEND=airtable in your .env — the rest of the app works fine
without the `pyairtable` package installed at all.

Set up:
    pip install pyairtable
    Create an Airtable base with a "Leads" table containing columns:
    lead_id, name, phone, email, interest, last_message, status,
    source, first_contact, last_contact, message_count, notes
    (all "Single line text" except message_count = Number)

    In .env:
        CRM_BACKEND=airtable
        AIRTABLE_API_KEY=pat_xxx...
        AIRTABLE_BASE_ID=app_xxx...
        AIRTABLE_TABLE_NAME=Leads
"""

from __future__ import annotations
from typing import Optional

import config
from crm import Lead, CSV_FIELDS


class AirtableStore:
    def __init__(self):
        try:
            from pyairtable import Api
        except ImportError as e:
            raise ImportError(
                "pyairtable is required for CRM_BACKEND=airtable. "
                "Install with: pip install pyairtable"
            ) from e

        if not (config.AIRTABLE_API_KEY and config.AIRTABLE_BASE_ID):
            raise RuntimeError(
                "AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set in .env "
                "to use the Airtable backend."
            )

        api = Api(config.AIRTABLE_API_KEY)
        self.table = api.table(config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)

    def _record_to_lead(self, record: dict) -> Lead:
        fields = record["fields"]
        data = {k: fields.get(k, "" if k != "message_count" else 0) for k in CSV_FIELDS}
        data["message_count"] = int(data["message_count"] or 0)
        lead = Lead(**data)
        lead._airtable_record_id = record["id"]  # stash for updates
        return lead

    def all(self) -> list[Lead]:
        return [self._record_to_lead(r) for r in self.table.all()]

    def find_by_phone(self, phone_key: str) -> Optional[Lead]:
        records = self.table.all(formula=f"{{phone}} = '{phone_key}'")
        return self._record_to_lead(records[0]) if records else None

    def find_by_id(self, lead_id: str) -> Optional[Lead]:
        records = self.table.all(formula=f"{{lead_id}} = '{lead_id}'")
        return self._record_to_lead(records[0]) if records else None

    def upsert(self, lead: Lead):
        fields = lead.to_row()
        record_id = getattr(lead, "_airtable_record_id", None)
        if not record_id:
            existing_records = self.table.all(formula=f"{{lead_id}} = '{lead.lead_id}'")
            record_id = existing_records[0]["id"] if existing_records else None

        if record_id:
            self.table.update(record_id, fields)
        else:
            self.table.create(fields)
