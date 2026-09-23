const FIELD_TYPES = ["str", "int", "float", "bool", "date"];

const MAX_WORDS = 100;
const MAX_FILE_MB = 15;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;
const MAX_EXTRACTION_FIELDS = 10;
const MAX_COMPUTE_FIELDS = 5;
const MAX_SAMPLE_FILES = 25;

const testDateInput = document.getElementById("test_date");
if (testDateInput && !testDateInput.value) {
  testDateInput.value = new Date().toLocaleDateString("en-CA");
}

function countWords(text) {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

// Truncates a text/textarea value to MAX_WORDS in place (used for field-builder inputs with no visible counter).
function enforceWordLimit(el) {
  const words = el.value.trim() ? el.value.trim().split(/\s+/) : [];
  if (words.length > MAX_WORDS) {
    el.value = words.slice(0, MAX_WORDS).join(" ");
  }
}

function setupWordCounters() {
  document.querySelectorAll("#oe-form input[type='text'], #oe-form textarea").forEach((el) => {
    const counter = el.nextElementSibling;
    if (!counter || !counter.classList.contains("word-count")) return;
    const update = () => {
      enforceWordLimit(el);
      const words = countWords(el.value);
      counter.textContent = `${words} / ${MAX_WORDS} words`;
      counter.classList.toggle("over-limit", words >= MAX_WORDS);
    };
    el.addEventListener("input", update);
    update();
  });
}
setupWordCounters();

function oversizedFileNames(fileList) {
  return Array.from(fileList)
    .filter((f) => f.size > MAX_FILE_BYTES)
    .map((f) => f.name);
}

function setupFileSizeGuards() {
  document.querySelectorAll('input[type="file"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (!input.files.length) return;
      const oversized = oversizedFileNames(input.files);
      if (oversized.length) {
        alert(`The following file(s) exceed the ${MAX_FILE_MB} MB limit and were removed:\n` + oversized.join("\n"));
        input.value = "";
        return;
      }
      if (input.name === "sample_files" && input.files.length > MAX_SAMPLE_FILES) {
        alert(`You can attach at most ${MAX_SAMPLE_FILES} sample/evidence files (selected ${input.files.length}).`);
        input.value = "";
      }
    });
  });
}
setupFileSizeGuards();

function refreshExtractionFieldNamesDatalist() {
  const datalist = document.getElementById("extraction-field-names");
  if (!datalist) return;
  const names = Array.from(document.querySelectorAll("#extraction-fields .field-name"))
    .map((el) => el.value.trim())
    .filter(Boolean);
  datalist.innerHTML = "";
  names.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    datalist.appendChild(opt);
  });
}

function addFieldRow(containerId, data = {}) {
  const container = document.getElementById(containerId);
  const isComputeField = containerId === "compute-fields";
  const isExtractionField = containerId === "extraction-fields";
  const row = document.createElement("div");
  row.className = isComputeField ? "field-row compute-row" : "field-row";
  if (isExtractionField) row.classList.add("extraction-row");

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "field_name";
  nameInput.className = "field-name";
  nameInput.value = data.name || "";

  const typeSelect = document.createElement("select");
  typeSelect.className = "field-type";
  FIELD_TYPES.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    typeSelect.appendChild(opt);
  });
  typeSelect.value = data.type || "str";

  const descInput = document.createElement("input");
  descInput.type = "text";
  descInput.placeholder = "extraction hint / describe computation";
  descInput.className = "field-desc";
  descInput.value = data.description || "";

  nameInput.addEventListener("input", () => enforceWordLimit(nameInput));
  descInput.addEventListener("input", () => enforceWordLimit(descInput));

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.textContent = "Remove";
  removeBtn.addEventListener("click", () => row.remove());

  const rowChildren = [nameInput, typeSelect, descInput];

  if (isExtractionField) {
    const primaryLabel = document.createElement("label");
    primaryLabel.className = "primary-label";
    const primaryRadio = document.createElement("input");
    primaryRadio.type = "radio";
    primaryRadio.name = "extraction_primary_field";
    primaryRadio.className = "field-primary";
    primaryRadio.checked = Boolean(data.is_primary);
    primaryLabel.append(primaryRadio, document.createTextNode(" Primary"));
    rowChildren.push(primaryLabel);
  }

  if (isComputeField) {
    const source1 = document.createElement("input");
    source1.type = "text";
    source1.placeholder = "source field * (1 required)";
    source1.className = "field-source-1";
    source1.setAttribute("list", "extraction-field-names");
    source1.required = true;
    source1.value = (data.source_fields && data.source_fields[0]) || "";

    const source2 = document.createElement("input");
    source2.type = "text";
    source2.placeholder = "source field (optional, max 2)";
    source2.className = "field-source-2";
    source2.setAttribute("list", "extraction-field-names");
    source2.value = (data.source_fields && data.source_fields[1]) || "";

    rowChildren.push(source1, source2);
  }

  rowChildren.push(removeBtn);
  row.append(...rowChildren);
  container.appendChild(row);

  if (isExtractionField && !container.querySelector(".field-primary:checked")) {
    row.querySelector(".field-primary").checked = true;
  }

  if (containerId === "extraction-fields") {
    refreshExtractionFieldNamesDatalist();
  }
}

function populateFieldsBuilder(containerId, fields) {
  const container = document.getElementById(containerId);
  const max = containerId === "extraction-fields" ? MAX_EXTRACTION_FIELDS : MAX_COMPUTE_FIELDS;
  const label = containerId === "extraction-fields" ? "Extraction Structure" : "Compute Structure";
  container.innerHTML = "";
  let limited = fields;
  if (fields.length > max) {
    limited = fields.slice(0, max);
    alert(`${label} is limited to ${max} fields; only the first ${max} rows were loaded.`);
  }
  if (!limited.length) {
    addFieldRow(containerId);
    return;
  }
  limited.forEach((f) => addFieldRow(containerId, f));
  if (containerId === "extraction-fields") refreshExtractionFieldNamesDatalist();
}

function collectFields(containerId) {
  const container = document.getElementById(containerId);
  const fields = [];
  container.querySelectorAll(".field-row").forEach((row) => {
    const name = row.querySelector(".field-name").value.trim();
    if (!name) return;
    const field = {
      name,
      type: row.querySelector(".field-type").value,
      description: row.querySelector(".field-desc").value.trim(),
    };
    const primaryRadio = row.querySelector(".field-primary");
    if (primaryRadio) {
      field.is_primary = primaryRadio.checked;
    }
    const source1 = row.querySelector(".field-source-1");
    if (source1) {
      const source2 = row.querySelector(".field-source-2");
      field.source_fields = [source1.value.trim(), source2 ? source2.value.trim() : ""].filter(Boolean);
    }
    fields.push(field);
  });
  return fields;
}

document.querySelectorAll(".add-field").forEach((btn) => {
  btn.addEventListener("click", () => {
    const targetId = btn.dataset.target;
    const max = targetId === "extraction-fields" ? MAX_EXTRACTION_FIELDS : MAX_COMPUTE_FIELDS;
    const label = targetId === "extraction-fields" ? "Extraction Structure" : "Compute Structure";
    const current = document.querySelectorAll(`#${targetId} .field-row`).length;
    if (current >= max) {
      alert(`${label} is limited to ${max} fields.`);
      return;
    }
    addFieldRow(targetId);
  });
});

document.getElementById("extraction-fields").addEventListener("input", (event) => {
  if (event.target.classList.contains("field-name")) refreshExtractionFieldNamesDatalist();
});

function downloadFieldsCsv(containerId, fileBaseName) {
  const fields = collectFields(containerId);
  const hasSourceFields = fields.some((f) => f.source_fields);
  const hasPrimary = fields.some((f) => "is_primary" in f);
  const header = ["name", "type", "description"];
  if (hasSourceFields) header.push("source_fields");
  if (hasPrimary) header.push("primary");
  const rows = [
    header,
    ...fields.map((f) => {
      const cells = [f.name, f.type, f.description];
      if (hasSourceFields) cells.push((f.source_fields || []).join("|"));
      if (hasPrimary) cells.push(f.is_primary ? "true" : "false");
      return cells;
    }),
  ];
  const csv = rows
    .map((r) => r.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${fileBaseName}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

document.querySelectorAll(".download-fields").forEach((btn) => {
  btn.addEventListener("click", () => downloadFieldsCsv(btn.dataset.target, btn.dataset.name));
});

function setupFieldsModeToggle(modeName, manualId, uploadId) {
  const radios = document.querySelectorAll(`input[name="${modeName}"]`);
  const manualEl = document.getElementById(manualId);
  const uploadEl = document.getElementById(uploadId);
  radios.forEach((radio) => {
    radio.addEventListener("change", () => {
      const isUpload = radio.value === "upload" && radio.checked;
      if (radio.checked) {
        manualEl.classList.toggle("hidden", isUpload);
        uploadEl.classList.toggle("hidden", !isUpload);
      }
    });
  });
}

setupFieldsModeToggle("extraction_fields_mode", "extraction-fields-manual", "extraction-fields-upload");
setupFieldsModeToggle("compute_fields_mode", "compute-fields-manual", "compute-fields-upload");

async function handleFieldsFilePreview(fileInput, containerId, modeName, manualId, uploadId) {
  const file = fileInput.files[0];
  if (!file) return;

  const previewData = new FormData();
  previewData.append("file", file);

  try {
    const res = await fetch("/parse-fields-file", { method: "POST", body: previewData });
    const data = await res.json();
    if (!data.ok) {
      alert(data.error || "Could not read the uploaded file.");
      return;
    }

    populateFieldsBuilder(containerId, data.fields);

    // Fields are now shown as manual rows; clear the file input so submit uses the JSON path.
    fileInput.value = "";
    document.querySelector(`input[name="${modeName}"][value="manual"]`).checked = true;
    document.getElementById(manualId).classList.remove("hidden");
    document.getElementById(uploadId).classList.add("hidden");
  } catch (err) {
    alert(String(err));
  }
}

document.querySelector('input[name="extraction_fields_file"]').addEventListener("change", (event) =>
  handleFieldsFilePreview(event.target, "extraction-fields", "extraction_fields_mode", "extraction-fields-manual", "extraction-fields-upload")
);
document.querySelector('input[name="compute_fields_file"]').addEventListener("change", (event) =>
  handleFieldsFilePreview(event.target, "compute-fields", "compute_fields_mode", "compute-fields-manual", "compute-fields-upload")
);

// seed each builder with one empty row
addFieldRow("extraction-fields");
addFieldRow("compute-fields");

const form = document.getElementById("oe-form");
const progressEl = document.getElementById("progress");
const stepsEl = document.getElementById("progress-steps");
const resultEl = document.getElementById("progress-result");
const submitBtn = document.getElementById("submit-btn");

let pollTimer = null;

function showError(messages) {
  resultEl.innerHTML = "";
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = messages.join("\n");
  resultEl.appendChild(box);
}

function renderSteps(steps) {
  stepsEl.innerHTML = "";
  steps.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = s;
    stepsEl.appendChild(li);
  });
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
      resultEl.innerHTML = "";
      const link = document.createElement("a");
      link.href = `/download/${encodeURIComponent(data.output_filename)}`;
      link.textContent = `Download ${data.output_filename}`;
      resultEl.appendChild(link);
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

  const sampleFilesInput = form.querySelector('input[name="sample_files"]');
  const excelExtensions = ["xlsx", "xls", "csv"];
  const hasExcelSample = Array.from(sampleFilesInput.files).some((f) =>
    excelExtensions.includes(f.name.split(".").pop().toLowerCase())
  );
  if (hasExcelSample) {
    const proceed = confirm(
      "One or more of your Sample Files is an Excel/CSV file. Before continuing, please confirm:\n\n" +
        "1. Extraction Structure field names exactly match the column headings in the Excel/CSV file.\n" +
        "2. The data is laid out as a table (one header row, one sample per data row).\n" +
        "3. The Primary field's value is unique for each row, the same way it must uniquely identify each sample document.\n\n" +
        "Click OK to continue, or Cancel to go back and check your file."
    );
    if (!proceed) return;
  }

  submitBtn.disabled = true;
  progressEl.classList.remove("hidden");
  stepsEl.innerHTML = "";
  resultEl.innerHTML = "";

  const formData = new FormData(form);
  const extractionMode = form.extraction_fields_mode.value;
  const computeMode = form.compute_fields_mode.value;
  formData.set(
    "extraction_fields_json",
    extractionMode === "manual" ? JSON.stringify(collectFields("extraction-fields")) : "[]"
  );
  formData.set(
    "compute_fields_json",
    computeMode === "manual" ? JSON.stringify(collectFields("compute-fields")) : "[]"
  );
  formData.set("ignore_sample_mismatch", form.ignore_sample_mismatch.checked ? "true" : "false");

  try {
    const res = await fetch("/submit", { method: "POST", body: formData });
    const data = await res.json();
    if (!data.ok) {
      showError(data.errors || ["Submission failed."]);
      submitBtn.disabled = false;
      return;
    }
    pollStatus(data.job_id);
  } catch (err) {
    // Chrome/Edge report a modified-on-disk file (e.g. still open/autosaving in Excel,
    // or being re-synced by OneDrive) as a generic "Failed to fetch" TypeError.
    if (err instanceof TypeError && /fetch/i.test(err.message)) {
      showError([
        "Upload failed before reaching the server (network error). This usually happens when " +
          "one of the selected files changed on disk while uploading - e.g. it was still open " +
          "in Excel, or OneDrive was re-syncing it. Close the file, wait for OneDrive to finish " +
          "syncing, then reselect it and try again.",
      ]);
    } else {
      showError([String(err)]);
    }
    submitBtn.disabled = false;
  }
});
