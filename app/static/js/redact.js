const MAX_FILE_MB = 15;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const MAX_FILES = 25;

const rulesContainer = document.getElementById("redaction-rules");
const addRuleBtn = document.getElementById("add-rule-btn");
const form = document.getElementById("redact-form");
const progressEl = document.getElementById("redact-progress");
const resultsEl = document.getElementById("redact-results");
const submitBtn = document.getElementById("redact-submit-btn");

function addOption(select, value, text) {
  const opt = document.createElement("option");
  opt.value = value;
  opt.textContent = text;
  select.appendChild(opt);
}

function addRuleRow() {
  const row = document.createElement("div");
  row.className = "rule-row";

  const label = document.createElement("input");
  label.type = "text";
  label.className = "rule-label";
  label.placeholder = "Label e.g. TFN";

  const typeSelect = document.createElement("select");
  typeSelect.className = "rule-type";
  addOption(typeSelect, "format", "Format template");
  addOption(typeSelect, "regex", "Regex");

  const pattern = document.createElement("input");
  pattern.type = "text";
  pattern.className = "rule-pattern";
  pattern.placeholder = "e.g. 999 999 999";

  const modeSelect = document.createElement("select");
  modeSelect.className = "rule-mode";
  addOption(modeSelect, "mask", "Mask (xxxxxxxxx)");
  addOption(modeSelect, "label", "Label (<TAG>)");

  const checkBtn = document.createElement("button");
  checkBtn.type = "button";
  checkBtn.className = "rule-check";
  checkBtn.textContent = "Check";

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.textContent = "Remove";
  removeBtn.addEventListener("click", () => row.remove());

  const warning = document.createElement("div");
  warning.className = "rule-warning";

  checkBtn.addEventListener("click", async () => {
    warning.textContent = "Checking...";
    warning.className = "rule-warning";
    try {
      const res = await fetch("/redact/validate-rule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: label.value.trim(),
          pattern_type: typeSelect.value,
          pattern: pattern.value.trim(),
        }),
      });
      const data = await res.json();
      if (data.ok) {
        warning.textContent = "Looks OK.";
        warning.className = "rule-warning ok";
      } else {
        warning.textContent = data.problems.join(" ");
        warning.className = "rule-warning error";
      }
    } catch (err) {
      warning.textContent = String(err);
      warning.className = "rule-warning error";
    }
  });

  row.append(label, typeSelect, pattern, modeSelect, checkBtn, removeBtn, warning);
  rulesContainer.appendChild(row);
}

addRuleBtn.addEventListener("click", () => addRuleRow());
addRuleRow();

function collectRules() {
  const mode = document.getElementById("preset-mode").value;
  const presets = Array.from(document.querySelectorAll(".preset-check:checked")).map((c) => ({ preset: c.value, mode }));
  const custom = Array.from(rulesContainer.querySelectorAll(".rule-row"))
    .map((row) => ({
      label: row.querySelector(".rule-label").value.trim(),
      pattern_type: row.querySelector(".rule-type").value,
      pattern: row.querySelector(".rule-pattern").value.trim(),
      mode: row.querySelector(".rule-mode").value,
    }))
    .filter((r) => r.label && r.pattern);
  return [...presets, ...custom];
}

const filesInput = form.querySelector('input[name="files"]');
filesInput.addEventListener("change", () => {
  if (!filesInput.files.length) return;
  const oversized = Array.from(filesInput.files).filter((f) => f.size > MAX_FILE_BYTES).map((f) => f.name);
  if (oversized.length) {
    alert(`The following file(s) exceed the ${MAX_FILE_MB} MB limit and were removed:\n` + oversized.join("\n"));
    filesInput.value = "";
    return;
  }
  if (filesInput.files.length > MAX_FILES) {
    alert(`You can redact at most ${MAX_FILES} files at a time (selected ${filesInput.files.length}).`);
    filesInput.value = "";
  }
});

function showError(messages) {
  resultsEl.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = messages.join("\n");
  resultsEl.appendChild(box);
}

function renderSummary(summary, downloadPath) {
  resultsEl.innerHTML = "";
  const table = document.createElement("table");
  table.className = "results-table";
  table.innerHTML = "<thead><tr><th>File</th><th>Status</th><th>Redactions</th></tr></thead>";
  const tbody = document.createElement("tbody");
  summary.forEach((r) => {
    const tr = document.createElement("tr");

    const fileTd = document.createElement("td");
    fileTd.textContent = r.filename;

    const statusTd = document.createElement("td");
    statusTd.textContent = r.ok ? "Redacted" : `Failed: ${r.error}`;
    statusTd.className = r.ok ? "status-ok" : "status-error";

    const countsTd = document.createElement("td");
    countsTd.textContent = r.ok
      ? Object.entries(r.redacted_counts).map(([k, v]) => `${k}: ${v}`).join(", ") || "no matches"
      : "-";

    tr.append(fileTd, statusTd, countsTd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  resultsEl.appendChild(table);

  if (downloadPath) {
    const link = document.createElement("a");
    link.href = "/download/" + downloadPath.split("/").map(encodeURIComponent).join("/");
    link.textContent = "Download redacted files (.zip)";
    link.className = "block-link";
    resultsEl.appendChild(link);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  const rules = collectRules();
  if (!rules.length) {
    alert("Tick at least one common format or add a custom rule with a label and pattern.");
    return;
  }

  submitBtn.disabled = true;
  progressEl.classList.remove("hidden");
  resultsEl.innerHTML = "";

  const formData = new FormData(form);
  formData.set("rules_json", JSON.stringify(rules));

  try {
    const res = await fetch("/redact/submit", { method: "POST", body: formData });
    const data = await res.json();
    if (!data.ok) {
      showError(data.errors || ["Submission failed."]);
      submitBtn.disabled = false;
      return;
    }
    renderSummary(data.summary, data.download_path);
    submitBtn.disabled = false;
  } catch (err) {
    showError([String(err)]);
    submitBtn.disabled = false;
  }
});
