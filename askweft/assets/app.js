"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const fieldLabels = {reference: "Payment reference", date: "Settlement date", party: "Counterparty key", duplicate: "Duplicate bank records"};
  const ui = {mode: "connecting", token: null, established: false, online: false, busy: false, switching: false, selectionUnavailable: false, view: null, selectedId: null, generation: 0, timer: null, signatures: new Map(), questionId: null, answerBinding: null, answerDirty: false, fileReadSerial: 0, fileReading: false, rawFileText: null, stages: []};
  class APIError extends Error {
    constructor(message, code = "request_failed", status = 0) { super(message); this.name = "APIError"; this.code = code; this.status = status; }
  }
  const text = (id, value) => { $(id).textContent = String(value ?? "—"); };
  const element = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  };
  const human = (value) => String(value ?? "Unknown").replaceAll("_", " ");
  const title = (value) => { const result = human(value); return result.charAt(0).toUpperCase() + result.slice(1); };
  const fieldName = (name) => fieldLabels[name] || title(name);
  const valueText = (value) => value === null || value === undefined ? "Unavailable" : typeof value === "boolean" ? (value ? "Yes" : "No") : String(value);
  const fraction = (value) => value && Number.isInteger(value.numerator) && Number.isInteger(value.denominator) && value.denominator > 0 ? value.denominator === 1 ? String(value.numerator) : `${value.numerator}/${value.denominator}` : "Not supplied";
  const utc = (value) => value ? String(value).replace("T", " ").replace(/(?:\.\d+)?(?:Z|\+00:00)$/, " UTC") : "";
  const session = () => ui.view?.session;
  const canWrite = () => ui.mode === "live" && ui.online && !ui.busy && !ui.switching && !ui.selectionUnavailable;
  const statePath = (id) => `api/state${id ? `?session=${encodeURIComponent(id)}` : ""}`;
  const announce = (message) => text("page-status", message);
  function showError(message, target) {
    if (target) text(target, message);
    if (!target || !$(target).getClientRects().length) { text("action-error-message", message); $("action-error").hidden = false; }
  }
  const clearError = () => { $("action-error").hidden = true; };

  async function request(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const headers = {Accept: "application/json"};
      const options = {headers, credentials: "same-origin", cache: "no-store", signal: controller.signal};
      if (body !== undefined) {
        options.method = "POST";
        headers["Content-Type"] = "application/json";
        headers["X-Askweft-Token"] = ui.token;
        options.body = JSON.stringify(body);
      }
      const response = await fetch(path, options);
      if (!(response.headers.get("content-type") || "").includes("application/json")) {
        if (path === "api/session" && (response.ok || [404, 405, 501].includes(response.status))) throw new APIError("No local session at this address.", "static_host", response.status);
        throw new APIError(`The server returned a non-JSON response (${response.status}).`, "invalid_response", response.status);
      }
      let result;
      try { result = await response.json(); } catch { throw new APIError("The server returned invalid JSON.", "invalid_response", response.status); }
      if (!response.ok) {
        if (path === "api/session" && [404, 405, 501].includes(response.status)) throw new APIError("No local session at this address.", "static_host", response.status);
        throw new APIError(result?.error?.message || `Request failed (${response.status}).`, result?.error?.code, response.status);
      }
      return result;
    } catch (error) {
      if (error instanceof APIError) throw error;
      throw new APIError(error.name === "AbortError" ? "The local server did not respond in time." : "The local server could not be reached.", "connection_failed");
    } finally { clearTimeout(timeout); }
  }

  function checkView(view) {
    if (!view || !Array.isArray(view.sessions) || !(view.session === null || typeof view.session === "object")) throw new APIError("Unsupported workspace response.", "invalid_view");
    if (view.session && (!view.session.id || !Array.isArray(view.session.alternatives) || !Array.isArray(view.session.options) || !Array.isArray(view.session.journal))) throw new APIError("The session response is incomplete.", "invalid_view");
    return view;
  }
  async function establish() {
    const result = await request("api/session");
    if (typeof result?.token !== "string" || !result.token) throw new APIError("Invalid local session response.", "invalid_session");
    ui.token = result.token;
    ui.established = true;
    ui.mode = "live";
  }
  function connection(online, message = "") {
    ui.online = online;
    text("mode-label", ui.mode === "recorded" ? "Recorded synthetic example" : online ? ui.view?.mode === "synthetic-local" ? "Synthetic local workspace" : "Local workspace" : ui.established ? "Workspace offline" : "No local connection");
    $("connection-notice").hidden = !message;
    text("connection-message", message);
    $("retry-connection").hidden = ui.mode === "recorded";
    $("open-latest").hidden = !ui.selectionUnavailable || ui.mode === "recorded";
    controls();
  }
  function schedule() { clearTimeout(ui.timer); if (ui.mode !== "recorded") ui.timer = setTimeout(poll, 2000); }

  async function readSelected(generation = ui.generation) {
    const selected = ui.selectedId;
    const view = checkView(await request(statePath(selected)));
    if (generation !== ui.generation || selected !== ui.selectedId) return false;
    applyView(view);
    ui.selectionUnavailable = false;
    ui.switching = false;
    connection(true);
    return true;
  }
  async function connect() {
    clearTimeout(ui.timer);
    const generation = ++ui.generation;
    ui.switching = true;
    controls();
    try {
      await establish();
      await readSelected(generation);
      announce("Local workspace refreshed. Review current state before making a request.");
    } catch (error) {
      if (generation !== ui.generation) return;
      if (!ui.established && error.code === "static_host") {
        try { await loadRecording(); return; }
        catch (recordingError) { connection(false, `No local workspace or saved recording is available. ${recordingError.message} Run “askweft --db example.sqlite demo” and open its printed URL.`); }
      } else if (error.code === "not_found" && ui.view) {
        ui.selectionUnavailable = true;
        connection(true, "The selected session is unavailable. Choose another session or open the latest session.");
      } else connection(false, `${error.message} ${ui.view ? "The last received view remains visible. Writes are disabled until a fresh connection returns." : "Run “askweft --db example.sqlite demo” and open its printed numeric loopback URL."}`);
    } finally {
      if (generation === ui.generation) { ui.switching = false; controls(); }
      schedule();
    }
  }
  async function poll() {
    if (ui.mode === "recorded") return;
    if (ui.busy || ui.switching || ui.selectionUnavailable || document.hidden) { schedule(); return; }
    if (!ui.established || !ui.online) { await connect(); return; }
    const generation = ui.generation;
    try { await readSelected(generation); }
    catch (error) {
      if (generation !== ui.generation) return;
      if (error.code === "not_found") {
        ui.selectionUnavailable = true;
        connection(true, "The selected session is unavailable. Choose another session or open the latest session.");
      } else connection(false, `${error.message} The last received view remains visible. Writes are disabled until a fresh connection returns.`);
    }
    schedule();
  }

  async function mutate(path, body, {feedback, newSession = false, success = "Workspace updated."} = {}) {
    if (!canWrite()) return false;
    ui.busy = true;
    ++ui.generation;
    clearError();
    if (feedback) text(feedback, "");
    controls();
    try {
      const view = checkView(await request(path, body));
      if (!newSession && view.session?.id !== ui.selectedId) throw new APIError("The response belongs to another session. Refresh before retrying.", "invalid_view");
      if (newSession) { ui.selectedId = view.session?.id || null; ui.questionId = null; ui.answerBinding = null; ui.answerDirty = false; }
      applyView(view);
      connection(true);
      announce(success);
      return true;
    } catch (error) {
      let message = error.message;
      if (error.code === "token_refused") {
        connection(false, "The local session changed. Refreshing the session and current state; the action will not be replayed.");
        ui.token = null;
        try {
          await establish();
          await readSelected(ui.generation);
          message = `${error.message} Session and state refreshed. Review the current view, then try the action again.`;
        } catch (refreshError) { connection(false, `${refreshError.message} Writes remain disabled until a fresh connection returns.`); }
      } else if (error.code === "stale_revision" || error.code === "answer_conflict") {
        try {
          await readSelected(ui.generation);
          message = `${error.message} Current state and journal refreshed. Review them before trying again.`;
        } catch (refreshError) { connection(false, `${refreshError.message} The last received view remains visible.`); }
      } else if (!error.status || error.status >= 500 || error.code === "invalid_view") connection(false, `${error.message} The result may be unconfirmed. A fresh view is required before another write.`);
      else if (error.code === "origin_refused" || error.code === "host_refused") message = `${error.message} Open the numeric loopback URL printed by the local server.`;
      showError(message, feedback);
      return false;
    } finally { ui.busy = false; controls(); schedule(); }
  }

  async function loadRecording() {
    const recording = await request("recorded.json");
    if (recording?.format !== 1 || !Array.isArray(recording.stages) || !recording.stages.length) throw new APIError("No supported recording is available.", "invalid_recording");
    const ids = new Set();
    for (const stage of recording.stages) {
      if (typeof stage.id !== "string" || ids.has(stage.id) || typeof stage.label !== "string") throw new APIError("Invalid saved stage.", "invalid_recording");
      checkView(stage.state);
      ids.add(stage.id);
    }
    ui.mode = "recorded";
    ui.stages = recording.stages;
    $("saved-stage").replaceChildren(...ui.stages.map((stage) => { const option = element("option", "", stage.label); option.value = stage.id; return option; }));
    $("recorded-panel").hidden = false;
    chooseStage(ui.stages[0].id);
    ui.switching = false;
    connection(false);
  }
  function chooseStage(id) {
    const stage = ui.stages.find((entry) => entry.id === id);
    if (!stage) return;
    ui.selectedId = stage.state.session?.id || null;
    ui.questionId = null;
    ui.answerBinding = null;
    ui.answerDirty = false;
    applyView(stage.state);
    $("saved-stage").value = stage.id;
    announce(`Saved synthetic stage: ${stage.label}. Read-only.`);
  }

  function renderChanged(id, data, render) {
    const signature = JSON.stringify(data);
    if (ui.signatures.get(id) === signature) return;
    $(id).replaceChildren(...render());
    ui.signatures.set(id, signature);
  }
  function fact(label, value, className) {
    const row = element("div", className);
    row.append(element("dt", "", label), element("dd", "", value));
    return row;
  }
  function details(data, label = "Raw details") {
    const result = element("details", "item-raw");
    result.append(element("summary", "", label), element("pre", "", JSON.stringify(data, null, 2)));
    return result;
  }
  function pill(label, className) { return element("span", `status-pill ${className || ""}`, label); }
  function applyView(view) {
    ui.view = view;
    const current = view.session;
    if (current) ui.selectedId = current.id;
    else ui.selectedId = null;
    renderChanged("session-select", view.sessions, () => view.sessions.length ? view.sessions.map((item) => { const option = element("option", "", `${item.title || item.id} · ${title(item.status)}`); option.value = item.id; return option; }) : [element("option", "", "No sessions")]);
    $("session-select").value = ui.selectedId || "";
    $("case-workspace").hidden = !current;
    $("empty-panel").hidden = Boolean(current);
    $("open-import").hidden = !current;
    text("case-title", current?.title || current?.case?.title || "No case selected");
    if (!current) { ui.answerBinding = null; controls(); return; }
    text("session-status", title(current.status));
    $("session-status").className = `status-pill ${current.status}`;
    text("session-reason", current.reason ? title(current.reason) : "");
    $("result-scope").hidden = current.status !== "resolved_within_model";
    text("usage-questions", `Questions ${current.usage?.questions ?? 0} of ${current.config.question_budget}`);
    text("usage-fields", `Unique fields ${current.usage?.fields ?? 0} of ${current.config.field_budget}`);
    text("usage-cost", `Cost ${current.usage?.cost ?? 0} units`);
    renderSource(current);
    renderAlternatives(current);
    renderRequest(current);
    renderJournal(current);
    const raw = JSON.stringify(view, null, 2);
    if ($("raw-view").textContent !== raw) text("raw-view", raw);
    controls();
  }

  function sourceFacts(record, invoice = false) {
    return [fact("Amount", `${record.amount_minor} minor units · ${record.currency}`), fact(invoice ? "Issued on" : "Booked on", valueText(invoice ? record.issued_on : record.booked_on)), fact("Reference", valueText(record.reference)), fact("Counterparty key", valueText(record.party_key))];
  }
  function renderSource(current) {
    const invoice = current.case.invoice;
    text("invoice-id", invoice.id);
    renderChanged("invoice-facts", invoice, () => sourceFacts(invoice, true));
    renderChanged("bank-records", current.case.bank_events, () => current.case.bank_events.map((record) => {
      const item = element("li", "bank-record"), heading = element("div", "item-top"), facts = element("dl", "fact-grid");
      heading.append(element("strong", "", record.id));
      facts.append(...sourceFacts(record));
      item.append(heading, facts);
      return item;
    }));
    const known = Object.entries(current.known || {});
    renderChanged("known-facts", known, () => known.map(([name, value]) => fact(fieldName(name), valueText(value))));
    $("no-known-facts").hidden = Boolean(known.length);
    const unavailable = current.unavailable_fields || [];
    $("unavailable-fields").hidden = !unavailable.length;
    text("unavailable-fields", `Unavailable this session: ${unavailable.map(fieldName).join(", ")}.`);
    renderChanged("session-details", [current.id, current.revision, current.input_sha256, current.created_at, current.config], () => [fact("Session", current.id), fact("Revision", current.revision), fact("Original input SHA256", current.input_sha256), fact("Created", utc(current.created_at)), fact("Configuration", `λ=${current.config.lambda}; questions=${current.config.question_budget}; unique fields=${current.config.field_budget}`)]);
  }
  function renderAlternatives(current) {
    const filter = $("alternative-filter").value;
    const alternatives = current.alternatives.filter((item) => filter === "all" || (filter === "remaining" ? item.survives : !item.survives));
    renderChanged("alternative-list", [current.id, filter, alternatives], () => alternatives.length ? alternatives.map((item) => {
      const row = element("li", "alternative"), top = element("div", "item-top"), heading = element("div", "item-title");
      heading.append(element("h3", "", item.id));
      const status = item.survives ? "remaining" : item.feasible ? "ruled-out" : "infeasible";
      top.append(heading, pill(status === "ruled-out" ? "Ruled out" : title(status), status));
      const ids = element("div", "bank-ids");
      for (const id of item.bank_ids || []) ids.append(element("span", "bank-id", id));
      const predictions = element("dl", "prediction-list");
      for (const name of ["reference", "date", "party", "duplicate"]) predictions.append(fact(`Predicted ${name === "party" ? "party" : name}`, valueText(item.predictions?.[name])));
      row.append(top, ids, predictions);
      if (item.rejection_reasons?.length) row.append(element("p", "rejection-reasons", item.rejection_reasons.map((reason) => typeof reason === "string" ? title(reason) : JSON.stringify(reason)).join(" · ")));
      row.append(details(item));
      return row;
    }) : [element("li", "empty-state", "No alternatives in this view.")]);
  }

  function partitionRows(partitions) {
    return (partitions || []).map((partition) => {
      const item = element("li", "partition");
      const values = Object.entries(partition.values || {}).map(([field, value]) => `${fieldName(field)}: ${valueText(value)}`).join(" · ");
      item.append(element("p", "partition-values", values), element("p", "partition-alternatives", (partition.alternatives || []).join(" · ")));
      return item;
    });
  }
  function renderRequest(current) {
    text("request-revision", `Revision ${current.revision}`);
    const pending = current.pending;
    $("pending-answer").hidden = !pending;
    $("question-preview").hidden = Boolean(pending) || current.status !== "active" || !current.options.length;
    $("terminal-state").hidden = Boolean(pending) || (current.status === "active" && Boolean(current.options.length));
    text("request-heading", pending ? "Requested fields" : "Next request");
    if (pending) { renderAnswer(current); return; }
    ui.answerBinding = null;
    ui.answerDirty = false;
    if (current.status !== "active" || !current.options.length) {
      text("terminal-reason", title(current.reason || current.status));
      return;
    }
    if (!current.options.some((option) => option.id === ui.questionId)) ui.questionId = current.suggestion?.id || current.options[0].id;
    renderChanged("question-select", [current.id, current.options.map((option) => [option.id, option.title, option.cost]), current.suggestion?.id], () => current.options.map((option) => {
      const node = element("option", "", `${option.title}${option.id === current.suggestion?.id ? " · Suggested" : ""}`);
      node.value = option.id;
      return node;
    }));
    $("question-select").value = ui.questionId;
    renderQuestion(current);
  }
  function renderQuestion(current) {
    const question = current.options.find((item) => item.id === ui.questionId);
    if (!question) return;
    text("question-title", question.title);
    text("question-fields", question.fields.map(fieldName).join(" · ")); $("question-fields").hidden = question.fields.length === 1 && fieldName(question.fields[0]) === question.title;
    text("question-cost", `${question.cost} units`);
    text("question-remaining", fraction(question.expected_remaining));
    renderChanged("question-partitions", question.partitions, () => partitionRows(question.partitions));
    text("question-explanation", `Expected removed: ${fraction(question.expected_eliminated)}. Score = expected removed ÷ declared cost = ${fraction(question.score)}. The server ranks these exact fractions; the answer groups above show its partition.`);
    text("cost-explanation", `Cost = 1 + λ × requested field weights, with λ=${current.config.lambda}. Reference and date weigh 1 each, party 2, duplicate 3. This request costs ${question.cost} declared effort units.`);
  }

  function renderAnswer(current) {
    const pending = current.pending;
    text("pending-title", pending.title);
    text("pending-cost", `Already requested · ${pending.cost} declared effort units`);
    renderChanged("pending-partitions", pending.partitions, () => partitionRows(pending.partitions));
    const key = JSON.stringify([current.id, current.revision, pending.id, pending.fields]);
    if (ui.answerBinding?.key === key) return;
    const changedDraft = ui.answerDirty;
    ui.answerBinding = {key, sessionId: current.id, revision: current.revision, requestId: pending.id, fields: [...pending.fields]};
    ui.answerDirty = false;
    $("answer-fields").replaceChildren(...pending.fields.map((field) => {
      const wrapper = element("div", "answer-field"), label = element("label", "", fieldName(field));
      const id = `answer-${field}`;
      label.htmlFor = id;
      wrapper.append(label);
      if (field === "duplicate") {
        const select = element("select"); select.id = id; select.required = true; select.dataset.write = "";
        for (const [value, caption] of [["", "Choose an answer"], ["true", "Yes — duplicate records"], ["false", "No — one record"], ["unknown", "Unknown"]]) { const option = element("option", "", caption); option.value = value; select.append(option); }
        wrapper.append(select);
      } else {
        const input = element("input"); input.id = id; input.type = field === "date" ? "date" : "text"; input.required = true; input.dataset.write = ""; input.autocomplete = "off";
        if (field !== "date") input.maxLength = 128;
        const mode = element("label", "answer-mode"), checkbox = element("input"); checkbox.type = "checkbox"; checkbox.id = `unknown-${field}`; checkbox.dataset.write = "";
        mode.append(checkbox, element("span", "", "Unknown"));
        checkbox.addEventListener("change", controls);
        wrapper.append(input, mode);
      }
      return wrapper;
    }));
    text("answer-feedback", changedDraft ? "The session revision or pending request changed. Review the current fields before answering." : "");
  }

  function renderJournal(current) {
    renderChanged("journal-list", [current.id, current.journal], () => current.journal.length ? current.journal.map((entry) => {
      const item = element("li", "journal-item"), top = element("div", "item-top"), heading = element("h3", "", title(entry.kind));
      top.append(heading, element("time", "journal-time", utc(entry.at)));
      item.append(top);
      if (entry.values) item.append(element("p", "journal-description", Object.entries(entry.values).map(([field, value]) => `${fieldName(field)}: ${value === null ? "Unknown" : valueText(value)}`).join(" · ")));
      else if (entry.fields?.length) item.append(element("p", "journal-description", entry.fields.map(fieldName).join(" · ")));
      const meta = element("div", "journal-meta");
      if (entry.remaining !== undefined) meta.append(element("span", "", `Remaining: ${Array.isArray(entry.remaining) ? entry.remaining.join(", ") || "None" : entry.remaining}`));
      if (entry.cost !== undefined) meta.append(element("span", "", `Cost: ${entry.cost} units`));
      if (entry.receipt_id) meta.append(element("span", "", `Receipt: ${entry.receipt_id}`));
      item.append(meta, details(entry, "Entry details"));
      return item;
    }) : [element("li", "empty-state", "No requests or answers recorded.")]);
  }

  function controls() {
    const disabled = !canWrite();
    document.querySelectorAll("[data-write]").forEach((item) => { item.disabled = disabled; });
    $("open-restart").disabled = disabled || !session();
    $("request-question").disabled = disabled || session()?.status !== "active" || !session()?.options.some((item) => item.id === ui.questionId) || Boolean(session()?.pending);
    $("answer-form").querySelector("button").disabled = disabled || !session()?.pending;
    $("import-form").querySelector('button[type="submit"]').disabled = disabled || ui.fileReading;
    $("session-select").disabled = ui.mode === "recorded" || ui.busy || ui.switching || !ui.view?.sessions.length;
    $("export-state").disabled = !ui.view || !session();
    $("workspace").setAttribute("aria-busy", String(ui.switching));
    for (const field of ui.answerBinding?.fields || []) if (field !== "duplicate") {
      const input = $(`answer-${field}`), unknown = $(`unknown-${field}`);
      if (input && unknown) { input.disabled = disabled || unknown.checked; input.required = !unknown.checked; }
    }
  }

  const config = (prefix) => ({lambda: Number($(`${prefix}-lambda`).value), question_budget: Number($(`${prefix}-questions`).value), field_budget: Number($(`${prefix}-fields`).value)});
  function openImport() { if (!canWrite()) return; text("import-feedback", ""); $("import-dialog").showModal(); $("source-json").focus(); }
  $("open-import").addEventListener("click", openImport);
  $("empty-import").addEventListener("click", openImport);
  ["close-import", "cancel-import"].forEach((id) => $(id).addEventListener("click", () => $("import-dialog").close()));
  ["close-restart", "cancel-restart"].forEach((id) => $(id).addEventListener("click", () => $("restart-dialog").close()));
  $("open-restart").addEventListener("click", () => {
    if (!canWrite() || !session()) return;
    const current = session().config;
    $("restart-lambda").value = current.lambda; $("restart-questions").value = current.question_budget; $("restart-fields").value = current.field_budget;
    text("restart-feedback", ""); $("restart-dialog").showModal();
  });
  $("source-json").addEventListener("input", () => { ++ui.fileReadSerial; ui.fileReading = false; ui.rawFileText = null; text("import-feedback", ""); controls(); });
  $("import-file").addEventListener("change", async () => {
    const file = $("import-file").files[0]; if (!file) return;
    const serial = ++ui.fileReadSerial;
    ui.fileReading = true;
    controls();
    try {
      if (file.size > 262144) throw new Error("The file exceeds the 256 KiB input limit.");
      const source = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(await file.arrayBuffer());
      if (serial !== ui.fileReadSerial) return;
      $("source-json").value = source;
      ui.rawFileText = source;
      text("import-feedback", "");
    } catch (error) { if (serial === ui.fileReadSerial) text("import-feedback", error instanceof TypeError ? "The file is not valid UTF-8. Choose a UTF-8 JSON file." : error.message); }
    finally { if (serial === ui.fileReadSerial) { ui.fileReading = false; controls(); } }
  });
  $("import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    // A textarea normalizes CRLF; retain decoded file text until the operator edits it.
    const source = ui.rawFileText ?? $("source-json").value;
    if (new TextEncoder().encode(source).length > 262144) { text("import-feedback", "Source JSON exceeds the 256 KiB input limit."); return; }
    if (await mutate("api/import", {source_json: source, config: config("import")}, {feedback: "import-feedback", newSession: true, success: "Case imported into a new session."})) { $("import-dialog").close(); $("workspace").focus(); }
  });
  $("restart-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!session()) return;
    if (await mutate("api/restart", {session_id: ui.selectedId, config: config("restart")}, {feedback: "restart-feedback", newSession: true, success: "New session created from preserved original input."})) $("restart-dialog").close();
  });
  $("request-question").addEventListener("click", () => {
    const current = session();
    if (!current || !ui.questionId) return;
    mutate("api/request", {session_id: current.id, expected_revision: current.revision, question_id: ui.questionId}, {success: "Fields requested. Provide a typed answer or explicit Unknown for each field."});
  });
  $("answer-form").addEventListener("input", () => { ui.answerDirty = true; });
  $("answer-form").addEventListener("change", () => { ui.answerDirty = true; });
  $("answer-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const bound = ui.answerBinding; if (!bound) return;
    const values = {};
    for (const field of bound.fields) {
      const input = $(`answer-${field}`);
      if (field === "duplicate") {
        if (!input.value) { input.focus(); text("answer-feedback", "Choose Yes, No or Unknown for duplicate bank records."); return; }
        values[field] = input.value === "unknown" ? null : input.value === "true";
      } else if ($(`unknown-${field}`).checked) values[field] = null;
      else {
        if (!input.value.trim()) { input.focus(); text("answer-feedback", `Enter ${fieldName(field).toLowerCase()} or explicitly select Unknown.`); return; }
        values[field] = input.value;
      }
    }
    await mutate("api/answer", {session_id: bound.sessionId, expected_revision: bound.revision, request_id: bound.requestId, values}, {feedback: "answer-feedback", success: "Answer recorded. The alternatives and journal reflect the server result."});
  });
  $("session-select").addEventListener("change", async () => {
    if (ui.mode === "recorded") return;
    ui.selectedId = $("session-select").value;
    ui.selectionUnavailable = false;
    ui.questionId = null;
    const generation = ++ui.generation;
    ui.switching = true; controls();
    try { await readSelected(generation); }
    catch (error) { if (generation === ui.generation) { ui.switching = false; if (error.code === "not_found") { ui.selectionUnavailable = true; connection(true, "The selected session is unavailable. Choose another session or open the latest session."); } else connection(false, `${error.message} Choose another session or retry the connection.`); } }
    schedule();
  });
  $("question-select").addEventListener("change", () => { ui.questionId = $("question-select").value; if (session()) renderQuestion(session()); controls(); });
  $("alternative-filter").addEventListener("change", () => session() && renderAlternatives(session()));
  $("saved-stage").addEventListener("change", () => chooseStage($("saved-stage").value));
  $("export-state").addEventListener("click", () => {
    if (!ui.view) return;
    const blob = new Blob([JSON.stringify(ui.view, null, 2) + "\n"], {type: "application/json"});
    const url = URL.createObjectURL(blob), link = element("a"); link.href = url; link.download = `askweft-${String(ui.selectedId || "view").replace(/[^A-Za-z0-9_.-]/g, "_")}.json`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("dismiss-error").addEventListener("click", clearError);
  $("retry-connection").addEventListener("click", connect);
  $("open-latest").addEventListener("click", () => { ui.selectedId = null; ui.selectionUnavailable = false; connect(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !ui.busy && ui.mode !== "recorded") { clearTimeout(ui.timer); poll(); } });
  window.addEventListener("pagehide", () => clearTimeout(ui.timer));
  controls();
  connect();
})();
