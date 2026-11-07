import { getState } from "./state.js";
import { empty, esc, heading, icon, table, uploadButton, options, paginationControls } from "./ui.js";
export interface Filters {
  search: string;
  language: string;
  channel: string;
  status: string;
}
export function dialogueResults(filters: Filters) {
  const {conversations: filtered, pagination} = getState();
  const active =
    filters.search ||
    Object.entries(filters).some(
      ([key, value]) => key !== "search" && value !== "all",
    );
  return `<div class="results-line"><span>Найдено диалогов: <strong>${pagination.total}</strong></span>${active ? '<button class="text-button" data-action="reset-filters">Сбросить фильтры</button>' : ""}</div>${filtered.length ? table(filtered) + paginationControls("dialogue-page") : empty("Ничего не найдено", "Попробуйте другую тему или измените фильтры.", '<button class="button secondary" data-action="reset-filters">Сбросить фильтры</button>')}`;
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
