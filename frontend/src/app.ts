import type { Checklist, Criterion, Evaluation } from "./types.js";
import {
  addConversations,
  evaluate,
  getState,
  loadWorkspace,
  cancelWorkspaceLoad,
  importDataset,
  resolveAppeal,
  saveChecklist,
  submitAppeal,
} from "./state.js";
import { ApiError, api } from "./api.js";
import { answerLabel, validValue } from "./scoring.js";
import { importExample, parseImport } from "./import.js";
import { empty, esc, href, icon } from "./ui.js";
import { mobileHeader, navItems, updateMobileNavigation } from "./navigation.js";
import {
  allCriteriaView,
  currentEvaluation,
  selectionFromQuery,
  focusCriterion,
  qualityView,
  elapsed,
  clock,
  usesDemoAudio,
} from "./review.js";
import { criterionMaster } from "./editor.js";
import { demoWaveform } from "./media.js";
import { chartView, overviewView } from "./overview.js";
import {
  appealsView,
  checklistView,
  detailView,
  dialogueResults,
  dialoguesView,
  editorCriterion,
  Filters,
} from "./views.js";
const app = document.querySelector<HTMLDivElement>("#app")!;
const modal = document.querySelector<HTMLDialogElement>("#modal")!;
const latestChecklist = () =>
  getState().checklists[getState().checklists.length - 1];
let draft: Checklist = {id: "", name: "Новый чек-лист", version: 1, criteria: [], createdAt: ""};
let loading = true;
let loaded = false;
let loadError = "";
let draftDirty = false;
let filters: Filters = {
  search: "",
  language: "all",
  channel: "all",
  status: "all",
};
let appealStatus = "open";
let selectedEvaluation = "";
let selectedCriterion = "";
let editorSelection = draft.criteria[0]?.id || "";
let editorMobileDetail = false;
let lastRoute = "";
let loadedRoute = "";
let requestVersion = 0;
let currentPage = 1;
let searchTimer: ReturnType<typeof setTimeout>;
let toastTimer: ReturnType<typeof setTimeout>;
let modalTrigger: HTMLElement | null = null;
let appealTarget: {
  conversationId: string;
  evaluation: Evaluation;
  criterion: Criterion;
} | null = null;
let switchTarget = "";
const busy = new Set<string>();
const evaluationJobs = new Map<string, {startedAt: number; checklistId: string; engine: string}>();
const evaluationRecoveryKey = "freedom-cqa:evaluation-recovery:v1";
const evaluationErrorPrefix = "freedom-cqa:evaluation-error:v1:";
const evaluationErrors = new Map<string, string>();
interface AsrResponse {language: string; duration_seconds: number; model: string; segments: {start_seconds: number; end_seconds: number; text: string}[]}
let audioDraft: AsrResponse | null = null;
let audioImportBusy = false;
interface StoredEvaluationJob {
  conversationId: string; startedAt: number; checklistId: string; engine: string; previousEvaluationIds: string[];
}
let evaluationTimer: ReturnType<typeof setInterval> | undefined;
let recoveryTimer: ReturnType<typeof setInterval> | undefined;
let recoveredEvaluationJob: StoredEvaluationJob | undefined;
function getEvaluationError(id: string) {
  const cached = evaluationErrors.get(id);
  if (cached) return cached;
  try { return localStorage.getItem(evaluationErrorPrefix + id) || ""; } catch { return ""; }
}
function setEvaluationError(id: string, message: string) {
  evaluationErrors.set(id, message);
  try { localStorage.setItem(evaluationErrorPrefix + id, message); } catch { /* UI still shows the in-memory error. */ }
}
function clearEvaluationError(id: string) {
  evaluationErrors.delete(id);
  try { localStorage.removeItem(evaluationErrorPrefix + id); } catch { /* Ignore unavailable storage. */ }
}
function storedEvaluationJob(): StoredEvaluationJob | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(evaluationRecoveryKey) || "null") as StoredEvaluationJob | null;
    if (!value || typeof value.conversationId !== "string" || !Number.isFinite(value.startedAt)
        || typeof value.checklistId !== "string" || typeof value.engine !== "string"
        || !Array.isArray(value.previousEvaluationIds)) return undefined;
    return value;
  } catch { return undefined; }
}
function clearStoredEvaluationJob() {
  localStorage.removeItem(evaluationRecoveryKey);
  recoveredEvaluationJob = undefined;
  if (recoveryTimer) { clearInterval(recoveryTimer); recoveryTimer = undefined; }
}
function startEvaluationRecovery(job: StoredEvaluationJob) {
  if (recoveryTimer) clearInterval(recoveryTimer);
  recoveredEvaluationJob = job;
  evaluationJobs.set(job.conversationId, {startedAt: job.startedAt, checklistId: job.checklistId, engine: job.engine});
  busy.add(job.conversationId);
  if (!evaluationTimer) evaluationTimer = setInterval(updateEvaluationElapsed, 1000);
  recoveryTimer = setInterval(() => void checkRecoveredEvaluation(), 5000);
}
async function runEvaluationWithProgress(id: string, checklistId: string, engine: string) {
  if (busy.has(id)) return false;
  clearEvaluationError(id);
  const job: StoredEvaluationJob = {conversationId: id, startedAt: Date.now(), checklistId, engine,
    previousEvaluationIds: getState().conversations.find(item => item.id === id)?.evaluations.map(item => item.id) || []};
  localStorage.setItem(evaluationRecoveryKey, JSON.stringify(job));
  evaluationJobs.set(id, {startedAt: job.startedAt, checklistId, engine});
  busy.add(id); render();
  if (!evaluationTimer) evaluationTimer = setInterval(updateEvaluationElapsed, 1000);
  updateEvaluationElapsed();
  let keepRecovery = false;
  try {
    const evaluation = await evaluate(id, checklistId, engine);
    clearStoredEvaluationJob(); clearEvaluationError(id); selectedEvaluation = evaluation.id;
    notify(evaluation.needsReview ? "Оценка сохранена. Есть критерии для ручной проверки." : "Оценка сохранена");
    return true;
  } catch (error) {
    const message = errorMessage(error); setEvaluationError(id, message); notify(message, "error");
    if (error instanceof ApiError && error.status === 0) { keepRecovery = true; startEvaluationRecovery(job); }
    return false;
  } finally {
    if (!keepRecovery) {
      clearStoredEvaluationJob(); busy.delete(id); evaluationJobs.delete(id);
      if (!evaluationJobs.size && evaluationTimer) { clearInterval(evaluationTimer); evaluationTimer = undefined; }
    }
    render();
  }
}
async function checkRecoveredEvaluation() {
  const job = recoveredEvaluationJob;
  if (!job) return;
  // The local Ollama request has a hard five minute limit. Leave a short margin for saving and polling.
  if (Date.now() - job.startedAt > 330_000) {
    clearStoredEvaluationJob();
    busy.delete(job.conversationId);
    evaluationJobs.delete(job.conversationId);
    if (!evaluationJobs.size && evaluationTimer) { clearInterval(evaluationTimer); evaluationTimer = undefined; }
    if (route().section === "dialogues" && route().id === job.conversationId) {
      await refreshWorkspace();
      const message = "Оценка не завершилась за 5 минут и не была сохранена. Проверьте доступность модели и запустите её снова.";
      setEvaluationError(job.conversationId, message);
      render();
      notify(message, "error");
    }
    return;
  }
  try {
    await loadWorkspace("dialogues", job.conversationId);
    const conversation = getState().conversations.find(item => item.id === job.conversationId);
    const evaluation = conversation?.evaluations.find(item => item.checklist.id === job.checklistId
      && !job.previousEvaluationIds.includes(item.id));
    if (!evaluation) return;
    selectedEvaluation = evaluation.id;
    clearStoredEvaluationJob();
    busy.delete(job.conversationId);
    evaluationJobs.delete(job.conversationId);
    if (!evaluationJobs.size && evaluationTimer) { clearInterval(evaluationTimer); evaluationTimer = undefined; }
    if (route().section === "dialogues" && route().id === job.conversationId) {
      loaded = true; loadedRoute = route().raw; loading = false; render();
      notify("Оценка сохранена");
    }
  } catch { /* Keep the recovery marker; the next poll can retry a temporary API failure. */ }
}
function updateEvaluationElapsed() {
  const job = [...evaluationJobs.values()][0];
  const output = document.getElementById("evaluation-elapsed");
  if (!job || !output) return;
  const seconds = Math.floor((Date.now() - job.startedAt) / 1000);
  output.textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
function route() {
  const raw = location.hash.slice(1) || "/overview";
  const [path, query = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean);
  let id = "";
  try {
    id = decodeURIComponent(parts[1] || "");
  } catch {
    /* Invalid route falls back to missing record. */
  }
  return { raw, section: parts[0] || "overview", id, query };
}
function nav(section: string) {
  const pending = getState().openAppeals;
  return `<a href="#/overview" class="brand"><img src="./assets/brand/freedom-logo.svg" alt="Freedom"></a><nav aria-label="Основная навигация">${navItems.map((item) => `<a href="#/${item.id}" class="nav-item ${section === item.id ? "active" : ""}"${section === item.id ? ' aria-current="page"' : ""}>${icon(item.icon, 21)}<span>${item.label}</span>${item.id === "appeals" && pending ? `<span class="nav-badge">${pending}</span>` : ""}</a>`).join("")}</nav><div class="sidebar-bottom"><button class="help-link" data-action="help">${icon("help", 20)}Помощь</button></div>`;
}
function render() {
  const r = route();
  const { conversations } = getState();
  if (r.raw !== lastRoute) {
    selectedEvaluation = "";
    selectedCriterion = "";
    if (r.section === "dialogues") {
      const conversation = conversations.find((c) => c.id === r.id);
      if (conversation) {
        const selection = selectionFromQuery(conversation, r.query);
        selectedEvaluation = selection.evaluationId;
        selectedCriterion = selection.criterionId;
      }
    }
  }
  let content = "";
  if (loading) content = empty("Загружаем данные", "Получаем данные этого раздела с сервера.");
  else if (!loaded || loadedRoute !== r.raw) content = empty("Не удалось загрузить данные", loadError, '<button class="button primary" data-action="refresh">Повторить</button>');
  else if (r.section === "dialogues" && r.id) {
    const c = conversations.find((c) => c.id === r.id);
    content = c
      ? detailView(c, selectedEvaluation, selectedCriterion, evaluationJobs.get(c.id), getEvaluationError(c.id))
      : empty(
          "Диалог не найден",
          "Откройте диалог из рабочего пространства.",
          '<a class="button secondary" href="#/dialogues">К диалогам</a>',
        );
  } else if (r.section === "dialogues") content = dialoguesView(filters);
  else if (r.section === "checklists")
    content = checklistView(
      draft,
      draftDirty,
      editorSelection,
      editorMobileDetail,
    );
  else if (r.section === "appeals") content = appealsView(appealStatus, r.id);
  else content = overviewView();
  app.innerHTML = `<div class="app-shell"><aside class="sidebar" aria-label="Навигация и помощь">${nav(r.section)}</aside><div class="app-main"><header class="topbar">${mobileHeader(r.section, Boolean(r.id))}<div class="breadcrumb"><button class="icon-button mobile-menu-button" aria-label="Открыть навигацию" data-action="menu">${icon("menu", 22)}</button><a href="#/overview">CQA</a>${icon("chevron", 14)}<span>${navItems.find((n) => n.id === r.section)?.label || "Обзор"}</span>${r.id ? `${icon("chevron", 14)}<strong>${r.section === "appeals" ? "Рассмотрение" : "Анализ разговора"}</strong>` : ""}</div><div class="topbar-actions"><button class="icon-button mobile-help" data-action="help" aria-label="Помощь">${icon("help", 21)}</button><button class="text-button refresh-button" data-action="refresh" aria-label="Обновить данные"${loading ? " disabled" : ""}>${icon("refresh", 20)}<span>Обновить данные</span></button></div></header><main id="main-content" class="main-content ${r.section === "dialogues" && r.id ? "conversation-main" : ""}" tabindex="-1">${loadError && loaded ? `<div class="notice-box" role="alert">${esc(loadError)}</div>` : ""}${content}</main></div></div>`;
  updateMobileNavigation(r.section, getState().openAppeals);
  document.title = `${navItems.find((n) => n.id === r.section)?.label || "Обзор"} · Freedom CQA`;
  if (busy.has(r.id)) setEvaluationBusy(r.id);
  if (loaded && !loading) lastRoute = r.raw;
  if (r.section === "dialogues" && r.id) {
    const c = conversations.find((c) => c.id === r.id);
    const e = c ? currentEvaluation(c, selectedEvaluation) : undefined;
    const cr = e ? focusCriterion(e, selectedCriterion) : undefined;
    const fromQuery = new URLSearchParams(r.query).get("evidence");
    const candidate = fromQuery === null ? undefined : Number(fromQuery);
    const index =
      candidate !== undefined &&
      Number.isInteger(candidate) &&
      c?.transcript[candidate]
        ? candidate
        : e?.results.find((result) => result.criterionId === cr?.id)
            ?.evidence[0];
    attachPlayer(index);
    if (index !== undefined)
      requestAnimationFrame(() => focusEvidence(index, false, false));
  }
}
function attachPlayer(initialIndex?: number) {
  const audio = document.getElementById(
    "conversation-audio",
  ) as HTMLAudioElement | null;
  const c = getState().conversations.find((c) => c.id === route().id);
  if (!audio || !c) return;
  const sync = () => {
    const duration = Number.isFinite(audio.duration)
      ? audio.duration
      : usesDemoAudio(c)
        ? demoWaveform.duration
        : 0;
    const output = document.getElementById("player-time");
    if (output)
      output.textContent = `${clock(audio.currentTime)} / ${clock(duration)}`;
    const range = document.getElementById(
      "player-seek",
    ) as HTMLInputElement | null;
    if (range) {
      range.max = String(duration);
      range.value = String(audio.currentTime);
    }
    const cursor = document.getElementById("waveform-cursor");
    if (cursor)
      cursor.style.left = `${duration ? (audio.currentTime / duration) * 100 : 0}%`;
    const button = document.querySelector<HTMLButtonElement>(
      '[data-action="audio-play"]',
    );
    if (button) {
      button.innerHTML = icon(audio.paused ? "play" : "pause", 22);
      button.setAttribute(
        "aria-label",
        audio.paused ? "Воспроизвести запись" : "Приостановить запись",
      );
    }
  };
  audio.addEventListener("timeupdate", sync);
  audio.addEventListener("play", sync);
  audio.addEventListener("pause", sync);
  audio.addEventListener("ended", sync);
  audio.addEventListener("error", () => {
    const error = document.getElementById("audio-error");
    if (error) {
      error.hidden = false;
      error.textContent = "Не удалось загрузить запись";
    }
  });
  audio.addEventListener(
    "loadedmetadata",
    () => {
      if (initialIndex !== undefined)
        audio.currentTime = Math.min(audio.duration, elapsed(c, initialIndex));
      sync();
    },
    { once: true },
  );
}
function focusEvidence(index: number, activateTab = true, moveFocus = true) {
  if (activateTab) detailTab("transcript");
  document
    .querySelectorAll(".message.highlighted")
    .forEach((el) => el.classList.remove("highlighted"));
  const message = document.getElementById(`message-${index}`);
  message?.classList.add("highlighted");
  if (moveFocus) message?.focus({ preventScroll: true });
  const container = document.querySelector<HTMLElement>(".transcript-messages");
  if (message && moveFocus && matchMedia("(max-width: 760px)").matches) {
    message.scrollIntoView({
      block: "center",
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  } else if (message && container && container.clientHeight) {
    const previous = document.getElementById(`message-${index - 1}`);
    const context =
      previous &&
      previous.offsetHeight + message.offsetHeight <= container.clientHeight
        ? previous
        : message;
    const top =
      context.getBoundingClientRect().top -
      container.getBoundingClientRect().top +
      container.scrollTop;
    container.scrollTo({
      top: Math.max(0, top),
      behavior:
        moveFocus && !matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "smooth"
          : "auto",
    });
  }
  const c = getState().conversations.find((c) => c.id === route().id);
  const audio = document.getElementById(
    "conversation-audio",
  ) as HTMLAudioElement | null;
  if (c && audio && Number.isFinite(audio.duration))
    audio.currentTime = Math.min(audio.duration, elapsed(c, index));
  const selection = document.getElementById("waveform-selection");
  const m = demoWaveform.messages.find((m) => m.index === index);
  if (selection && m) {
    selection.style.left = `${(m.start / demoWaveform.duration) * 100}%`;
    selection.style.width = `${(m.duration / demoWaveform.duration) * 100}%`;
  }
}
function notify(message: string, kind: "success" | "error" = "success") {
  const toast = document.querySelector<HTMLDivElement>("#toast")!;
  clearTimeout(toastTimer);
  toast.innerHTML = `${icon(kind === "error" ? "alert" : "check", 18)}<span>${esc(message)}</span><button data-action="close-toast" aria-label="Закрыть уведомление">${icon("close", 15)}</button>`;
  toast.classList.add("visible");
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 5000);
}
function openModal(
  title: string,
  description: string,
  body: string,
  wide = false,
) {
  modalTrigger = document.activeElement as HTMLElement;
  if (modal.open) modal.close();
  modal.className = `modal ${wide ? "modal-wide" : ""}`;
  modal.innerHTML = `<div class="modal-heading"><div><h2 id="modal-title">${esc(title)}</h2>${description ? `<p>${esc(description)}</p>` : ""}</div><button class="icon-button" data-action="close-modal" aria-label="Закрыть окно">${icon("close", 20)}</button></div>${body}`;
  modal.showModal();
  document.body.style.overflow = "hidden";
}
function closeModal() {
  modal.close();
  document.body.style.overflow = "";
  modalTrigger?.focus();
}
modal.addEventListener("close", () => {
  document.body.style.overflow = "";
  modalTrigger?.focus();
});
modal.addEventListener("click", (event) => {
  if (event.target !== modal) return;
  const rect = modal.getBoundingClientRect();
  if (
    event.clientX < rect.left ||
    event.clientX > rect.right ||
    event.clientY < rect.top ||
    event.clientY > rect.bottom
  )
    closeModal();
});
function uploadModal() {
  audioDraft = null;
  openModal(
    "Загрузить диалоги",
    "Добавьте транскрипты в рабочее пространство для оценки.",
    `<details class="audio-import" open><summary>Загрузить аудио и оценить</summary><form id="audio-form"><div class="field"><label for="audio-file">Запись для расшифровки</label><input id="audio-file" name="file" type="file" accept=".mp3,.wav,.m4a,.mp4,.mpeg,.mpga,.webm" required><span class="muted">До 25 МиБ и 30 минут. Распознавание работает локально на этом Mac.</span></div><div class="field"><label for="audio-language">Язык записи</label><select id="audio-language" name="language"><option value="auto">Определить автоматически</option><option value="ru">Русский</option><option value="kk">Казахский</option><option value="en">Английский</option></select></div><p id="audio-status" class="muted" role="status" hidden></p><p id="audio-error" class="form-error" role="alert" hidden></p><button type="submit" class="button secondary">Распознать аудио</button></form><div id="audio-transcript-editor" class="asr-editor" hidden></div></details><form id="upload-form"><input type="file" id="json-file" accept=".json,application/json" hidden aria-label="JSON-файл с диалогами"><button class="upload-zone" type="button" data-action="choose-file"><span class="upload-icon">${icon("file", 26)}</span><strong id="upload-filename">Выберите JSON-файл</strong><span>Массив диалогов или ответ API · до 4 МиБ</span><span class="button secondary small">${icon("upload", 15)}Выбрать файл</span></button><div class="field"><div class="field-heading"><label for="json-input">Или вставьте JSON</label><button type="button" class="text-button" data-action="import-example">Вставить пример</button></div><textarea id="json-input" class="code-input" rows="7" required placeholder='[ { "conversation_id": "…", "transcript": […] } ]'></textarea><span class="muted">Если поле <code>language</code> отсутствует или равно <code>auto</code>, язык определится по репликам.</span></div><p id="import-error" class="form-error" role="alert" hidden></p><div class="modal-footer"><span class="muted">Данные сохраняются на сервере. До 100 диалогов за один импорт.</span><button type="submit" class="button primary">Добавить диалоги${icon("arrow", 16)}</button></div></form>`,
    true,
  );
  modal.insertAdjacentHTML("beforeend", `<details><summary>Импорт набора организатора</summary><form id="dataset-form"><div class="field"><label for="dataset-group">ID набора</label><input id="dataset-group" name="group" value="DEV" required maxlength="80"></div><p id="dataset-error" class="form-error" role="alert" hidden></p><button class="button secondary" type="submit">Импортировать набор</button></form></details>`);
}
function showAudioTranscript(result: AsrResponse) {
  audioDraft = result;
  const container = document.getElementById("audio-transcript-editor");
  if (!container) return;
  const lang = ({ru: "русский", kk: "казахский", en: "английский"} as Record<string, string>)[result.language] || result.language;
  container.hidden = false;
  container.innerHTML = `<div class="notice-box"><strong>Расшифровка готова · ${esc(lang)}</strong><br>Whisper не определяет роли собеседников. Назначьте говорящего у каждой части и при необходимости поправьте текст; после этого диалог сохранится и запустится оценка.</div><div class="field"><label for="audio-detected-language">Язык транскрипта</label><select id="audio-detected-language"><option value=""${!["ru", "kk", "en"].includes(result.language) ? " selected" : ""}>Укажите язык</option><option value="ru"${result.language === "ru" ? " selected" : ""}>Русский</option><option value="kk"${result.language === "kk" ? " selected" : ""}>Казахский</option><option value="en"${result.language === "en" ? " selected" : ""}>Английский</option></select></div>${result.segments.map((segment, i) => {
    const start = Math.floor(segment.start_seconds), end = Math.floor(segment.end_seconds);
    const time = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    return `<div class="asr-turn"><label for="asr-speaker-${i}">Часть ${i + 1} · ${time(start)}–${time(end)}</label><select id="asr-speaker-${i}" aria-label="Говорящий, часть ${i + 1}"><option value="">Назначить говорящего…</option><option value="client">Клиент</option><option value="operator">Оператор</option></select><textarea id="asr-text-${i}" rows="2" aria-label="Текст, часть ${i + 1}" required>${esc(segment.text)}</textarea></div>`;
  }).join("")}<p id="audio-save-error" class="form-error" role="alert" hidden></p><button class="button primary" type="button" data-action="audio-evaluate">Добавить диалог и запустить оценку${icon("arrow", 16)}</button>`;
}
function showError(id: string, message: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
}
function setEvaluationBusy(id: string) {
  document
    .querySelectorAll<HTMLButtonElement>('[data-action="evaluate"]')
    .forEach((button) => {
      if (button.dataset.id === id) {
        button.disabled = true;
        button.innerHTML = `${icon("spark", 17, "pulse")}Оцениваем…`;
      }
    });
}
function detailTab(tab: string) {
  const grid = document.getElementById("detail-grid");
  if (!grid) return;
  grid.classList.toggle("mobile-show-transcript", tab === "transcript");
  grid.classList.toggle("mobile-show-evaluation", tab === "evaluation");
  document
    .querySelectorAll<HTMLButtonElement>('[data-action="detail-tab"]')
    .forEach((button) => {
      button.classList.toggle("active", button.dataset.tab === tab);
      button.setAttribute("aria-pressed", String(button.dataset.tab === tab));
    });
}
function updateDraftUI() {
  const status = document.getElementById("draft-status");
  if (status) status.textContent = `Версия ${draft.version} · Есть изменения`;
  const save = document.getElementById(
    "save-checklist",
  ) as HTMLButtonElement | null;
  if (save) save.disabled = false;
  const total = draft.criteria.reduce(
    (sum, c) => sum + (Number.isFinite(c.weight) ? c.weight : 0),
    0,
  );
  const label = document.getElementById("weight-total");
  if (label) {
    label.innerHTML = `${Number(total.toFixed(1))}% <small>/ 100%</small>`;
    label.className =
      Math.abs(total - 100) < 0.01 ? "text-success" : "text-warning";
  }
}
function loadChecklist(id: string) {
  const c = getState().checklists.find((c) => c.id === id);
  if (!c) return;
  draft = structuredClone(c);
  draftDirty = false;
  editorSelection = draft.criteria[0]?.id || "";
  editorMobileDetail = false;
  render();
}
function mutateCriterion(
  target: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement,
) {
  const c = draft.criteria.find((c) => c.id === target.dataset.id);
  if (!c) return;
  const key = target.dataset.field;
  if (key === "weight") c.weight = (target as HTMLInputElement).valueAsNumber;
  else if (key === "steps") {
    c.steps = target.value.split(",").map((v) => Number(v.trim()));
    c.min = 0;
    c.max = Math.max(...c.steps);
  } else if (key === "stepDescriptions") {
    c.stepDescriptions = Object.fromEntries(
      target.value
        .split("\n")
        .filter((line) => line.includes(":"))
        .map((line) => {
          const i = line.indexOf(":");
          return [line.slice(0, i).trim(), line.slice(i + 1).trim()];
        }),
    );
  } else if (key === "allowNA") {
    c.allowNA = (target as HTMLInputElement).checked;
    const el = document.querySelector<HTMLElement>(
      `[data-na-field="${CSS.escape(c.id)}"]`,
    );
    if (el) el.hidden = !c.allowNA;
  } else if (key === "type") {
    c.type = target.value as Criterion["type"];
    c.steps = c.type === "scale" ? [0, 5, 10, 15, 20] : [0, 1];
    c.min = 0;
    c.max = c.type === "scale" ? 20 : 1;
    c.stepDescriptions = {};
    if (c.type === "flag") {
      c.weight = 0;
      c.allowNA = false;
      c.naCondition = "";
    }
    const index = draft.criteria.findIndex((x) => x.id === c.id);
    document.getElementById("criterion-editor")!.innerHTML = editorCriterion(
      c,
      index,
    );
    document.getElementById(`type-${c.id}`)?.focus();
  } else if (
    key === "name" ||
    key === "prompt" ||
    key === "section" ||
    key === "naCondition"
  )
    c[key] = target.value;
  draftDirty = true;
  updateDraftUI();
  const title = document.querySelector<HTMLElement>(
    `[data-title="${CSS.escape(c.id)}"]`,
  );
  if (title) title.textContent = c.name || "Без названия";
  const weight = document.querySelector<HTMLElement>(
    `[data-weight="${CSS.escape(c.id)}"]`,
  );
  if (weight)
    weight.textContent = `${Number.isFinite(c.weight) ? c.weight : "—"}%`;
}
document.addEventListener("input", (event) => {
  const target = event.target as HTMLInputElement;
  if (target.id === "player-seek") {
    const audio = document.getElementById(
      "conversation-audio",
    ) as HTMLAudioElement | null;
    if (audio) audio.currentTime = Number(target.value);
  }
  if (target.id === "search") {
    filters.search = target.value;
    scheduleDialogueSearch();
  }
  if (target.id === "checklist-name") {
    draft.name = target.value;
    draftDirty = true;
    updateDraftUI();
  }
  if (target.dataset.field) mutateCriterion(target);
});
document.addEventListener("change", async (event) => {
  const target = event.target as HTMLInputElement;
  if (target.dataset.filter) {
    filters[target.dataset.filter as keyof Filters] = target.value;
    currentPage = 1;
    await refreshWorkspace(true);
  }
  if (target.id === "checklist-version") {
    const id = target.value;
    if (!draftDirty) loadChecklist(id);
    else {
      switchTarget = id;
      target.value = draft.id;
      openModal(
        "Открыть другую версию?",
        "Несохранённые изменения будут потеряны.",
        `<div class="modal-footer"><button class="button secondary" data-action="close-modal">Остаться</button><button class="button primary" data-action="confirm-switch">Открыть</button></div>`,
      );
    }
  }
  if (target.id === "evaluation-history") {
    selectedEvaluation = target.value;
    selectedCriterion = "";
    render();
  }
  if (target.name === "decision")
    document.getElementById("new-value-field")!.hidden =
      target.value !== "change";
  if (target.id === "json-file") {
    const file = target.files?.[0];
    if (!file) return;
    if (file.size > 4 * 1024 * 1024) {
      showError("import-error", "Размер файла должен быть не больше 4 МиБ.");
      return;
    }
    try {
      const raw = await file.text();
      if (!modal.open || !document.getElementById("json-input")) return;
      (document.getElementById("json-input") as HTMLTextAreaElement).value =
        raw;
      document.getElementById("upload-filename")!.textContent = file.name;
    } catch {
      showError(
        "import-error",
        "Не удалось прочитать файл. Попробуйте выбрать его ещё раз.",
      );
    }
  }
});
document.addEventListener("click", async (event) => {
  const target = event.target as Element;
  const control = target.closest<HTMLElement>("[data-action]");
  const link = target.closest<HTMLAnchorElement>("a");
  if (link?.classList.contains("skip-link")) {
    event.preventDefault();
    document.getElementById("main-content")?.focus();
    return;
  }
  if (pendingForms.size && link) { event.preventDefault(); return; }
  if (link && modal.open && modal.classList.contains("navigation-modal"))
    closeModal();
  if (!control) return;
  const action = control.dataset.action;
  if ((busy.size || pendingForms.size) && ["refresh", "evaluate", "upload", "confirm-switch", "checklist-version", "add-criterion", "delete-criterion"].includes(action || "")) {
    notify("Дождитесь завершения текущей операции."); return;
  }
  // Safari does not focus buttons on tap; retain a real return target for dialogs.
  if (["upload", "menu", "help", "all-criteria", "appeal"].includes(action || "")) {
    control.focus({ preventScroll: true });
  }
  if (action === "refresh") { await refreshWorkspace(); return; }
  if (action === "upload") uploadModal();
  if (action === "close-modal") closeModal();
  if (action === "close-toast")
    document.getElementById("toast")!.classList.remove("visible");
  if (action === "choose-file") document.getElementById("json-file")!.click();
  if (action === "import-example") {
    (document.getElementById("json-input") as HTMLTextAreaElement).value =
      importExample;
    document.getElementById("upload-filename")!.textContent =
      "Выберите JSON-файл";
    document.getElementById("import-error")!.hidden = true;
  }
  if (action === "audio-evaluate") {
    if (!audioDraft || audioImportBusy || pendingForms.size) return;
    audioImportBusy = true;
    const error = document.getElementById("audio-save-error")!;
    error.hidden = true;
    try {
      const transcript = audioDraft.segments.map((segment, i) => {
        const speaker = (document.getElementById(`asr-speaker-${i}`) as HTMLSelectElement | null)?.value;
        const text = (document.getElementById(`asr-text-${i}`) as HTMLTextAreaElement | null)?.value.trim();
        if (speaker !== "client" && speaker !== "operator") throw new Error(`Назначьте говорящего для части ${i + 1}.`);
        if (!text) throw new Error(`Добавьте текст в части ${i + 1}.`);
        const seconds = Math.floor(segment.start_seconds);
        return {id: String(i + 1), timestamp: `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`, speaker, text};
      });
      const language = ({ru: "RU", kk: "KZ", en: "EN"} as Record<string, string>)[(document.getElementById("audio-detected-language") as HTMLSelectElement | null)?.value || ""];
      if (!language) throw new Error("Выберите язык транскрипта: русский, казахский или английский.");
      const imported = await addConversations(parseImport(JSON.stringify([{
        conversation_id: `audio-${crypto.randomUUID()}`, title: "Расшифрованный звонок",
        channel: "call", language, transcript, audio_url: null,
      }])));
      const conversation = imported[0];
      if (!conversation) throw new Error("Диалог не добавился в рабочее пространство.");
      const checklist = getState().checklists.find(item => item.criteria.some(criterion => criterion.rule?.type === "semantic")) || latestChecklist();
      if (!checklist) throw new Error("Не найден чек-лист для оценки.");
      closeModal(); location.hash = `/dialogues/${encodeURIComponent(conversation.id)}`;
      await runEvaluationWithProgress(conversation.id, checklist.id, "auto");
    } catch (err) { showError("audio-save-error", errorMessage(err)); }
    finally { audioImportBusy = false; }
  }
  if (action === "menu") {
    openModal(
      "Рабочее пространство",
      "",
      `<div class="mobile-navigation">${nav(route().section)}</div>`,
    );
    modal.classList.add("navigation-modal");
  }
  if (action === "help") {
    if (modal.open) closeModal();
    openModal(
      "От диалога к решению",
      "Три шага для проверки качества обслуживания.",
      `<ol class="help-steps"><li><span>01</span><div><h3>Выберите диалог</h3><p>Откройте разговор из списка или загрузите транскрипты в JSON.</p></div></li><li><span>02</span><div><h3>Проверьте оценку</h3><p>Выберите чек-лист. Откройте обоснование и перейдите к реплике-доказательству.</p></div></li><li><span>03</span><div><h3>Примите решение</h3><p>Оспорьте критерий, рассмотрите апелляцию и сохраните финальный результат.</p></div></li></ol><div class="notice-box">Диалоги, чек-листы, оценки и решения сохраняются на сервере. Для AI-оценки нужна настроенная модель. Ручная проверка создаёт оценку с неоценёнными смысловыми критериями.</div><div class="modal-footer"><button class="button primary" data-action="close-modal">Всё понятно</button></div>`,
    );
  }
  if (action === "chart") {
    const mode = control.dataset.mode!;
    document.getElementById("chart-content")!.innerHTML = chartView(mode);
    document.querySelectorAll('[data-action="chart"]').forEach((button) => {
      button.classList.toggle(
        "active",
        (button as HTMLElement).dataset.mode === mode,
      );
      button.setAttribute(
        "aria-pressed",
        String((button as HTMLElement).dataset.mode === mode),
      );
    });
  }
  if (action === "reset-filters") {
    filters = { search: "", language: "all", channel: "all", status: "all" };
    currentPage = 1;
    await refreshWorkspace();
  }
  if (action === "dialogue-page" || action === "appeal-page") {
    currentPage = Number(control.dataset.page);
    if (action === "appeal-page" && route().id) {
      location.hash = `/appeals?page=${currentPage}&status=${appealStatus}`;
      return;
    }
    await refreshWorkspace();
  }
  if (action === "detail-tab") detailTab(control.dataset.tab!);
  if (action === "evidence") focusEvidence(Number(control.dataset.index));
  if (action === "audio-play") {
    const audio = document.getElementById(
      "conversation-audio",
    ) as HTMLAudioElement | null;
    if (audio) {
      if (audio.paused) {
        try {
          await audio.play();
        } catch {
          notify("Не удалось воспроизвести запись. Попробуйте ещё раз.");
        }
      } else audio.pause();
    }
  }
  if (action === "all-criteria") {
    const c = getState().conversations.find((c) => c.id === route().id);
    const e = c ? currentEvaluation(c, selectedEvaluation) : undefined;
    if (c && e) {
      openModal(
        `Все ${e.checklist.criteria.length} критериев`,
        `${e.checklist.name} · версия ${e.checklist.version}`,
        allCriteriaView(c, e),
        true,
      );
      modal.classList.add("criteria-modal");
    }
  }
  if (action === "focus-criterion") {
    const c = getState().conversations.find((c) => c.id === route().id);
    const e = c ? currentEvaluation(c, selectedEvaluation) : undefined;
    if (c && e) {
      selectedCriterion = control.dataset.id!;
      closeModal();
      document.querySelector(".quality-workbench")!.innerHTML = qualityView(
        c,
        e,
        selectedCriterion,
      );
      const index = e.results.find((r) => r.criterionId === selectedCriterion)
        ?.evidence[0];
      if (index !== undefined) focusEvidence(index, false, false);
      const focus = document.querySelector<HTMLElement>(".focused-criterion");
      focus?.setAttribute("tabindex", "-1");
      focus?.focus({ preventScroll: true });
    }
  }
  if (action === "select-editor-criterion") {
    editorSelection = control.dataset.id!;
    editorMobileDetail = true;
    const c = draft.criteria.find((c) => c.id === editorSelection);
    if (c) {
      document.getElementById("criterion-editor")!.innerHTML = editorCriterion(
        c,
        draft.criteria.indexOf(c),
      );
      document.getElementById("criteria-master-items")!.innerHTML =
        criterionMaster(draft, editorSelection);
      const workspace = document.querySelector(".checklist-workspace");
      workspace?.classList.add("editor-show-detail");
      workspace?.classList.remove("editor-show-list");
      if (matchMedia("(max-width: 760px)").matches) {
        const heading = document.querySelector<HTMLElement>(".criterion-editor-header h2");
        heading?.setAttribute("tabindex", "-1");
        heading?.focus({ preventScroll: true });
        document.querySelector(".criterion-editor-header")?.scrollIntoView({ block: "start" });
      }
    }
  }
  if (action === "editor-back") {
    editorMobileDetail = false;
    const workspace = document.querySelector(".checklist-workspace");
    workspace?.classList.add("editor-show-list");
    workspace?.classList.remove("editor-show-detail");
    if (matchMedia("(max-width: 760px)").matches) {
      const selected = document.querySelector<HTMLElement>(".criterion-master-item.selected");
      selected?.focus({ preventScroll: true });
      selected?.scrollIntoView({ block: "center" });
    }
  }
  if (action === "evaluate") {
    const id = control.dataset.id!;
    const checklistId = (
      document.getElementById("evaluation-checklist") as HTMLSelectElement
    ).value;
    const engine = (document.getElementById("evaluation-engine") as HTMLSelectElement).value;
    await runEvaluationWithProgress(id, checklistId, engine);
  }
  if (action === "appeal") {
    const c = getState().conversations.find((c) => c.id === route().id);
    const evaluation = c?.evaluations.find(
      (e) => e.id === control.dataset.evaluation,
    );
    const criterion = evaluation?.checklist.criteria.find(
      (cr) => cr.id === control.dataset.criterion,
    );
    if (!c || !evaluation || !criterion) return;
    appealTarget = { conversationId: c.id, evaluation, criterion };
    const value =
      evaluation.results.find((r) => r.criterionId === criterion.id)?.value ??
      null;
    openModal(
      "Оспорить оценку",
      "Объясните, почему критерий требует пересмотра.",
      `<form id="appeal-form"><div class="field"><label for="appeal-author">Ваше имя</label><input id="appeal-author" name="author" required maxlength="120" autocomplete="name"></div><div class="appeal-criterion"><span class="eyebrow">СПОРНЫЙ КРИТЕРИЙ</span><h3>${esc(criterion.name)}</h3><span class="badge warning">${esc(answerLabel(value, criterion, evaluation.results.find(r => r.criterionId === criterion.id)?.status))}</span></div><div class="field"><label for="appeal-comment">Комментарий к апелляции</label><textarea id="appeal-comment" name="comment" rows="5" required maxlength="2000" placeholder="Что нужно учесть проверяющему? Укажите фрагмент или контекст разговора."></textarea></div><p id="appeal-error" class="form-error" role="alert" hidden></p><button type="button" class="text-button" data-action="refresh">Обновить данные</button><div class="modal-footer"><button type="button" class="button secondary" data-action="close-modal">Отмена</button><button type="submit" class="button primary">Отправить апелляцию${icon("external", 15)}</button></div></form>`,
    );
  }
  if (action === "appeal-filter") {
    appealStatus = control.dataset.status!;
    currentPage = 1;
    if (route().id) {
      location.hash = "/appeals";
    } else await refreshWorkspace();
  }
  if (action === "checklist-version") {
    const id = control.dataset.id!;
    if (!draftDirty) loadChecklist(id);
    else {
      switchTarget = id;
      openModal(
        "Перейти к другой версии?",
        "Несохранённые изменения в редакторе будут потеряны.",
        `<div class="modal-footer"><button class="button secondary" data-action="close-modal">Остаться</button><button class="button primary" data-action="confirm-switch">Перейти${icon("external", 15)}</button></div>`,
      );
    }
  }
  if (action === "confirm-switch") {
    closeModal();
    loadChecklist(switchTarget);
  }
  if (action === "add-criterion") {
    const c: Criterion = {
      id: `criterion-${Date.now()}`,
      name: "Новый критерий",
      section: "Дополнительные критерии",
      prompt: "",
      weight: 10,
      type: "binary",
      min: 0,
      max: 1,
      steps: [0, 1],
      stepDescriptions: {},
      allowNA: false,
      naCondition: "",
    };
    draft.criteria.push(c);
    draftDirty = true;
    editorSelection = c.id;
    editorMobileDetail = true;
    render();
    document.getElementById(`name-${c.id}`)?.focus();
  }
  if (action === "delete-criterion") {
    draft.criteria = draft.criteria.filter((c) => c.id !== control.dataset.id);
    draftDirty = true;
    editorSelection = draft.criteria[0]?.id || "";
    render();
  }
});
const pendingForms = new Set<string>();
document.addEventListener("submit", async (event) => {
  const form = event.target as HTMLFormElement;
  const errors: Record<string, string> = {"upload-form": "import-error", "audio-form": "audio-error", "appeal-form": "appeal-error", "resolve-form": "review-error", "checklist-form": "checklist-error", "dataset-form": "dataset-error"};
  if (!errors[form.id]) return;
  event.preventDefault();
  if (loading || pendingForms.size || busy.size) { notify("Дождитесь завершения текущей операции."); return; }
  const data = new FormData(form);
  const controls = Array.from(form.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | HTMLButtonElement>("input, select, textarea, button"));
  const previouslyDisabled = controls.map(c => c.disabled);
  pendingForms.add(form.id);
  let saved = false;
  controls.forEach(c => c.disabled = true);
  // The checklist submit button is outside the form.
  const externalSubmit = document.getElementById("save-checklist") as HTMLButtonElement | null;
  if (form.id === "checklist-form" && externalSubmit) externalSubmit.disabled = true;
  try {
    if (form.id === "audio-form") {
      const file = data.get("file");
      if (!(file instanceof File) || !file.size) throw new Error("Выберите аудиофайл.");
      const status = document.getElementById("audio-status")!;
      status.hidden = false; status.textContent = "Загружаю аудио и распознаю речь локальной моделью…";
      const result = await api.upload<AsrResponse>("transcribe", data, 600000);
      showAudioTranscript(result);
      status.textContent = `Распознано частей: ${result.segments.length}. Проверьте говорящих перед оценкой.`;
    } else if (form.id === "upload-form") {
      const records = parseImport((document.getElementById("json-input") as HTMLTextAreaElement).value);
      const count = (await addConversations(records)).length;
      closeModal(); location.hash = "/dialogues";
      notify(`Добавлено диалогов: ${count}`);
    } else if (form.id === "dataset-form") {
      const result = await importDataset(String(data.get("group") || "").trim());
      closeModal(); location.hash = "/dialogues";
      notify(`Импортировано: ${result.imported}. Пропущено: ${result.skipped}.`);
    } else if (form.id === "appeal-form" && appealTarget) {
      await submitAppeal({ conversationId: appealTarget.conversationId, evaluationId: appealTarget.evaluation.id,
        criterionId: appealTarget.criterion.id, originalValue: appealTarget.evaluation.results.find(r => r.criterionId === appealTarget!.criterion.id)?.value ?? null,
        author: String(data.get("author") || "").trim(), comment: String(data.get("comment") || "").trim() });
      closeModal(); render(); notify("Апелляция отправлена на рассмотрение");
    } else if (form.id === "resolve-form") {
      await resolveAppeal(form.dataset.id!, data.get("decision") === "change" ? "change" : "confirm",
        data.get("value") === "na" ? null : Number(data.get("value")),
        String(data.get("reason") || "").trim(), String(data.get("reviewer") || "").trim(),
        String(data.get("evidence") || ""), String(data.get("range-start") || ""), String(data.get("range-end") || ""));
      appealStatus = "resolved"; notify("Решение сохранено. Итоговая оценка пересчитана.");
    } else if (form.id === "checklist-form") {
      const problem = validateChecklist(draft);
      if (problem) throw new Error(problem);
      draft = structuredClone(await saveChecklist(draft));
      draftDirty = false; render(); notify(`Чек-лист сохранён · версия ${draft.version}`);
    }
    saved = true;
  } catch (error) { showError(errors[form.id], errorMessage(error)); }
  finally {
    pendingForms.delete(form.id);
    controls.forEach((c, i) => c.disabled = previouslyDisabled[i]);
    if (form.id === "checklist-form" && externalSubmit?.isConnected) externalSubmit.disabled = !draftDirty;
    if (["upload-form", "dataset-form", "resolve-form"].includes(form.id) && saved) {
      await refreshWorkspace();
    }
  }
});
function errorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : "Не удалось выполнить операцию.";
  return error instanceof ApiError && error.status === 409
    ? `${message} Нажмите «Обновить данные», проверьте введённые значения и повторите действие.` : message;
}
function scheduleDialogueSearch() {
  clearTimeout(searchTimer);
  cancelWorkspaceLoad();
  requestVersion++;
  currentPage = 1;
  const results = document.getElementById("dialogue-results");
  if (results) results.innerHTML = empty("Ищем диалоги", "Обновляем результаты поиска.");
  searchTimer = setTimeout(() => void refreshWorkspace(true), 300);
}
async function refreshWorkspace(resultsOnly = false) {
  if (loaded && (busy.size || pendingForms.size)) { notify("Дождитесь завершения текущей операции."); return; }
  clearTimeout(searchTimer);
  const version = ++requestVersion;
  const requestedRoute = route();
  if (loadedRoute !== requestedRoute.raw) resultsOnly = false;
  const resolveForm = document.getElementById("resolve-form") as HTMLFormElement | null;
  const savedForm = resolveForm ? {id: resolveForm.dataset.id, entries: Array.from(new FormData(resolveForm).entries())} : null;
  loading = true; loadError = "";
  if (!resultsOnly) render();
  else { const results = document.getElementById("dialogue-results"); if (results) results.innerHTML = empty("Загружаем диалоги", "Обновляем результаты."); }
  try {
    const committed = await loadWorkspace(requestedRoute.section, requestedRoute.id, {
      ...filters, page: currentPage, status: requestedRoute.section === "appeals" ? appealStatus : filters.status,
    });
    if (!committed || version !== requestVersion || route().raw !== requestedRoute.raw) return;
    loaded = true; loadedRoute = requestedRoute.raw;
    if (requestedRoute.section === "appeals") appealStatus = getState().appealStatus;
    if (appealTarget && modal.open && document.getElementById("appeal-form")) {
      const target = appealTarget;
      const evaluation = getState().conversations.find(c => c.id === target.conversationId)?.evaluations.find(e => e.id === target.evaluation.id);
      const criterion = evaluation?.checklist.criteria.find(c => c.id === target.criterion.id);
      if (evaluation && criterion) {
        const changed = evaluation.revision !== target.evaluation.revision;
        appealTarget = {conversationId: target.conversationId, evaluation, criterion};
        const result = evaluation.results.find(r => r.criterionId === criterion.id);
        const panel = modal.querySelector(".appeal-criterion");
        if (panel) panel.innerHTML = `<span class="eyebrow">СПОРНЫЙ КРИТЕРИЙ</span><h3>${esc(criterion.name)}</h3><span class="badge warning">${esc(answerLabel(result?.value ?? null, criterion, result?.status))}</span>`;
        if (changed) showError("appeal-error", "Оценка обновилась. Проверьте новое значение; ваш комментарий сохранён.");
      }
    }
    if (!draftDirty && latestChecklist()) {
      draft = structuredClone(latestChecklist());
      editorSelection = draft.criteria[0]?.id || "";
    }
  } catch (error) {
    if (version !== requestVersion || route().raw !== requestedRoute.raw) return;
    loadError = errorMessage(error);
    // Never present the previous page/filter as the result of a failed request.
    loadedRoute = "";
  }
  finally {
    if (version !== requestVersion || route().raw !== requestedRoute.raw) return;
    loading = false;
    if (resultsOnly && !loadError) {
      const results = document.getElementById("dialogue-results");
      if (results) results.innerHTML = dialogueResults(filters);
    } else render();
    const form = document.getElementById("resolve-form") as HTMLFormElement | null;
    if (savedForm && form && form.dataset.id === savedForm.id) {
      for (const [name, value] of savedForm.entries) {
        form.querySelectorAll<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(`[name="${name}"]`).forEach(input => {
          if (input instanceof HTMLInputElement && input.type === "radio") input.checked = input.value === value;
          else input.value = String(value);
        });
      }
      form.querySelector<HTMLInputElement>('input[name="decision"]:checked')?.dispatchEvent(new Event("change", {bubbles: true}));
    }
  }
}
export function validateChecklist(c: Checklist): string | null {
  if (!c.name.trim()) return "Введите название чек-листа.";
  if (!c.criteria.length) return "Добавьте хотя бы один критерий.";
  if (c.criteria.some((cr) => !cr.name.trim() || !cr.prompt.trim()))
    return "Заполните названия и формулировки всех критериев.";
  for (const cr of c.criteria) {
    if (
      !Number.isFinite(cr.weight) ||
      cr.weight < 0 ||
      (cr.type !== "flag" && cr.weight === 0)
    )
      return "Укажите положительный вес для каждого оцениваемого критерия.";
    if (cr.type === "flag" && (cr.weight !== 0 || cr.allowNA))
      return "Флаг нарушения должен иметь нулевой вес и не допускает N/A.";
    if (
      cr.steps.length < 2 ||
      cr.steps.some((v) => !Number.isFinite(v) || v < 0) ||
      !cr.steps.includes(0) ||
      new Set(cr.steps).size !== cr.steps.length ||
      cr.max <= 0
    )
      return `Проверьте ступени критерия «${cr.name}»: нужны уникальные неотрицательные числа, включая 0.`;
    if (
      cr.type !== "scale" &&
      (cr.steps.length !== 2 || !validValue(0, cr) || !validValue(1, cr))
    )
      return "Для бинарного ответа и флага нужны ступени 0 и 1.";
    if (cr.allowNA && !cr.naCondition.trim())
      return `Укажите условие N/A для критерия «${cr.name}».`;
    if (
      cr.type === "scale" &&
      cr.steps.some((step) => !cr.stepDescriptions[step]?.trim())
    )
      return `Добавьте описание каждой ступени критерия «${cr.name}».`;
  }
  const weight = c.criteria.reduce((sum, cr) => sum + cr.weight, 0);
  if (Math.abs(weight - 100) > 0.01)
    return `Сумма весов должна составлять 100%. Сейчас ${Number(weight.toFixed(1))}%.`;
  return null;
}
window.addEventListener("hashchange", () => {
  if (pendingForms.size || busy.size) {
    if (route().raw !== loadedRoute) location.hash = loadedRoute;
    return;
  }
  if (location.hash === "#main-content") {
    document.getElementById("main-content")?.focus();
    return;
  }
  currentPage = routePage();
  filters = {search: "", language: "all", channel: "all", status: new URLSearchParams(route().query).get("status") || "all"};
  if (route().section === "appeals") appealStatus = new URLSearchParams(route().query).get("status") || appealStatus;
  void refreshWorkspace();
  window.scrollTo({ top: 0 });
});
window.addEventListener("beforeunload", (event) => {
  if (draftDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
function routePage() {
  const value = Number(new URLSearchParams(route().query).get("page") || 1);
  return Number.isInteger(value) && value >= 1 && value <= 100000 ? value : 1;
}
currentPage = routePage();
filters.status = new URLSearchParams(route().query).get("status") || "all";
if (route().section === "appeals") appealStatus = new URLSearchParams(route().query).get("status") || "open";
const pendingEvaluation = storedEvaluationJob();
if (pendingEvaluation && Date.now() - pendingEvaluation.startedAt <= 330_000) startEvaluationRecovery(pendingEvaluation);
else if (pendingEvaluation) localStorage.removeItem(evaluationRecoveryKey);
void refreshWorkspace();
