const $ = (sel) => document.querySelector(sel);

let selectedFile = null;
let currentReport = null;
const pollers = new Map();

// --- Upload ----------------------------------------------------------------
const fileInput = $("#file-input");
const dropzone = $("#dropzone");
const dzText = $("#dropzone-text");
const uploadBtn = $("#upload-btn");

dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => fileInput.files.length && setFile(fileInput.files[0]));

function setFile(f) {
  selectedFile = f;
  dzText.textContent = `📄 ${f.name}`;
  uploadBtn.disabled = false;
}

$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedFile) return;
  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading…";
  const fd = new FormData();
  fd.append("file", selectedFile);
  try {
    const res = await fetch("/api/datasets/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
    const { dataset_id } = await res.json();
    selectedFile = null;
    dzText.textContent = "Click to choose a CSV, or drag it here";
    await loadDatasets();
    pollDataset(dataset_id);
  } catch (err) {
    alert(err.message);
  } finally {
    uploadBtn.textContent = "Analyze";
  }
});

// --- Datasets list ---------------------------------------------------------
$("#refresh-btn").addEventListener("click", loadDatasets);

async function loadDatasets() {
  const res = await fetch("/api/datasets");
  const rows = await res.json();
  const body = $("#datasets-body");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted center">No datasets yet.</td></tr>`;
    return;
  }
  body.innerHTML = rows.map((d) => `
    <tr>
      <td>${escapeHtml(d.name)}</td>
      <td>${d.source_type}</td>
      <td>${d.row_count || "—"}</td>
      <td><span class="badge ${d.status}">${d.status}</span></td>
      <td>${d.ai_readiness_score != null ? `${d.ai_readiness_score} (${d.grade})` : "—"}</td>
      <td>${d.status === "done" ? `<a class="link" data-id="${d.id}">View report →</a>` : ""}</td>
    </tr>`).join("");
  body.querySelectorAll("a.link").forEach((a) =>
    a.addEventListener("click", () => openReport(a.dataset.id)));
}

function pollDataset(id) {
  if (pollers.has(id)) return;
  const t = setInterval(async () => {
    const res = await fetch(`/api/datasets/${id}`);
    const d = await res.json();
    if (d.status === "done" || d.status === "failed") {
      clearInterval(t);
      pollers.delete(id);
      await loadDatasets();
      if (d.status === "done") openReport(id);
      else alert(`Analysis failed: ${d.error || "unknown error"}`);
    }
  }, 1200);
  pollers.set(id, t);
}

// --- Report ----------------------------------------------------------------
$("#close-report").addEventListener("click", () => $("#report-card").classList.add("hidden"));
$("#export-btn").addEventListener("click", () => {
  if (!currentReport) return;
  const blob = new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${currentReport.dataset.name || "report"}.contextra.json`;
  a.click();
});

async function openReport(id) {
  const res = await fetch(`/api/datasets/${id}/report`);
  const r = await res.json();
  currentReport = r;
  renderReport(r);
  $("#report-card").classList.remove("hidden");
  $("#report-card").scrollIntoView({ behavior: "smooth" });
}

function gradeColor(score) {
  if (score >= 80) return "var(--accent-2)";
  if (score >= 60) return "var(--warn)";
  return "var(--danger)";
}

function renderReport(r) {
  const s = r.ai_score;
  const prof = r.profile?.columns || {};
  const sem = r.semantic_map?.columns || {};
  const body = $("#report-body");

  if (!s) {
    body.innerHTML = `<p class="muted">No score available (status: ${r.dataset.status}).</p>`;
    return;
  }

  const color = gradeColor(s.ai_readiness_score);
  const gauge = `
    <div class="gauge" style="background: conic-gradient(${color} ${s.ai_readiness_score * 3.6}deg, #21262d 0deg);">
      <div class="gauge" style="width:96px;height:96px;background:var(--card);">
        <div class="gauge-inner">
          <div class="gauge-score" style="color:${color}">${s.ai_readiness_score}</div>
          <div class="gauge-grade">Grade ${s.grade}</div>
        </div>
      </div>
    </div>`;

  const dims = Object.entries(s.dimensions).map(([k, v]) => `
    <div class="dim-row">
      <span>${k.replace(/_/g, " ")}</span>
      <span class="bar"><span style="width:${v}%;background:${gradeColor(v)}"></span></span>
      <span>${v}</span>
    </div>`).join("");

  const issues = s.issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("");

  const colRows = Object.entries(prof).map(([name, c]) => {
    const sm = sem[name] || {};
    const conf = sm.confidence != null ? sm.confidence : 0;
    const confClass = conf >= 0.6 ? "conf-high" : "conf-low";
    return `<tr>
      <td>${escapeHtml(name)}</td>
      <td>${sm.semantic_type ? `${escapeHtml(sm.semantic_type)} <span class="${confClass}">(${(conf*100).toFixed(0)}%)</span>` : "—"}</td>
      <td>${(c.null_rate*100).toFixed(1)}%</td>
      <td>${(c.uniqueness*100).toFixed(1)}%</td>
      <td>${c.cardinality}</td>
      <td>${c.pii ? `<span class="pii">${c.pii}</span>` : "—"}</td>
    </tr>`;
  }).join("");

  body.innerHTML = `
    <div class="score-hero">
      ${gauge}
      <div class="dims">${dims}</div>
    </div>

    <div class="section-title">Issues</div>
    <ul class="issues">${issues}</ul>

    <div class="section-title">Semantic map &amp; column profile</div>
    <table>
      <thead><tr><th>Column</th><th>Semantic type</th><th>Null</th><th>Unique</th><th>Cardinality</th><th>PII</th></tr></thead>
      <tbody>${colRows}</tbody>
    </table>
    <p class="hint">Entities detected: ${(r.semantic_map?.entities_detected || []).join(", ") || "—"} ·
       Rows: ${r.dataset.row_count}</p>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// init
loadDatasets();
