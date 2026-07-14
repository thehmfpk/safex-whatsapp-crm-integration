// SafeX Solutions — CRM Dashboard client logic
// Talks to the Flask API (/api/leads, /api/stats, /api/demo/simulate)

const STATUSES = ["New", "Contacted", "Qualified", "Converted", "Lost"];

let allLeads = [];

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function renderPipeline(stats) {
  const el = document.getElementById("pipeline");
  el.innerHTML = STATUSES.map(
    (s) => `
    <div class="pipe-stage" data-stage="${s}">
      <div class="pipe-label"><span class="dot"></span>${s}</div>
      <div class="pipe-count">${stats[s.toLowerCase()] ?? 0}</div>
    </div>`
  ).join("");
}

function badgeFor(status) {
  return `<span class="badge badge-${status}" data-lead-badge>
      <span class="chevron" style="color:inherit"></span>${status}
    </span>`;
}

function renderTable(leads) {
  const body = document.getElementById("leadsBody");
  const empty = document.getElementById("emptyState");

  if (!leads.length) {
    body.innerHTML = "";
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  body.innerHTML = leads
    .map((l) => {
      return `
      <tr data-lead-id="${l.lead_id}">
        <td>
          <div class="lead-name">${escapeHtml(l.name || "Unknown")}</div>
          <div class="lead-source">${escapeHtml(l.source || "whatsapp")}</div>
        </td>
        <td class="mono">${escapeHtml(l.phone)}</td>
        <td class="msg-preview" title="${escapeHtml(l.last_message)}">${escapeHtml(l.last_message)}</td>
        <td>${escapeHtml(l.interest || "—")}</td>
        <td>
          <select class="status-select" data-lead-id="${l.lead_id}">
            ${STATUSES.map(
              (s) => `<option value="${s}" ${s === l.status ? "selected" : ""}>${s}</option>`
            ).join("")}
          </select>
        </td>
        <td class="mono">${l.message_count}</td>
        <td class="mono">${escapeHtml(l.last_contact)}</td>
      </tr>`;
    })
    .join("");

  document.querySelectorAll(".status-select").forEach((sel) => {
    sel.className = `status-select badge badge-${sel.value}`;
    sel.addEventListener("change", async (e) => {
      const leadId = e.target.dataset.leadId;
      const newStatus = e.target.value;
      await fetchJSON(`/api/leads/${leadId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      e.target.className = `status-select badge badge-${newStatus}`;
      loadAll();
    });
  });
}

function applyFilters() {
  const q = document.getElementById("searchInput").value.trim().toLowerCase();
  const status = document.getElementById("statusFilter").value;

  let filtered = allLeads;
  if (status) filtered = filtered.filter((l) => l.status === status);
  if (q) {
    filtered = filtered.filter((l) =>
      [l.name, l.phone, l.interest, l.last_message].join(" ").toLowerCase().includes(q)
    );
  }
  renderTable(filtered);
}

async function loadAll() {
  const [leads, stats] = await Promise.all([
    fetchJSON("/api/leads"),
    fetchJSON("/api/stats"),
  ]);
  allLeads = leads;
  renderPipeline(stats);
  applyFilters();
}

async function loadHealth() {
  try {
    const h = await fetchJSON("/health");
    document.getElementById("backendLabel").textContent = h.backend;
  } catch (e) {
    document.getElementById("backendLabel").textContent = "unknown";
  }
}

document.getElementById("searchInput").addEventListener("input", applyFilters);
document.getElementById("statusFilter").addEventListener("change", applyFilters);
document.getElementById("refreshBtn").addEventListener("click", loadAll);

document.getElementById("demoForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("demoName").value;
  const phone = document.getElementById("demoPhone").value;
  const message = document.getElementById("demoMessage").value;

  const resultBox = document.getElementById("demoResult");
  resultBox.hidden = false;
  resultBox.innerHTML = "Processing…";

  try {
    const data = await fetchJSON("/api/demo/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, phone, message }),
    });

    resultBox.innerHTML = `
      <div class="drow"><span class="dlabel">Detected status</span><strong>${data.extraction.status}</strong></div>
      <div class="drow"><span class="dlabel">Interest</span><strong>${escapeHtml(data.extraction.interest)}</strong></div>
      <div class="drow"><span class="dlabel">Sentiment</span><strong>${data.extraction.sentiment}</strong></div>
      <div class="drow"><span class="dlabel">Lead record</span><strong>${data.is_new ? "Created new lead" : "Updated existing lead (de-duplicated)"} — ${data.lead.lead_id}</strong></div>
      <div class="drow"><span class="dlabel">Bot auto-reply</span><strong>${escapeHtml(data.reply)}</strong></div>
    `;
    document.getElementById("demoMessage").value = "";
    loadAll();
  } catch (err) {
    resultBox.innerHTML = `<span style="color:#f3a1ad">Something went wrong: ${err.message}</span>`;
  }
});

loadHealth();
loadAll();
setInterval(loadAll, 15000); // light auto-refresh so the dashboard feels "live"
