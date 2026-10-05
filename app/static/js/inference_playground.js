(function () {
  const log = document.getElementById("chat-log");
  const form = document.getElementById("chat-form");
  const text = document.getElementById("chat-text");
  const send = document.getElementById("chat-send");
  const model = document.getElementById("chat-model");
  const modelUse = document.getElementById("model-use");
  let messages = [];

  function showUse() {
    const opt = model.options[model.selectedIndex];
    modelUse.textContent = opt.dataset.use || "";
  }

  function addBubble(role, content, extraClass) {
    const empty = log.querySelector(".chat-empty");
    if (empty) empty.remove();
    const el = document.createElement("div");
    el.className = `chat-msg ${role} ${extraClass || ""}`;
    el.textContent = content;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function reset() {
    messages = [];
    log.innerHTML = '<div class="chat-empty">Send a message to start the conversation.</div>';
  }

  // Switching models starts a fresh conversation so models are compared like-for-like.
  model.addEventListener("change", () => { showUse(); reset(); });
  document.getElementById("chat-clear").addEventListener("click", reset);
  showUse();

  text.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const content = text.value.trim();
    if (!content) return;
    text.value = "";
    messages.push({ role: "user", content });
    addBubble("user", content);
    const pending = addBubble("assistant", "Thinking...", "pending");
    send.disabled = true;
    model.disabled = true;
    try {
      const res = await fetch("/playground/inference/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: model.value, messages }),
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Request failed.");
      pending.classList.remove("pending");
      pending.textContent = data.reply || "(empty response)";
      messages.push({ role: "assistant", content: data.reply || "" });
    } catch (err) {
      pending.classList.remove("pending");
      pending.classList.add("error");
      pending.textContent = err.message;
      messages.pop();
    } finally {
      send.disabled = false;
      model.disabled = false;
      log.scrollTop = log.scrollHeight;
      text.focus();
    }
  });
})();
