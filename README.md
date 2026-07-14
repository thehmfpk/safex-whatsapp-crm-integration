# SafeX Solutions — WhatsApp Auto-Reply Bot

## CRM Integration Module

**Group 53 · Week 2 individual contribution**

This is the **CRM Integration** component of the group's WhatsApp Auto-Reply
Bot: it takes leads captured by the bot, **de-duplicates** them by phone
number, **tags their pipeline status** automatically using an LLM, and
stores everything in a simple CRM (a CSV "sheet" by default, or an
Airtable base if you configure it) plus a live dashboard to view it all.

## Screenshots

### CRM Page

![CRM](images/CRM.png)
![CRM2](images/CRM2.png)

### whatsapp

![whatsapp](images/whatsapp.png)
---

## 1. What this module does

```
WhatsApp user sends a message
        │
        ▼
Twilio WhatsApp Sandbox ──POST /webhook──▶ app.py (Flask)
                                               │
                                               ▼
                                  llm_helper.py → Groq LLM API
                                  extracts: name, email, interest,
                                  status (New/Contacted/Qualified/
                                  Converted/Lost), sentiment
                                               │
                                               ▼
                                  crm.py → CRMClient
                                  • de-duplicates by phone number
                                  • escalates status (never downgrades
                                    a Converted/Lost lead by accident)
                                  • saves to data/leads.csv (or Airtable)
                                               │
                                               ▼
                            Dashboard at http://localhost:5000
                     (blue / black / white themed live CRM view)
```

---

## 2. Project structure

```
whatsapp-crm-integration/
├── app.py                  Flask server: webhook + dashboard + JSON API
├── crm.py                  Core CRM logic: de-dup, status tagging, CSV storage
├── airtable_backend.py     Optional Airtable storage backend
├── llm_helper.py           Groq LLM call + regex fallback extractor
├── config.py                Central settings (reads from .env)
├── seed_demo_data.py        Populates sample leads for screenshots/demo
├── requirements.txt
├── .env          
├── data/
│   └── leads.csv             The "CRM sheet" (auto-created, already seeded
│                              with sample leads for you to explore)
├── templates/
│   └── dashboard.html
├── static/
│   ├── style.css             Blue / black / white brand theme
│   ├── script.js
│   └── img/logo.png
├── tests/
│   └── sample_messages.json  Sample WhatsApp messages for testing
└── notebook/
    └── CRM_Integration_Demo.ipynb   Step-by-step demo notebook
```

---

## 3. Setup (Windows + VS Code)

1. **Install Python 3.10+** if you don't have it: https://www.python.org/downloads/
2. Open the project folder in VS Code.
3. Open a terminal in VS Code (``Ctrl+` ``) and run:

   ```powershell
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Copy the environment template and add your keys:

   ```powershell
   copy .env.example .env
   ```

   Open `.env` in VS Code and set at minimum:

   ```
   GROQ_API_KEY=gsk_your_key_here
   ```
5. **Get a free Groq API key** (no credit card): go to
   https://console.groq.com → sign up → **API Keys** → **Create API Key**.
   Paste it into `.env`.
6. Run the app:

   ```powershell
   python app.py
   ```
7. Open **http://127.0.0.1:5000** in your browser — you'll see the
   dashboard already populated with sample leads (seeded ahead of time so
   you have something to screenshot immediately).
8. To reset and re-generate the sample data at any point:

   ```powershell
   del data\leads.csv
   python seed_demo_data.py
   ```

---

## 4. Setup (Google Colab)

Colab is great for the **notebook demo** (`notebook/CRM_Integration_Demo.ipynb`)
but can't host a persistent Flask server for the dashboard — use Colab
for the notebook part, and VS Code / your own machine to run `app.py` for
the live dashboard.

1. Upload `notebook/CRM_Integration_Demo.ipynb` to Colab (File → Upload notebook).
2. Also upload `config.py`, `crm.py`, `llm_helper.py`, `airtable_backend.py`
   from this repo into the Colab file browser (left sidebar → upload) — the
   notebook's first cell will prompt you for these if they're missing.
3. Run the cells top to bottom. Paste your Groq key into the designated
   cell when prompted (or leave it blank to use the offline fallback
   extractor).

---

## 5. Connecting to real WhatsApp messages (Twilio Sandbox — free)

1. Create a free Twilio account: https://console.twilio.com
2. Go to **Messaging → Try it out → Send a WhatsApp message** to activate
   the WhatsApp Sandbox. You'll get a sandbox number and a join code
   (e.g. "join example-word") — send that from your own WhatsApp to the
   sandbox number to opt in.
3. Copy your **Account SID** and **Auth Token** from the Twilio console
   into `.env`:

   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. Expose your local Flask server to the internet with **ngrok** (free):

   ```powershell
   ngrok http 5000
   ```

   Copy the `https://....ngrok-free.app` URL it gives you.
5. In the Twilio console, under the WhatsApp Sandbox settings, set
   **"When a message comes in"** to:

   ```
   https://YOUR-NGROK-URL/webhook
   ```

   Method: `POST`.
6. Send a WhatsApp message to your Twilio sandbox number from your phone —
   it will appear in the dashboard within a couple of seconds, and you'll
   get an auto-reply back.

---

## 6. Using Airtable instead of the CSV sheet (optional)

The assignment scope says "a simple CRM sheet **or** Airtable base" — CSV
is the zero-setup default, but Airtable is fully supported:

1. `pip install pyairtable` (already in requirements.txt).
2. Create a free Airtable base with a table called `Leads` containing
   these columns (all "Single line text" except `message_count`, which
   should be "Number"): `lead_id, name, phone, email, interest, last_message, status, source, first_contact, last_contact, message_count, notes`.
3. Get your API key (Airtable → Account → Developer hub → Personal access
   tokens) and your Base ID (from the base's API docs page).
4. In `.env`:
   ```
   CRM_BACKEND=airtable
   AIRTABLE_API_KEY=pat_xxxxxxxxxxxxxxxxxx
   AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX
   AIRTABLE_TABLE_NAME=Leads
   ```
5. Restart `app.py` — leads now read/write straight to Airtable, and the
   dashboard/API work exactly the same either way.

---

## 7. How de-duplication & status tagging work (the core logic)

- **De-duplication key:** the WhatsApp phone number, normalized (strips
  `whatsapp:` prefix, spaces, dashes; adds a `+` country code) so the same
  person always maps to the same record no matter how their number is
  formatted in different messages.
- **On a repeat message from a known number:** the existing lead is
  **updated in place** (message count increments, last message/timestamp
  refresh, any newly-learned name/email fills in blanks) — never
  duplicated.
- **Status tagging:** each inbound message is classified by the LLM (or
  the offline fallback) into one of `New → Contacted → Qualified → Converted / Lost`. The pipeline only ever moves **forward**: a lead
  already marked `Converted` or `Lost` won't get bumped back to `New`
  just because they send a casual follow-up message.

This logic lives entirely in `crm.py` (`CRMClient.add_or_update_lead`) and
is unit-testable independent of Flask/Twilio — see
`notebook/CRM_Integration_Demo.ipynb`, section 5, for a runnable
de-duplication check with an assertion.

---

## 8. API reference (for the other group members' modules)

| Route                      | Method | Purpose                                                                   |
| -------------------------- | ------ | ------------------------------------------------------------------------- |
| `/webhook`               | POST   | Twilio inbound WhatsApp webhook                                           |
| `/`                      | GET    | CRM dashboard (HTML)                                                      |
| `/api/leads`             | GET    | All leads as JSON                                                         |
| `/api/stats`             | GET    | Pipeline counts as JSON                                                   |
| `/api/leads/<id>/status` | POST   | Manually change a lead's status                                           |
| `/api/leads/export`      | GET    | Download`leads.csv`                                                     |
| `/api/demo/simulate`     | POST   | Test the pipeline without Twilio — body:`{"name", "phone", "message"}` |
| `/health`                | GET    | Health check + active storage backend                                     |

---

## 9. Sample data

`tests/sample_messages.json` and the pre-seeded `data/leads.csv` are
modeled on SafeX Solutions' actual service lines (from
safexsolutions.com): **Web Development, Cybersecurity Solutions, AI
Automation, Digital Marketing, Creative Media Services, and the Skill
Development Centre**. This makes the dashboard/demo look like genuine
SafeX customer inquiries rather than generic placeholder text — handy
for the assignment screenshots/video. Feel free to edit
`tests/sample_messages.json` and re-run `seed_demo_data.py` any time.

## 10. Testing without any external accounts

Run the seed script any time to push realistic sample data through the
**real** pipeline (extraction → de-dup → tagging) so the dashboard always
has something to look at:

```bash
python seed_demo_data.py
```

Or use the **"Try it"** box on the dashboard itself — it calls
`/api/demo/simulate` directly from the browser, no Postman/curl needed.

---

## 11. Tech stack (matches the assignment's required technologies)

- **Python** — all backend logic
- **Pandas** — used in the notebook for tabular lead analysis
- **LLM API (Groq, free tier)** — structured lead extraction & status
  classification, in place of a from-scratch NLP model, per the
  "spaCy/NLTK **or** an LLM API" option in the brief
- **Flask** — serves the webhook, dashboard, and JSON API
- **Twilio WhatsApp Sandbox API** — real WhatsApp message delivery

---

## 12. Deliverables checklist (per assignment brief)

- Jupyter notebook with sample input/output — `notebook/CRM_Integration_Demo.ipynb`
- Source code / working files — this whole repo
- Written documentation — this README
- Screenshots / short recording — run `python app.py`, seed the demo
  data, and record your screen walking through the dashboard + the
  "Try it" simulator + a real WhatsApp message via the Twilio sandbox
