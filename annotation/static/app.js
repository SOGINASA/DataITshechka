"use strict";
const $ = id => document.getElementById(id);
const state = { boot: null, record: null, annotation: null, criterion: 0, annotator: "", dirty: false, busy: false, loadNumber: 0,
  review: { active: false, queue: null, task: null, skipped: new Set() } };
const roleNames = { operator: "Оператор", client: "Клиент", bot: "Бот", system: "Система" };

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notice(message = "", error = false) {
  $("notice").textContent = message;
  $("notice").className = error ? "error" : "";
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Ошибка локального сервера.");
  return data;
}
function allowLeave() { return !state.dirty || window.confirm("Есть несохранённые изменения. Перейти без сохранения?"); }
function labelForCurrent() { return state.annotation.labels[state.criterion]; }
function saveState() {
  $("save-state").textContent = !state.annotation ? "" :
    `Автор: ${state.annotator || "не выбран"} · ${state.dirty ? "есть несохранённые изменения" : state.annotation.revision ? `сохранено, версия ${state.annotation.revision}` : "ещё не сохранено"} · ${state.annotation.status === "complete" ? "завершено" : "черновик"}`;
  const summary = state.annotation?.score_summary;
  $("score-summary").textContent = state.dirty ? "Сохраните изменения для пересчёта балла." : !summary ? "Баллы будут рассчитаны после сохранения." : !summary.configured ? "В этом чек-листе веса не заданы." :
    `${summary.total === null ? "Итог пока не рассчитан" : `Итог: ${summary.total.toFixed(2)} / 100`} · грубые ошибки: ${summary.critical_errors === true ? "ДА" : summary.critical_errors === false ? "нет" : "не определено"}`;
  if (state.annotation?.origin === "ai_example") $("save-state").textContent += " · пример ИИ, не проверен человеком";
  if (state.annotation?.human_verification) $("save-state").textContent += ` · подтверждено вами: ${state.annotation.labels.filter(x => x.human_checked).length}/${state.annotation.labels.length}`;
  else if (state.annotation?.origin === "ai_preannotation") $("save-state").textContent += " · предварительная разметка ИИ, требует проверки";
  const context = state.annotation?.assessment_context;
  $("assessment-context").textContent = context ? `${context.basis === "transcript_only" ? "Оценён только транскрипт. Аудио не прослушано; темп, дикция и акустическая разборчивость не оценивались." : "Вы отметили, что аудио прослушано."} Ограничения исходной разметки: ${context.limitations.join(" ")}` : "";
  if (state.record && state.boot.checklist.applicable_channels && !state.boot.checklist.applicable_channels.includes(state.record.channel)) {
    $("score-summary").textContent = "Этот чек-лист не предназначен для данного канала. Применимость нужно уточнить; разметка не станет эталоном.";
  }
}
function touch() {
  state.dirty = true;
  state.annotation.reviewed = false;
  state.annotation.reviewer = "";
  labelForCurrent().human_checked = false;
  $("reviewed").checked = false;
  $("reviewer").value = "";
  saveState();
  renderTabs();
}
function emptyAnnotation(record) {
  return {
    conversation_id: record.conversation_id, content_hash: record.content_hash,
    checklist_hash: state.boot.checklist_hash, annotator: state.annotator,
    revision: 0, status: "draft", reviewed: false, reviewer: "",
    labels: state.boot.checklist.criteria.map(c => ({ criterion_id: c.id, verdict: "", score: null,
      reason: "", confidence: "medium", evidence_turn_ids: [], checked_span: null }))
  };
}
function filteredRecords() {
  const query = $("search").value.toLowerCase().trim();
  return state.boot.records.filter(r => (!$("language").value || r.language === $("language").value)
    && (!$("channel").value || r.channel === $("channel").value)
    && (!query || r.conversation_id.toLowerCase().includes(query))
    && (!state.review.active || (state.review.queue?.tasks || []).some(t => t.checklist_hash === state.boot.checklist_hash && t.conversation_id === r.conversation_id)));
}
function renderList() {
  const records = filteredRecords();
  $("record-count").textContent = `${records.length}/${state.boot.records.length}`;
  const fragment = document.createDocumentFragment();
  for (const r of records) {
    const button = el("button", undefined, "conversation" + (r.conversation_id === state.record?.conversation_id ? " active" : ""));
    button.append(el("span", r.conversation_id), el("small", `${r.language} · ${r.channel === "voice call" ? "звонок" : "чат"} · ${r.transcript.length} репл.`));
    const saved = state.boot.annotations.find(a => a.conversation_id === r.conversation_id && a.annotator === state.annotator);
    if (saved) button.append(el("small", saved.content_hash !== r.content_hash ? "Транскрипт изменён" : saved.reviewed ? "Подтверждено" : saved.origin === "ai_preannotation" ? (saved.score_summary?.pending_criteria?.length ? `ИИ · уточнить: ${saved.score_summary.pending_criteria.length}` : "ИИ · предварительно") : saved.status === "complete" ? "Завершено" : "Черновик"));
    button.disabled = state.busy;
    button.addEventListener("click", () => {
      if (r === state.record || !allowLeave()) return;
      const task = state.review.active && state.review.queue.tasks.find(t => t.checklist_hash === state.boot.checklist_hash && t.conversation_id === r.conversation_id);
      (task ? openReviewTask(task) : loadRecord(r)).catch(showError);
    });
    fragment.append(button);
  }
  if (!records.length) fragment.append(el("p", "Нет диалогов по фильтру.", "empty"));
  $("conversation-list").replaceChildren(fragment);
}
function renderTabs() {
  if (!state.annotation) return;
  const fragment = document.createDocumentFragment();
  let done = 0;
  state.boot.checklist.criteria.forEach((c, i) => {
    const label = state.annotation.labels[i];
    if (label.verdict) done++;
    const className = "criterion-tab" + (i === state.criterion ? " active" : "")
      + (label.verdict === "uncertain" ? " uncertain" : label.verdict ? " done" : "");
    const button = el("button", `${label.human_checked ? "✓ " : ""}${i + 1}. ${c.name}`, className);
    button.setAttribute("aria-pressed", String(i === state.criterion));
    button.disabled = state.busy;
    button.addEventListener("click", () => { state.criterion = i; renderTabs(); renderForm(); renderTranscript(); });
    fragment.append(button);
  });
  $("criteria").replaceChildren(fragment);
  $("progress").textContent = state.annotation.human_verification ? `${state.annotation.labels.filter(x => x.human_checked).length}/${state.annotation.labels.length} подтверждено` : `${done}/${state.annotation.labels.length} ответов`;
}
function renderTranscript() {
  const current = labelForCurrent();
  const fragment = document.createDocumentFragment();
  for (const turn of state.record.transcript) {
    const selected = current.evidence_turn_ids.includes(turn.turn_id);
    const row = el("label", undefined, `turn ${turn.speaker}${selected ? " selected" : ""}`);
    const checkbox = el("input"); checkbox.type = "checkbox"; checkbox.checked = selected; checkbox.disabled = state.busy;
    checkbox.setAttribute("aria-label", `Доказательство ${turn.turn_id}, ${roleNames[turn.speaker]}`);
    const content = el("div");
    content.append(el("div", `${turn.turn_id} · ${roleNames[turn.speaker]} · ${turn.timestamp}`, "turn-meta"), el("div", turn.text, "turn-text"));
    checkbox.addEventListener("change", () => {
      current.evidence_turn_ids = checkbox.checked ? [...current.evidence_turn_ids, turn.turn_id] : current.evidence_turn_ids.filter(t => t !== turn.turn_id);
      row.classList.toggle("selected", checkbox.checked);
      touch(); updateEvidenceSummary();
    });
    row.append(checkbox, content); fragment.append(row);
  }
  $("transcript").replaceChildren(fragment);
}
function option(value, text) { const node = el("option", text); node.value = value; return node; }
function field(title, control) { const label = el("label", title); label.append(control); return label; }
function updateEvidenceSummary() {
  const current = labelForCurrent();
  $("evidence-summary").textContent = `Реплики: ${current.evidence_turn_ids.join(", ") || "не выбраны"}`
    + (current.checked_span ? ` · Проверенный участок: ${current.checked_span.start_turn_id}–${current.checked_span.end_turn_id}` : "");
}
function renderForm() {
  const criterion = state.boot.checklist.criteria[state.criterion];
  const current = labelForCurrent();
  const container = document.createDocumentFragment();
  container.append(el("h3", criterion.name), el("p", criterion.description, "rule"));
  if (current.human_checked) container.append(el("p", "✓ Эта оценка уже подтверждена вами. Изменение ответа снимет отметку проверки.", "evidence-note"));
  const baseline = state.annotation.review_baseline?.labels.find(x => x.criterion_id === criterion.id);
  if (baseline) {
    const original = el("details", undefined, "source-card");
    original.append(el("summary", `Исходный ответ ИИ: ${baseline.verdict === "score" ? baseline.score : baseline.verdict === "uncertain" ? "не уверен" : baseline.verdict === "na" ? "N/A" : baseline.verdict === "pass" ? "Да" : "Нет"}`), el("p", baseline.reason));
    container.append(original);
  }
  if (criterion.section || criterion.weight !== undefined) container.append(el("p", `${criterion.section || ""} · ${criterion.is_critical ? "отдельный флаг без баллов" : criterion.weight === undefined ? "вес не задан" : `вес ${criterion.weight}`}`, "evidence-note"));
  for (const [title, text] of [[criterion.is_critical ? "Да — нарушение выявлено" : "Да / шкала", criterion.pass_rule], [criterion.is_critical ? "Нет — нарушение не выявлено" : "Нет / нижние ступени", criterion.fail_rule], ["N/A", criterion.na_allowed ? criterion.na_rule : "Не допускается для этого критерия"]]) {
    const p = el("p", undefined, "rule"); p.append(el("strong", title + ": "), document.createTextNode(text)); container.append(p);
  }
  const verdict = el("select"); verdict.id = "verdict";
  verdict.append(option("", "Выберите ответ"));
  if (criterion.type === "binary") verdict.append(option("pass", criterion.yes_label || "Выполнено"), option("fail", criterion.no_label || "Нарушено / пропущено"));
  else for (const score of criterion.allowed_scores) verdict.append(option(`score:${score}`, `Баллы: ${score}`));
  if (criterion.na_allowed) verdict.append(option("na", "N/A — неприменимо по правилу"));
  verdict.append(option("uncertain", "Не уверен — требуется разбор"));
  verdict.value = current.verdict === "score" ? `score:${current.score}` : current.verdict;
  verdict.addEventListener("change", () => {
    current.verdict = verdict.value.startsWith("score:") ? "score" : verdict.value;
    current.score = current.verdict === "score" ? Number(verdict.value.split(":")[1]) : null;
    touch();
  });
  const reason = el("textarea"); reason.id = "reason"; reason.value = current.reason;
  reason.placeholder = "Что сделал оператор? Почему это соответствует правилу? Для N/A объясните неприменимость, для отсутствия — что искали и где.";
  reason.addEventListener("input", () => { current.reason = reason.value; touch(); });
  const confidence = el("select"); confidence.id = "confidence";
  confidence.append(option("high", "Высокая — правило и доказательства однозначны"), option("medium", "Средняя — есть нюансы"), option("low", "Низкая — нужен повторный разбор"));
  confidence.value = current.confidence;
  confidence.addEventListener("change", () => { current.confidence = confidence.value; touch(); });
  container.append(field("Ответ", verdict), field("Объяснение решения", reason), field("Уверенность человека-разметчика", confidence));
  const evidence = el("p", "", "evidence-note"); evidence.id = "evidence-summary"; container.append(evidence);
  container.append(el("p", `Если действие отсутствует, выделите участок, где оно должно было быть. Границы включаются. Для ответа «Да» или положительного балла отметьте конкретную реплику галочкой слева. Допустимые роли: ${(criterion.positive_evidence_roles || ["operator"]).map(r => roleNames[r]).join(", ")}.`, "evidence-note"));
  const spans = el("div", undefined, "span-row");
  const start = el("select"), end = el("select"); start.id = "span-start"; end.id = "span-end";
  for (const select of [start, end]) {
    select.append(option("", "Не задано"));
    for (const t of state.record.transcript) select.append(option(t.turn_id, `${t.turn_id} · ${roleNames[t.speaker]} · ${t.timestamp}`));
  }
  start.value = current.checked_span?.start_turn_id || ""; end.value = current.checked_span?.end_turn_id || "";
  const updateSpan = () => {
    // Keep partial selection in the controls; saving with only one end is blocked below.
    current.checked_span = start.value || end.value ? { start_turn_id: start.value, end_turn_id: end.value } : null;
    touch(); updateEvidenceSummary();
  };
  start.addEventListener("change", updateSpan); end.addEventListener("change", updateSpan);
  spans.append(field("Начало участка", start), field("Конец участка", end)); container.append(spans);
  const whole = el("button", "Проверен весь диалог", "secondary");
  whole.addEventListener("click", () => {
    start.value = state.record.transcript[0].turn_id; end.value = state.record.transcript.at(-1).turn_id; updateSpan();
  });
  const clear = el("button", "Сбросить участок", "secondary");
  clear.addEventListener("click", () => { start.value = ""; end.value = ""; updateSpan(); });
  container.append(whole, document.createTextNode(" "), clear);
  $("criterion-form").replaceChildren(container); updateEvidenceSummary();
  if (state.busy) $("criterion-form").querySelectorAll("input,select,textarea,button").forEach(x => { x.disabled = true; });
}
function setBusy(busy) {
  state.busy = busy;
  document.querySelectorAll("button,input,select,textarea").forEach(node => { node.disabled = busy; });
  if (!busy) $("audio-notes").disabled = !$("audio-reviewed").checked;
}
async function loadRecord(record, supplied = undefined) {
  const number = ++state.loadNumber;
  setBusy(true); notice();
  try {
    const saved = supplied !== undefined ? supplied : state.annotator ? await api(`/api/annotation?${new URLSearchParams({ conversation_id: record.conversation_id, annotator: state.annotator })}`) : null;
    if (number !== state.loadNumber) return;
    state.record = record;
    const stale = saved && saved.content_hash !== record.content_hash;
    state.annotation = saved || emptyAnnotation(record);
    state.dirty = false;
    $("conversation-title").textContent = record.conversation_id;
    $("conversation-meta").textContent = `${record.language} · ${record.channel} · ${record.transcript.length} реплик`;
    const audio = $("audio"); audio.hidden = true; audio.removeAttribute("href");
    if (record.audio_url) {
      try { const url = new URL(record.audio_url); if (["https:", "http:"].includes(url.protocol)) { audio.href = `/audio/${encodeURIComponent(record.conversation_id)}`; audio.hidden = false; } } catch (_) { /* Invalid audio URL is not rendered. */ }
    }
    $("reviewer").value = state.annotation.reviewer; $("reviewed").checked = state.annotation.reviewed;
    if (stale) {
      // Preserve old revision for safe replacement, but never reuse labels against new content.
      state.annotation = { ...emptyAnnotation(record), revision: saved.revision };
      $("reviewer").value = ""; $("reviewed").checked = false;
      notice("Текст диалога изменился. Старые ответы сброшены на экране; предыдущая версия останется в истории после сохранения.", true);
    }
  } finally {
    if (number === state.loadNumber) {
      setBusy(false);
      if (state.record) { renderList(); renderTabs(); renderTranscript(); renderForm(); renderAudioReview(); saveState(); }
    }
  }
}
function showError(error) { notice(error.message || String(error), true); }
async function save(status) {
  if (!state.annotation || state.busy) return false;
  if (!state.annotator || $("annotator").value.trim() !== state.annotator) {
    notice("Укажите имя автора и нажмите «Открыть разметку автора» до начала работы.", true); return false;
  }
  setBusy(true); notice();
  try {
    const payload = { ...state.annotation, status, annotator: state.annotator,
      reviewed: $("reviewed").checked, reviewer: $("reviewer").value.trim() };
    const saved = await api("/api/annotation", payload);
    state.annotation = saved; state.dirty = false;
    state.boot.annotations = state.boot.annotations.filter(a => !(a.conversation_id === saved.conversation_id && a.annotator === state.annotator));
    state.boot.annotations.push(saved);
    let queueError = false;
    try { await updateReviewQueue(); } catch (_) { queueError = true; }
    notice(queueError ? "Оценка сохранена. Очередь пока не обновилась; повторите переход к следующей задаче." : status === "draft" ? "Черновик сохранён на диск." : "Диалог завершён и сохранён.", queueError);
    return true;
  } catch (error) { showError(error); return false; }
  finally { setBusy(false); renderList(); renderTabs(); renderReviewProgress(); saveState(); }
}
function installBootstrap(bootstrap) {
  state.boot = bootstrap;
  const profiles = state.boot.profiles || [];
  const selectedProfile = profiles.find(p => p.checklist_hash === state.boot.checklist_hash);
  $("profile").replaceChildren(option("", "Пользовательский чек-лист"), ...profiles.map(p => option(p.id, p.name)));
  $("profile").value = selectedProfile?.id || "";
  $("annotator-options").replaceChildren(...[...new Set(state.boot.annotations.map(a => a.annotator))].sort().map(name => option(name, name)));
  const checklist = state.boot.checklist;
  $("banner").className = "banner" + (checklist.status === "official" ? " official" : "");
  $("banner").textContent = `${checklist.status === "demo" ? "УЧЕБНЫЕ КРИТЕРИИ. Это не официальный чек-лист. " : checklist.adaptation_status ? "Голосовая адаптация команды по разрешению организаторов. " : "Чек-лист отмечен пользователем как официальный. "}${checklist.name} · ${checklist.version} · версия ${state.boot.checklist_hash.slice(0, 10)}`;
  const channels = state.boot.checklist.applicable_channels || ["agent chat", "voice call"];
  if (channels.length === 1) $("channel").value = channels[0];
}
async function refresh() {
  installBootstrap(await api("/api/bootstrap"));
  state.criterion = 0;
  const channels = state.boot.checklist.applicable_channels || ["agent chat", "voice call"];
  const candidates = state.boot.records.filter(r => channels.includes(r.channel));
  const record = candidates.find(r => r.conversation_id === state.record?.conversation_id) || candidates[0] || state.boot.records[0];
  await loadRecord(record);
}
function renderReviewProgress() {
  const counts = state.review.queue?.counts;
  $("review-progress").textContent = counts ? `Подтверждено: ${counts.confirmed}/${counts.total} · Неуверенных осталось: ${counts.uncertain_pending} · Других неподтверждённых: ${counts.other_pending}` : "";
  $("review-actions").hidden = !state.review.active;
  $("review-exit").hidden = !state.review.active;
  const task = state.review.task;
  $("review-task").textContent = state.review.active && task ? `${task.conversation_id} · ${task.criterion_name} · ${task.channel === "voice call" ? "звонок — запись открывается ссылкой над транскриптом" : "чат"}` : "";
}
async function updateReviewQueue() {
  state.review.queue = await api(`/api/review/queue?${new URLSearchParams({ phase: $("review-phase").value })}`);
  renderReviewProgress();
}
async function openReviewTask(task) {
  setBusy(true);
  try {
    const result = await api("/api/review/open", task);
    installBootstrap(result.bootstrap);
    state.annotator = result.annotation.annotator; $("annotator").value = state.annotator;
    state.review.task = task;
    state.criterion = state.boot.checklist.criteria.findIndex(c => c.id === task.criterion_id);
    if (state.criterion < 0) throw new Error("Критерий больше не существует.");
    $("language").value = ""; $("search").value = "";
    await loadRecord(state.boot.records.find(r => r.conversation_id === task.conversation_id), result.annotation);
    renderReviewProgress();
  } finally { setBusy(false); renderAudioReview(); }
}
async function nextReviewTask() {
  await updateReviewQueue();
  let task = state.review.queue.tasks.find(t => !state.review.skipped.has(t.key));
  if (!task && $("review-phase").value === "uncertain" && state.review.queue.counts.other_pending) {
    $("review-phase").value = "remaining"; await updateReviewQueue();
    task = state.review.queue.tasks.find(t => !state.review.skipped.has(t.key));
  }
  if (task) { await openReviewTask(task); return; }
  state.review.task = null; renderReviewProgress(); renderList();
  const count = state.review.queue.counts;
  notice(count.uncertain_pending + count.other_pending === 0 ? "Все оценки подтверждены. Разметка сохранена." : "В этой очереди остались только отложенные случаи. Нажмите «Продолжить разметку», чтобы вернуться к ним, или выберите другую очередь.");
}
async function startReview() {
  if (!allowLeave()) return;
  state.review.active = true; state.review.skipped.clear();
  try { await nextReviewTask(); } catch (error) { showError(error); }
}
function ensureVerification() {
  if (!state.annotation.human_verification) state.annotation.human_verification = {
    basis: "manual_ui", reviewer: $("reviewer").value.trim() || "Пользователь", independent_second_review_claimed: false
  };
}
async function confirmReview(all = false) {
  if (state.busy || !state.annotation) return;
  const current = labelForCurrent();
  if (!all && ["", "uncertain"].includes(current.verdict)) {
    notice("Выберите окончательный ответ и обновите объяснение. Если данных пока нет — нажмите «Отложить».", true); return;
  }
  const before = state.annotation.labels.map(x => x.human_checked);
  ensureVerification();
  for (const label of all ? state.annotation.labels : [current]) {
    if (!["", "uncertain"].includes(label.verdict)) { label.human_checked = true; label.review_basis = "manual_ui"; }
  }
  state.dirty = true;
  const complete = state.annotation.labels.every(x => x.human_checked && !["", "uncertain"].includes(x.verdict));
  if (await save(complete ? "complete" : "draft")) {
    try { await nextReviewTask(); } catch (error) { showError(error); }
  } else {
    state.annotation.labels.forEach((x, i) => { x.human_checked = before[i] || false; });
    renderTabs(); saveState();
  }
}
async function skipReview() {
  if (state.busy || !state.review.task) return;
  if (state.dirty && !await save("draft")) return;
  state.review.skipped.add(state.review.task.key);
  try { await nextReviewTask(); } catch (error) { showError(error); }
}
function renderAudioReview() {
  const voice = state.record?.channel === "voice call";
  $("audio-review").hidden = !voice;
  const context = state.annotation?.assessment_context;
  $("audio-reviewed").checked = context?.audio_reviewed || false;
  const notes = context?.acoustic_observations?.notes;
  $("audio-notes").value = notes && notes !== "not_assessed" ? notes : "";
  $("audio-notes").disabled = state.busy || !$("audio-reviewed").checked;
}
function changeAudioReview() {
  if (!state.annotation || state.record.channel !== "voice call") return;
  const listened = $("audio-reviewed").checked;
  const context = state.annotation.assessment_context || { limitations: [], excluded_turn_spans: [], acoustic_observations: {} };
  context.audio_reviewed = listened; context.basis = listened ? "transcript_and_audio" : "transcript_only";
  if (!listened) {
    for (const key of Object.keys(context.acoustic_observations)) context.acoustic_observations[key] = "not_assessed";
    $("audio-notes").value = "";
  }
  else context.acoustic_observations.notes = $("audio-notes").value.trim() || "not_assessed";
  state.annotation.assessment_context = context;
  const management = state.annotation.labels.find(x => x.criterion_id === "management");
  if (management) management.human_checked = false;
  touch(); $("audio-notes").disabled = !listened; saveState();
}
function download(name, value) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = el("a"); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("open-annotator").addEventListener("click", async () => {
  if (state.busy) return;
  const name = $("annotator").value.trim();
  if (!name) { notice("Введите имя автора разметки.", true); return; }
  if (!allowLeave()) return;
  state.review.active = false; state.review.task = null; renderReviewProgress();
  const old = state.annotator; state.annotator = name;
  try { await loadRecord(state.record); try { localStorage.setItem("cqa-annotator", name); } catch (_) {} }
  catch (error) { state.annotator = old; showError(error); }
});
for (const id of ["language", "channel", "search"]) $(id).addEventListener("input", () => { if (state.boot) renderList(); });
$("reviewer").addEventListener("input", () => { if (state.annotation) { state.dirty = true; saveState(); } });
$("reviewed").addEventListener("change", () => { if (state.annotation) { state.dirty = true; saveState(); } });
$("save-draft").addEventListener("click", () => save("draft"));
$("save-complete").addEventListener("click", () => save("complete"));
$("download-checklist").addEventListener("click", () => { if (state.boot) download("checklist.json", state.boot.checklist); });
$("review-start").addEventListener("click", startReview);
$("review-phase").addEventListener("change", () => { if (state.review.active) startReview(); else updateReviewQueue().catch(showError); });
$("review-exit").addEventListener("click", () => {
  if (!allowLeave()) return;
  state.review.active = false; state.review.task = null; renderReviewProgress(); renderList();
});
$("confirm-next").addEventListener("click", () => confirmReview(false));
$("confirm-dialogue").addEventListener("click", () => confirmReview(true));
$("review-skip").addEventListener("click", skipReview);
$("audio-reviewed").addEventListener("change", changeAudioReview);
$("audio-notes").addEventListener("input", changeAudioReview);
$("profile").addEventListener("change", async () => {
  const choice = $("profile").value;
  const prior = state.boot.profiles.find(p => p.checklist_hash === state.boot.checklist_hash)?.id || "";
  if (!choice || !allowLeave()) { $("profile").value = prior; return; }
  state.review.active = false; state.review.task = null; renderReviewProgress();
  setBusy(true);
  try {
    await api("/api/checklist/select", { profile: choice }); state.dirty = false;
    await refresh(); notice("Открыта отдельная версия чек-листа. Разметка других версий сохранена.");
  } catch (error) { $("profile").value = prior; showError(error); } finally { setBusy(false); }
});
$("checklist-file").addEventListener("change", async event => {
  const file = event.target.files[0]; if (!file || !allowLeave()) { event.target.value = ""; return; }
  if (file.size > 1_000_000) { notice("Слишком большой файл чек-листа.", true); event.target.value = ""; return; }
  setBusy(true);
  try {
    const value = JSON.parse(await file.text());
    state.review.active = false; state.review.task = null; renderReviewProgress();
    await api("/api/checklist", value); state.dirty = false;
    await refresh(); notice("Чек-лист загружен. Открыта разметка для этой версии; прежние файлы сохранены.");
  } catch (error) { showError(error); } finally { setBusy(false); event.target.value = ""; }
});
window.addEventListener("beforeunload", event => { if (state.dirty) { event.preventDefault(); event.returnValue = ""; } });
window.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); save("draft"); } });
try { state.annotator = localStorage.getItem("cqa-annotator") || ""; } catch (_) {}
$("annotator").value = state.annotator;
setBusy(true);
refresh().then(async () => {
  await updateReviewQueue();
  if (new URLSearchParams(window.location.search).get("review") === "1") await startReview();
}).catch(error => { setBusy(false); showError(error); });
