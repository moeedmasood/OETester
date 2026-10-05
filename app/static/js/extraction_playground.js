(function () {
  const MAX_FIELDS = 10;
  const container = document.getElementById("ext-fields");
  const form = document.getElementById("ext-form");
  const submitBtn = document.getElementById("submit-btn");
  const resultBox = document.getElementById("ext-result");
  const errorBox = document.getElementById("ext-error");
  const table = document.getElementById("ext-table");

  function addField() {
    if (container.children.length >= MAX_FIELDS) return;
    const row = document.createElement("div");
    row.className = "field-row";
    row.innerHTML =
      '<input type="text" class="f-name" placeholder="Field name" />' +
      '<select class="f-type"><option value="str">Text</option><option value="int">Integer</option>' +
      '<option value="float">Number</option><option value="bool">Yes/No</option><option value="date">Date</option></select>' +
      '<input type="text" class="f-desc" placeholder="Description" />' +
      '<button type="button">Remove</button>';
    row.querySelector("button").addEventListener("click", () => row.remove());
    container.appendChild(row);
  }

  document.getElementById("ext-add-field").addEventListener("click", addField);
  addField();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fields = [...container.children]
      .map((r) => ({
        name: r.querySelector(".f-name").value.trim(),
        type: r.querySelector(".f-type").value,
        description: r.querySelector(".f-desc").value.trim(),
      }))
      .filter((f) => f.name);

    const fd = new FormData();
    fd.append("model_id", document.getElementById("ext-model").value);
    fd.append("file", document.getElementById("ext-file").files[0]);
    fd.append("fields_json", JSON.stringify(fields));

    resultBox.classList.remove("hidden");
    errorBox.classList.add("hidden");
    table.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.textContent = "Extracting...";
    try {
      const res = await fetch("/playground/extraction/run", { method: "POST", body: fd });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Extraction failed.");
      const tbody = table.querySelector("tbody");
      tbody.innerHTML = "";
      for (const [key, value] of Object.entries(data.result)) {
        const tr = document.createElement("tr");
        const th = document.createElement("td");
        const td = document.createElement("td");
        th.textContent = key;
        td.textContent = typeof value === "object" ? JSON.stringify(value) : String(value);
        if (data.missing.includes(key)) td.className = "status-error";
        tr.append(th, td);
        tbody.appendChild(tr);
      }
      table.classList.remove("hidden");
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.classList.remove("hidden");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Run Extraction";
    }
  });
})();
