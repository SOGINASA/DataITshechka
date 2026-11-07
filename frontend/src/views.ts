import type {
  Checklist,
  Conversation,
  Criterion,
  Evaluation,
} from "./types.js";
import { getState } from "./state.js";
import {
  answerLabel,
  finalValue,
  formatScore,
  normalized,
  score,
  scoreTone,
} from "./scoring.js";
import {
  conversationStatus,
  date,
  empty,
  esc,
  heading,
  href,
  icon,
  table,
  time,
  uploadButton,
  options,
} from "./ui.js";
export interface Filters {
  search: string;
  language: string;
  channel: string;
  status: string;
}
export function filterConversations(filters: Filters) {
  const { conversations, appeals } = getState();
  return conversations
    .filter((c) => {
      const evaluation = c.evaluations[c.evaluations.length - 1];
      const value = score(evaluation, appeals);
      return (
        `${c.id} ${c.title} ${c.operator}`
          .toLocaleLowerCase()
          .includes(filters.search.toLocaleLowerCase()) &&
        (filters.language === "all" || filters.language === c.language) &&
        (filters.channel === "all" || filters.channel === c.channel) &&
        (filters.status === "all" ||
          (filters.status === "pending" && !evaluation) ||
          (filters.status === "assessed" && !!evaluation) ||
          (filters.status === "attention" && value !== null && value < 80) ||
          (filters.status === "appeal" &&
            appeals.some(
              (a) => a.conversationId === c.id && a.status === "open",
            )))
      );
    })
    .sort((a, b) => new Date(b.date).valueOf() - new Date(a.date).valueOf());
}
export function dialogueResults(filters: Filters) {
  const filtered = filterConversations(filters);
  const active =
    filters.search ||
    Object.entries(filters).some(
      ([key, value]) => key !== "search" && value !== "all",
    );
  return `<div class="results-line"><span>Найдено диалогов: <strong>${filtered.length}</strong></span>${active ? '<button class="text-button" data-action="reset-filters">Сбросить фильтры</button>' : ""}</div>${filtered.length ? table(filtered) : empty("Ничего не найдено", "Попробуйте другую тему или измените фильтры.", '<button class="button secondary" data-action="reset-filters">Сбросить фильтры</button>')}`;
}
export function dialoguesView(filters: Filters) {
  return (
    heading(
      "КОНТРОЛЬ КАЧЕСТВА",
      "Диалоги",
      "Весь контекст разговора. Каждая оценка — с обоснованием.",
      uploadButton(),
    ) +
    `<section class="panel"><div class="filters"><label class="search-field">${icon("search")}<input id="search" placeholder="Поиск по теме, оператору или ID" aria-label="Поиск диалогов" value="${esc(filters.search)}"></label><div class="filter-controls">${icon("filter", 16)}<label class="sr-only" for="language-filter">Язык</label><select id="language-filter" data-filter="language">${options(
      [
        ["all", "Все языки"],
        ["RU", "Русский"],
        ["KZ", "Казахский"],
        ["EN", "Английский"],
      ],
      filters.language,
    )}</select><label class="sr-only" for="channel-filter">Канал</label><select id="channel-filter" data-filter="channel">${options(
      [
        ["all", "Все каналы"],
        ["agent chat", "Чаты"],
        ["voice call", "Звонки"],
      ],
      filters.channel,
    )}</select><label class="sr-only" for="status-filter">Статус оценки</label><select id="status-filter" data-filter="status">${options(
      [
        ["all", "Все статусы"],
        ["assessed", "Оценены"],
        ["pending", "Не оценены"],
        ["attention", "Нужна проверка"],
        ["appeal", "Апелляции"],
      ],
      filters.status,
    )}</select></div></div><div id="dialogue-results">${dialogueResults(filters)}</div></section>`
  );
}
export { detailView } from "./review.js";
export { checklistView, editorCriterion } from "./editor.js";
export { appealsView } from "./appeals.js";
