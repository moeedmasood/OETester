const MAX_FILE_MB = 15;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const MAX_FILES = 25;
const DOWNLOAD_COUNTDOWN_SECONDS = 60;

const form = document.getElementById("anonymise-form");
const progressEl = document.getElementById("anonymise-progress");
const stepsEl = document.getElementById("anonymise-progress-steps");
const resultsEl = document.getElementById("anonymise-results");
const submitBtn = document.getElementById("anonymise-submit-btn");

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
    alert(`You can anonymise at most ${MAX_FILES} files at a time (selected ${filesInput.files.length}).`);
    filesInput.value = "";
  }
});

let pollTimer = null;

function showError(messages) {
  resultsEl.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = messages.join("\n");
  resultsEl.appendChild(box);
}

function renderSteps(steps) {
  stepsEl.innerHTML = "";
  steps.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = s;
    stepsEl.appendChild(li);
  });
}

// Fades the download link out after DOWNLOAD_COUNTDOWN_SECONDS, per the anonymisation service's short-lived link.
function startDownloadCountdown(anchor) {
  let remaining = DOWNLOAD_COUNTDOWN_SECONDS;
  const update = () => { anchor.textContent = `Download (${remaining}s)`; };
  update();
  const timer = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearInterval(timer);
      const expired = document.createElement("span");
      expired.className = "link-expired";
      expired.textContent = "Link expired";
      anchor.replaceWith(expired);
      return;
    }
    update();
  }, 1000);
}

function renderResults(results) {
  resultsEl.innerHTML = "";
  const table = document.createElement("table");
  table.className = "results-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>File</th><th>Status</th><th>Download</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  results.forEach((r) => {
    const tr = document.createElement("tr");

    const fileTd = document.createElement("td");
    fileTd.textContent = r.filename;

    const statusTd = document.createElement("td");
    statusTd.textContent = r.ok ? `Anonymised (${r.redacted_entity_count} entities)` : `Failed: ${r.error}`;
    statusTd.className = r.ok ? "status-ok" : "status-error";

    const downloadTd = document.createElement("td");
    if (r.ok && r.download_url) {
      const anchor = document.createElement("a");
      anchor.href = r.download_url;
      anchor.target = "_blank";
      anchor.rel = "noopener";
      downloadTd.appendChild(anchor);
      startDownloadCountdown(anchor);
    } else {
      downloadTd.textContent = "-";
    }

    tr.append(fileTd, statusTd, downloadTd);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  resultsEl.appendChild(table);
}

function pollStatus(jobId) {
  pollTimer = setInterval(async () => {
    const res = await fetch(`/status/${jobId}`);
    const data = await res.json();
    if (!data.ok) {
      clearInterval(pollTimer);
      showError([data.error || "Unknown error polling job status."]);
      submitBtn.disabled = false;
      return;
    }

    renderSteps(data.steps);

    if (data.status === "done") {
      clearInterval(pollTimer);
      renderResults(data.result || []);
      submitBtn.disabled = false;
    } else if (data.status === "error") {
      clearInterval(pollTimer);
      showError([data.error || "Processing failed."]);
      submitBtn.disabled = false;
    }
  }, 1500);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.checkValidity()) {
    form.reportValidity();
    return;
  }
  const checked = form.querySelectorAll('input[name="entity_types"]:checked');
  if (!checked.length) {
    alert("Select at least one type of information to anonymise.");
    return;
  }

  submitBtn.disabled = true;
  progressEl.classList.remove("hidden");
  stepsEl.innerHTML = "";
  resultsEl.innerHTML = "";

  const formData = new FormData(form);
  try {
    const res = await fetch("/anonymise/submit", { method: "POST", body: formData });
    const data = await res.json();
    if (!data.ok) {
      showError(data.errors || ["Submission failed."]);
      submitBtn.disabled = false;
      return;
    }
    pollStatus(data.job_id);
  } catch (err) {
    showError([String(err)]);
    submitBtn.disabled = false;
  }
});
