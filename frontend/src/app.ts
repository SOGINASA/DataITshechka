import type { Checklist, Criterion, Evaluation } from "./types.js";
import {
  addConversations,
  evaluate,
  getState,
  getPersistenceWarning,
  resolveAppeal,
  saveChecklist,
  submitAppeal,
} from "./state.js";
import { answerLabel, validValue } from "./scoring.js";
import { importExample, parseImport } from "./import.js";
import { empty, esc, href, icon } from "./ui.js";
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
let draft: Checklist = structuredClone(latestChecklist());
let draftDirty = false;
let filters: Filters = {
  search: "",
  language: "all",
  channel: "all",
  status: "all",
};
let appealStatus = "open";
let selectedEvaluation = "";
let lastRoute = "";
let toastTimer: ReturnType<typeof setTimeout>;
let modalTrigger: HTMLElement | null = null;
let appealTarget: {
  conversationId: string;
  evaluation: Evaluation;
  criterion: Criterion;
} | null = null;
let switchTarget = "";
const busy = new Set<string>();
const navItems = [
  { id: "overview", label: "Обзор", icon: "dashboard" },
  { id: "dialogues", label: "Диалоги", icon: "chat" },
  { id: "checklists", label: "Чек-листы", icon: "checklist" },
  { id: "appeals", label: "Апелляции", icon: "scale" },
];
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
  const pending = getState().appeals.filter((a) => a.status === "open").length;
  return `<a href="#/overview" class="brand"><img src="./assets/brand/freedom-logo.svg" alt="Freedom"><span class="brand-subtitle">CONVERSATION QUALITY</span></a><div class="workspace-label"><span class="workspace-icon">${icon("book", 16)}</span><div><strong>Контроль качества</strong><span>Рабочее пространство</span></div></div><div class="nav-heading">РАБОЧАЯ ОБЛАСТЬ</div><nav aria-label="Основная навигация">${navItems.map((item) => `<a href="#/${item.id}" class="nav-item ${section === item.id ? "active" : ""}"${section === item.id ? ' aria-current="page"' : ""}>${icon(item.icon, 19)}<span>${item.label}</span>${item.id === "appeals" && pending ? `<span class="nav-badge">${pending}</span>` : ""}${section === item.id ? '<span class="nav-indicator"></span>' : ""}</a>`).join("")}</nav><div class="sidebar-bottom"><button class="help-link" data-action="help">${icon("help")}Как это работает${icon("external", 15)}</button><div class="demo-workspace"><span class="demo-avatar">CQ</span><div><strong>Демо-пространство</strong><span><i class="tiny-dot"></i>Локальные данные</span></div></div></div>`;
}
function render() {
  const r = route();
  const { conversations } = getState();
  if (r.raw !== lastRoute) {
    selectedEvaluation = "";
    filters = {
      search: "",
      language: "all",
      channel: "all",
      status: new URLSearchParams(r.query).get("status") || "all",
    };
    if (r.section === "appeals" && r.id) {
      const a = getState().appeals.find((a) => a.id === r.id);
      if (a) appealStatus = a.status;
    }
  }
  let content = "";
  if (r.section === "dialogues" && r.id) {
    const c = conversations.find((c) => c.id === r.id);
    content = c
      ? detailView(c, selectedEvaluation)
      : empty(
          "Диалог не найден",
          "Откройте диалог из рабочего пространства.",
          '<a class="button secondary" href="#/dialogues">К диалогам</a>',
        );
  } else if (r.section === "dialogues") content = dialoguesView(filters);
  else if (r.section === "checklists")
    content = checklistView(draft, draftDirty);
  else if (r.section === "appeals") content = appealsView(appealStatus, r.id);
  else content = overviewView();
  app.innerHTML = `<div class="app-shell"><aside class="sidebar">${nav(r.section)}</aside><div class="app-main"><header class="topbar"><div class="breadcrumb"><button class="icon-button mobile-menu-button" aria-label="Открыть навигацию" data-action="menu">${icon("menu", 20)}</button><span class="desktop-only">${icon("sidebar", 17)}</span><span class="breadcrumb-divider desktop-only"></span><span>CQA</span>${icon("chevron", 13)}<span>${navItems.find((n) => n.id === r.section)?.label || "Обзор"}</span>${r.id ? `${icon("chevron", 13)}<strong>${r.section === "appeals" ? "Рассмотрение" : "Карточка диалога"}</strong>` : ""}</div><div class="topbar-right"><span class="demo-pill"><i></i>Демо-данные</span><span class="topbar-date">7 ноября 2026</span></div></header><main id="main-content" class="main-content" tabindex="-1">${getPersistenceWarning() ? `<div class="notice-box storage-warning" role="alert">${icon("alert", 18)}${esc(getPersistenceWarning())}</div>` : ""}${content}</main><footer class="app-footer"><span>Freedom · Conversation Quality Analytics</span><span>С вниманием к каждому диалогу</span></footer></div></div>`;
  document.title = `${navItems.find((n) => n.id === r.section)?.label || "Обзор"} · Freedom CQA`;
  if (busy.has(r.id)) setEvaluationBusy(r.id);
  lastRoute = r.raw;
}
function notify(message: string) {
  if (getPersistenceWarning())
    message =
      "Изменения применены в этой вкладке, но сохранить их в браузере не удалось. Подробности — в предупреждении на странице.";
  const toast = document.querySelector<HTMLDivElement>("#toast")!;
  clearTimeout(toastTimer);
  toast.innerHTML = `${icon("check", 18)}<span>${esc(message)}</span><button data-action="close-toast" aria-label="Закрыть уведомление">${icon("close", 15)}</button>`;
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
  openModal(
    "Загрузить диалоги",
    "Добавьте транскрипты в рабочее пространство для оценки.",
    `<form id="upload-form"><input type="file" id="json-file" accept=".json,application/json" hidden aria-label="JSON-файл с диалогами"><button class="upload-zone" type="button" data-action="choose-file"><span class="upload-icon">${icon("file", 26)}</span><strong id="upload-filename">Выберите JSON-файл</strong><span>Массив диалогов или ответ API · до 5 МБ</span><span class="button secondary small">${icon("upload", 15)}Выбрать файл</span></button><div class="field"><div class="field-heading"><label for="json-input">Или вставьте JSON</label><button type="button" class="text-button" data-action="import-example">Вставить пример</button></div><textarea id="json-input" class="code-input" rows="7" required placeholder='[ { "conversation_id": "…", "transcript": […] } ]'></textarea></div><p id="import-error" class="form-error" role="alert" hidden></p><div class="modal-footer"><span class="muted">Данные сохраняются в этом браузере.</span><button type="submit" class="button primary">Добавить диалоги${icon("arrow", 16)}</button></div></form>`,
    true,
  );
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
    const details = target.closest("details")!;
    const index = draft.criteria.findIndex((x) => x.id === c.id);
    details.outerHTML = editorCriterion(c, index).replace(
      "<details ",
      "<details open ",
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
  if (target.id === "search") {
    filters.search = target.value;
    document.getElementById("dialogue-results")!.innerHTML =
      dialogueResults(filters);
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
    document.getElementById("dialogue-results")!.innerHTML =
      dialogueResults(filters);
  }
  if (target.id === "evaluation-history") {
    selectedEvaluation = target.value;
    render();
  }
  if (target.name === "decision")
    document.getElementById("new-value-field")!.hidden =
      target.value !== "change";
  if (target.id === "json-file") {
    const file = target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      showError("import-error", "Размер файла должен быть не больше 5 МБ.");
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
  if (link && modal.open && modal.classList.contains("navigation-modal"))
    closeModal();
  if (!control) return;
  const action = control.dataset.action;
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
      `<ol class="help-steps"><li><span>01</span><div><h3>Выберите диалог</h3><p>Откройте разговор из списка или загрузите транскрипты в JSON.</p></div></li><li><span>02</span><div><h3>Проверьте оценку</h3><p>Выберите чек-лист. Откройте обоснование и перейдите к реплике-доказательству.</p></div></li><li><span>03</span><div><h3>Примите решение</h3><p>Оспорьте критерий, рассмотрите апелляцию и сохраните финальный результат.</p></div></li></ol><div class="notice-box">Сейчас это фронтенд с мок-данными. Оценки моделируются локально; AI-анализ не подключён. Начальные правила соответствуют чек-листу кейса. Изменения сохраняются в этом браузере.</div><div class="modal-footer"><button class="button primary" data-action="close-modal">Всё понятно</button></div>`,
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
    render();
  }
  if (action === "detail-tab") detailTab(control.dataset.tab!);
  if (action === "evidence") {
    detailTab("transcript");
    document
      .querySelectorAll(".message.highlighted")
      .forEach((el) => el.classList.remove("highlighted"));
    const index = Number(control.dataset.index);
    const message = document.getElementById(`message-${index}`);
    message?.classList.add("highlighted");
    message?.focus({ preventScroll: true });
    requestAnimationFrame(() =>
      message?.scrollIntoView({
        behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "center",
      }),
    );
    const c = getState().conversations.find((c) => c.id === route().id);
    const audio = document.getElementById(
      "conversation-audio",
    ) as HTMLAudioElement | null;
    if (audio && c && Number.isFinite(audio.duration)) {
      const first = new Date(c.transcript[0].timestamp).valueOf();
      const selected = new Date(c.transcript[index].timestamp).valueOf();
      if (Number.isFinite(first) && Number.isFinite(selected))
        audio.currentTime = Math.max(
          0,
          Math.min(audio.duration, (selected - first) / 1000),
        );
    }
  }
  if (action === "evaluate") {
    const id = control.dataset.id!;
    if (busy.has(id)) return;
    const checklistId = (
      document.getElementById("evaluation-checklist") as HTMLSelectElement
    ).value;
    busy.add(id);
    setEvaluationBusy(id);
    await new Promise((resolve) => setTimeout(resolve, 850));
    const evaluation = evaluate(id, checklistId);
    busy.delete(id);
    selectedEvaluation = evaluation?.id || "";
    render();
    notify("Демонстрационная оценка готова");
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
      `<form id="appeal-form"><div class="appeal-criterion"><span class="eyebrow">СПОРНЫЙ КРИТЕРИЙ</span><h3>${esc(criterion.name)}</h3><span class="badge warning">${esc(answerLabel(value, criterion))}</span></div><div class="field"><label for="appeal-comment">Комментарий к апелляции</label><textarea id="appeal-comment" name="comment" rows="5" required maxlength="2000" placeholder="Что нужно учесть проверяющему? Укажите фрагмент или контекст разговора."></textarea></div><p id="appeal-error" class="form-error" role="alert" hidden></p><div class="modal-footer"><button type="button" class="button secondary" data-action="close-modal">Отмена</button><button type="submit" class="button primary">Отправить апелляцию${icon("external", 15)}</button></div></form>`,
    );
  }
  if (action === "appeal-filter") {
    appealStatus = control.dataset.status!;
    if (route().id) {
      location.hash = "/appeals";
    } else render();
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
    document
      .querySelector(".criteria-editor-list")!
      .insertAdjacentHTML(
        "beforeend",
        editorCriterion(c, draft.criteria.length - 1),
      );
    updateDraftUI();
    document.getElementById(`name-${c.id}`)?.focus();
  }
  if (action === "delete-criterion") {
    draft.criteria = draft.criteria.filter((c) => c.id !== control.dataset.id);
    control.closest("details")?.remove();
    draftDirty = true;
    updateDraftUI();
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target as HTMLFormElement;
  if (
    !["upload-form", "appeal-form", "resolve-form", "checklist-form"].includes(
      form.id,
    )
  )
    return;
  event.preventDefault();
  if (form.id === "upload-form") {
    try {
      const records = parseImport(
        (document.getElementById("json-input") as HTMLTextAreaElement).value,
      );
      const count = addConversations(records);
      if (!count) {
        showError(
          "import-error",
          "Диалоги с этими ID уже есть в рабочем пространстве.",
        );
        return;
      }
      closeModal();
      location.hash = "/dialogues";
      render();
      notify(
        `Добавлено диалогов: ${count}${count < records.length ? `. Дубликаты пропущены: ${records.length - count}` : ""}`,
      );
    } catch (e) {
      showError("import-error", (e as Error).message);
    }
  }
  if (form.id === "appeal-form" && appealTarget) {
    const comment = (new FormData(form).get("comment") as string).trim();
    if (!comment) {
      showError("appeal-error", "Добавьте комментарий к апелляции.");
      return;
    }
    const a = submitAppeal({
      conversationId: appealTarget.conversationId,
      evaluationId: appealTarget.evaluation.id,
      criterionId: appealTarget.criterion.id,
      originalValue:
        appealTarget.evaluation.results.find(
          (r) => r.criterionId === appealTarget!.criterion.id,
        )?.value ?? null,
      comment,
    });
    closeModal();
    render();
    notify(
      a
        ? "Апелляция отправлена на рассмотрение"
        : "Апелляция по этому критерию уже существует",
    );
  }
  if (form.id === "resolve-form") {
    const data = new FormData(form);
    const decision = data.get("decision") === "change" ? "change" : "confirm";
    const value = data.get("value") === "na" ? null : Number(data.get("value"));
    const reason = String(data.get("reason") || "").trim();
    if (!reason) {
      showError("review-error", "Обоснуйте решение.");
      return;
    }
    if (!resolveAppeal(form.dataset.id!, decision, value, reason)) {
      showError(
        "review-error",
        "Выберите допустимую ступень шкалы и добавьте обоснование.",
      );
      return;
    }
    appealStatus = "resolved";
    render();
    notify("Решение сохранено. Итоговая оценка пересчитана.");
  }
  if (form.id === "checklist-form") {
    const problem = validateChecklist(draft);
    if (problem) {
      showError("checklist-error", problem);
      return;
    }
    draft = structuredClone(saveChecklist(draft));
    draftDirty = false;
    render();
    notify(`Чек-лист сохранён · версия ${draft.version}`);
  }
});
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
  if (location.hash === "#main-content") {
    document.getElementById("main-content")?.focus();
    return;
  }
  render();
  window.scrollTo({ top: 0 });
});
window.addEventListener("beforeunload", (event) => {
  if (draftDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
render();
