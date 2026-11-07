import type { Conversation, Criterion } from "./types.js";
import { getState } from "./state.js";
import { score, scoreTone, formatScore, isAssessed } from "./scoring.js";
export const esc = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
export const href = (kind: string, id = "") =>
  `#/${kind}${id ? "/" + encodeURIComponent(id) : ""}`;
const paths: Record<string, string> = {
  play: '<path d="m8 4 12 8-12 8V4Z"/>',
  pause: '<path d="M8 4v16M16 4v16"/>',
  dashboard:
    '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z"/>',
  checklist:
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 8 1 1 2-2m-3 7 1 1 2-2m3-5h3m-3 6h3"/>',
  scale: '<path d="M12 3v17m-5 1h10M4 7h16M6 7l-4 7h8L6 7Zm12 0-4 7h8l-4-7Z"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  external: '<path d="M7 17 17 7M7 7h10v10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  back: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  filter: '<path d="M4 6h16M7 12h10m-7 6h4"/>',
  phone:
    '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.7A2 2 0 0 1 4.2 2h3a2 2 0 0 1 2 1.7c.1 1 .4 2 .7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.5c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2.1Z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18"/>',
  shield:
    '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6m0 4h.01"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3m.1 4h.01"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Z"/><path d="M14 2v6h6m-11 4-2 3 2 3m6-6 2 3-2 3"/>',
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
  save: '<path d="m19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2ZM7 3v6h10V3M7 21v-8h10v8"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  headphones:
    '<path d="M3 14v-3a9 9 0 0 1 18 0v3M3 13h4v8H4a1 1 0 0 1-1-1v-7Zm18 0h-4v8h3a1 1 0 0 0 1-1v-7Z"/>',
  spark:
    '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/>',
  corner: '<path d="M5 4v8h14m-5-5 5 5-5 5"/>',
  quote: '<path d="M4 12h5v7H2v-7c0-5 3-7 7-7M17 12h5v7h-7v-7c0-5 3-7 7-7"/>',
  sidebar:
    '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18m8-14-3 5 3 5"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
};
export function icon(name: string, size = 18, className = "") {
  return `<svg class="icon ${esc(className)}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.chat}</svg>`;
}
export function date(value: string, short = false) {
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? "—"
    : new Intl.DateTimeFormat("ru-RU", {
        day: "numeric",
        month: "short",
        ...(short ? {} : { hour: "2-digit", minute: "2-digit" }),
        timeZone: "Asia/Almaty",
      }).format(d);
}
export function time(value: string) {
  if (!value.includes("T")) return value;
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? value
    : new Intl.DateTimeFormat("ru-RU", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "Asia/Almaty",
      }).format(d);
}
export function scoreBadge(value: number | null) {
  return `<span class="score-value ${scoreTone(value)}"><strong>${formatScore(value)}</strong>${value !== null ? `<span class="score-track"><i style="width:${Math.max(0, Math.min(value, 100))}%"></i></span>` : ""}</span>`;
}
export function conversationStatus(c: Conversation) {
  const { appeals } = getState();
  const evaluation = c.evaluations[c.evaluations.length - 1];
  if (c.summary?.openAppeals || appeals.some((a) => a.conversationId === c.id && a.status === "open"))
    return '<span class="badge warning"><i class="status-dot"></i>Апелляция</span>';
  if (!evaluation && !c.summary?.evaluationId)
    return '<span class="badge neutral"><i class="status-dot"></i>Не оценён</span>';
  if (!(c.summary ? c.summary.assessed : isAssessed(evaluation)))
    return '<span class="badge warning"><i class="status-dot"></i>Оценка не завершена</span>';
  const value = c.summary ? c.summary.score : score(evaluation, appeals);
  return `<span class="badge ${scoreTone(value)}"><i class="status-dot"></i>${value !== null && value < 80 ? "Нужна проверка" : "Оценён"}</span>`;
}
export function table(conversations: Conversation[]) {
  return `<p class="table-scroll-hint">${icon("arrow", 14)}<span>Прокрутите таблицу, чтобы увидеть оценки и статусы</span></p><div class="table-wrap"><table class="dialogue-table"><thead><tr><th>Диалог</th><th>Оператор</th><th>Канал / язык</th><th>Оценка</th><th>Статус</th><th><span class="sr-only">Открыть</span></th></tr></thead><tbody>${conversations
    .map(
      (c) =>
        `<tr><td><a href="${href("dialogues", c.id)}" class="conversation-link"><span class="channel-box">${icon(c.channel === "voice call" ? "phone" : "chat")}</span><span><strong>${esc(c.title)}</strong><small>${esc(c.id)} <span>·</span> ${esc(date(c.date, true))}</small></span></a></td><td><span class="person"><span class="avatar tone-${c.operator.length % 3}">${esc(
          c.operator
            .split(" ")
            .map((n) => n[0])
            .slice(0, 2)
            .join(""),
        )}</span><span>${esc(c.operator)}</span></span></td><td><span class="channel-label">${c.channel === "voice call" ? "Звонок" : "Чат"}<span class="language">${esc(c.language)}</span></span></td><td>${scoreBadge(c.summary ? c.summary.score : score(c.evaluations[c.evaluations.length - 1], getState().appeals))}</td><td>${conversationStatus(c)}</td><td><a href="${href("dialogues", c.id)}" class="icon-button row-link" aria-label="Открыть диалог ${esc(c.id)}">${icon("external", 17)}</a></td></tr>`,
    )
    .join("")}</tbody></table></div>`;
}
export function empty(title: string, text: string, action = "") {
  return `<div class="empty-state">${icon("search", 32)}<h3>${esc(title)}</h3><p>${esc(text)}</p>${action}</div>`;
}
export function heading(
  _eyebrow: string,
  title: string,
  _text: string,
  action = "",
) {
  return `<div class="page-heading"><h1 class="page-title">${title === "Диалоги" ? brandArt("dialogues") : ""}${esc(title)}</h1>${action}</div>`;
}
export function brandArt(kind: "dialogues" | "checklist" | "appeals") {
  return `<img class="brand-art" src="./assets/media/freedom-${kind}.png" width="64" height="64" alt="" aria-hidden="true" decoding="async">`;
}
export const uploadButton = () =>
  `<button class="button primary" data-action="upload">${icon("plus")}Загрузить диалоги</button>`;
export function field(label: string, id: string, control: string) {
  return `<div class="field"><label for="${esc(id)}">${esc(label)}</label>${control}</div>`;
}

export function options(values: [string, string][], value: string) {
  return values
    .map(
      ([key, label]) =>
        `<option value="${esc(key)}"${key === value ? " selected" : ""}>${esc(label)}</option>`,
    )
    .join("");
}
export function valueOptions(criterion: Criterion, value: number | null) {
  return (
    criterion.steps
      .map(
        (step) =>
          `<option value="${step}"${value === step ? " selected" : ""}>${esc(criterion.type === "scale" ? String(step) + " / " + criterion.max : step === 1 ? "Да" : "Нет")}${criterion.stepDescriptions[step] ? " — " + esc(criterion.stepDescriptions[step]) : ""}</option>`,
      )
      .join("") +
    (criterion.allowNA
      ? `<option value="na"${value === null ? " selected" : ""}>N/A — не применяется</option>`
      : "")
  );
}

export function paginationControls(action: string) {
  const {pagination: p} = getState();
  if (p.pages <= 1) return "";
  return `<nav class="results-line" aria-label="Страницы списка"><button class="button secondary small" data-action="${action}" data-page="${p.page - 1}"${p.page <= 1 ? " disabled" : ""}>Назад</button><span>Страница ${p.page} из ${p.pages}</span><button class="button secondary small" data-action="${action}" data-page="${p.page + 1}"${p.page >= p.pages ? " disabled" : ""}>Далее</button></nav>`;
}
