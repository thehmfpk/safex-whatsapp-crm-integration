"""
app.py
------
Flask server for SafeX Solutions' WhatsApp Auto-Reply Bot - CRM
Integration module (Group 53, Week 2).

Routes
------
POST /webhook          Twilio WhatsApp webhook. Receives the inbound
                       message, runs it through llm_helper.extract_lead_info,
                       saves/updates it in the CRM via crm.CRMClient, and
                       replies with an auto-generated message (TwiML).

GET  /                 CRM dashboard (blue/black/white themed UI).
GET  /api/leads        JSON list of all leads (used by the dashboard JS).
GET  /api/stats        JSON pipeline counts (used by the dashboard cards).
POST /api/leads/<id>/status   Manually change a lead's status.
GET  /api/leads/export        Download leads.csv.
POST /api/demo/simulate       Feed a sample message through the pipeline
                               without needing Twilio - used for the demo
                               video / screenshots.

Run:
    pip install -r requirements.txt
    cp .env.example .env      # then fill in GROQ_API_KEY at minimum
    python app.py
    -> open http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import csv as csv_module

from flask import Flask, jsonify, render_template, request, send_file, abort

import config
from crm import CRMClient
from llm_helper import extract_lead_info, generate_auto_reply

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY

crm = CRMClient()

# Try to import Twilio's TwiML helper; the app should still run for the
# dashboard-only demo even if the twilio package isn't installed yet.
try:
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print(
        "[app] WARNING: the 'twilio' package is not installed. The /webhook route "
        "will reply with JSON instead of TwiML, which Twilio cannot parse - install "
        "it with: pip install twilio"
    )


def _twiml_reply(text: str):
    """Always returns a *valid* TwiML response, even in fallback/error paths,
    so Twilio never shows the user a generic 'could not process' error."""
    if TWILIO_AVAILABLE:
        resp = MessagingResponse()
        resp.message(text)
        return str(resp), 200, {"Content-Type": "application/xml"}
    # No twilio package: hand-roll minimal valid TwiML so Twilio can still
    # parse the response (better than JSON, which Twilio will reject).
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escaped}</Message></Response>'
    return xml, 200, {"Content-Type": "application/xml"}


# ---------------------------------------------------------------------------
# Webhook: this is where WhatsApp/Twilio POSTs inbound messages
# ---------------------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    try:
        incoming_msg = request.values.get("Body", "").strip()
        from_number = request.values.get("From", "")  # e.g. 'whatsapp:+9230012345'
        profile_name = request.values.get("ProfileName", "")

        if not incoming_msg or not from_number:
            print(f"[webhook] Missing Body or From. Raw form data: {dict(request.values)}")
            return _twiml_reply("Sorry, I didn't catch that - could you send that again?")

        extraction = extract_lead_info(incoming_msg)

        lead, is_new = crm.add_or_update_lead(
            phone=from_number,
            message_text=incoming_msg,
            name=profile_name or extraction.get("name", ""),
            email=extraction.get("email", ""),
            interest=extraction.get("interest", ""),
            status=extraction.get("status"),
            source="whatsapp",
        )

        reply_text = generate_auto_reply(incoming_msg, extraction)
        print(f"[webhook] {'NEW' if is_new else 'UPDATED'} lead {lead.lead_id} ({lead.phone}) -> status={lead.status}")
        return _twiml_reply(reply_text)

    except Exception:
        # Never let an unexpected error bubble up as a raw 500 - Twilio would
        # show the WhatsApp user a generic error with no way for you to debug
        # it. Instead: log the full traceback to your terminal (this is what
        # you should screenshot/copy if you need help), and still reply.
        import traceback
        print("[webhook] ERROR while processing inbound message:")
        traceback.print_exc()
        return _twiml_reply("Thanks for your message! We're looking into a small hiccup - we'll be in touch shortly.")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html", statuses=config.LEAD_STATUSES)


@app.route("/api/leads")
def api_leads():
    leads = crm.get_all_leads()
    leads.sort(key=lambda l: l.last_contact, reverse=True)
    return jsonify([l.to_row() for l in leads])


@app.route("/api/stats")
def api_stats():
    return jsonify(crm.stats())


@app.route("/api/leads/<lead_id>/status", methods=["POST"])
def api_update_status(lead_id):
    new_status = request.json.get("status") if request.is_json else request.form.get("status")
    try:
        lead = crm.update_status(lead_id, new_status)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    return jsonify(lead.to_row())


@app.route("/api/leads/export")
def api_export():
    leads = crm.get_all_leads()
    buf = io.StringIO()
    writer = csv_module.DictWriter(buf, fieldnames=list(leads[0].to_row().keys()) if leads else
                                    ["lead_id", "name", "phone", "email", "interest",
                                     "last_message", "status", "source", "first_contact",
                                     "last_contact", "message_count", "notes"])
    writer.writeheader()
    for l in leads:
        writer.writerow(l.to_row())
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name="safex_leads_export.csv")


# ---------------------------------------------------------------------------
# Demo helper (no Twilio account needed) - used for the assignment video
# ---------------------------------------------------------------------------
@app.route("/api/demo/simulate", methods=["POST"])
def api_demo_simulate():
    payload = request.get_json(force=True)
    message = payload.get("message", "")
    phone = payload.get("phone", "+923001234567")
    name = payload.get("name", "")

    extraction = extract_lead_info(message)
    lead, is_new = crm.add_or_update_lead(
        phone=phone,
        message_text=message,
        name=name or extraction.get("name", ""),
        email=extraction.get("email", ""),
        interest=extraction.get("interest", ""),
        status=extraction.get("status"),
        source="demo",
    )
    reply = generate_auto_reply(message, extraction)
    return jsonify({
        "extraction": extraction,
        "reply": reply,
        "lead": lead.to_row(),
        "is_new": is_new,
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "backend": crm.backend})


if __name__ == "__main__":
    app.run(debug=config.DEBUG, port=config.PORT, host="0.0.0.0")
