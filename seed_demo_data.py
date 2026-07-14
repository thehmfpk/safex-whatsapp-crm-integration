"""
seed_demo_data.py
------------------
Feeds tests/sample_messages.json through the real pipeline
(llm_helper -> crm) so the dashboard has realistic-looking leads for
screenshots / the demo video. Safe to re-run - it de-duplicates just
like the live webhook would.

Run:
    python seed_demo_data.py
"""
import json
from pathlib import Path

from crm import CRMClient
from llm_helper import extract_lead_info

SAMPLE_FILE = Path(__file__).parent / "tests" / "sample_messages.json"


def main():
    crm = CRMClient()
    samples = json.loads(SAMPLE_FILE.read_text())

    for s in samples:
        extraction = extract_lead_info(s["message"])
        lead, is_new = crm.add_or_update_lead(
            phone=s["phone"],
            message_text=s["message"],
            name=s.get("name", ""),
            email=extraction.get("email", ""),
            interest=extraction.get("interest", ""),
            status=extraction.get("status"),
            source="whatsapp",
        )
        action = "CREATED" if is_new else "UPDATED (de-duplicated)"
        print(f"[{action}] {lead.name:15s} | {lead.phone:16s} | status={lead.status:10s} | {s['message'][:50]}")

    print("\nDone. Start the dashboard with: python app.py")


if __name__ == "__main__":
    main()
