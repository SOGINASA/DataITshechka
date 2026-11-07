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
          `<option value="${step}" ${value === step ? "selected" : ""}>${esc(answerLabel(step, criterion))}${criterion.stepDescriptions[step] ? " — " + esc(criterion.stepDescriptions[step]) : ""}</option>`,
      )
      .join("") +
    (criterion.allowNA
      ? `<option value="na"${value === null ? " selected" : ""}>N/A — не применяется</option>`
      : "")
  );
}
export function detailView(c: Conversation, evaluationId = "") {
  const { checklists, appeals } = getState();
  const evaluation =
    c.evaluations.find((e) => e.id === evaluationId) ||
    c.evaluations[c.evaluations.length - 1];
  const total = score(evaluation, appeals);
  const changed =
    evaluation &&
    appeals.some(
      (a) => a.evaluationId === evaluation.id && a.status === "resolved",
    );
  return `<a href="#/dialogues" class="back-link">${icon("back", 16)}Все диалоги</a><div class="page-heading detail-heading"><div><h1>${esc(c.title)}</h1><div class="detail-meta"><span>${icon(c.channel === "voice call" ? "phone" : "chat", 15)}${c.channel === "voice call" ? "Звонок" : "Чат"} · ${esc(c.language)}</span><span>${esc(c.id)}</span><span>${esc(date(c.date))}</span>${conversationStatus(c)}</div></div></div><div class="evaluation-toolbar"><div><span class="operator-label">Оператор</span><strong>${esc(c.operator)}</strong></div><div class="evaluation-controls"><label for="evaluation-checklist" class="sr-only">Чек-лист для оценки</label><select id="evaluation-checklist">${[
    ...checklists,
  ]
    .reverse()
    .map(
      (list) =>
        `<option value="${esc(list.id)}">${esc(list.name)} · v${list.version}</option>`,
    )
    .join(
      "",
    )}</select><button class="button primary" data-action="evaluate" data-id="${esc(c.id)}">${icon("spark", 17)}${evaluation ? "Оценить повторно" : "Оценить диалог"}</button></div></div><p class="simulation-note">Демо-оценка · Смысловой AI-анализ ещё не подключён. Повторный запуск создаёт новую версию результата.</p>${c.channel === "voice call" ? `<section class="audio-strip"><span class="audio-icon">${icon("headphones", 21)}</span><div><strong>Запись разговора</strong><span>${c.audioUrl ? "Аудио и транскрипт в одном месте" : "Запись в демонаборе недоступна. Используйте транскрипт."}</span></div>${c.audioUrl ? `<audio id="conversation-audio" controls preload="none" src="${esc(c.audioUrl)}"></audio>` : `<span class="duration">${icon("clock", 15)}${esc(c.duration)}</span>`}</section>` : ""}<div class="mobile-detail-tabs segmented"><button data-action="detail-tab" data-tab="transcript" aria-pressed="false">Транскрипт</button><button data-action="detail-tab" data-tab="evaluation" class="active" aria-pressed="true">Оценка качества</button></div><div id="detail-grid" class="detail-grid mobile-show-evaluation"><section class="panel transcript-panel"><div class="panel-heading"><div class="heading-inline">${icon("chat")}<h2>Транскрипт</h2></div><span class="muted">${c.transcript.length} реплик</span></div><div class="transcript-messages">${c.transcript.map((m, i) => `<article id="message-${i}" tabindex="-1" class="message ${m.speaker}"><div class="message-meta"><strong>${esc(m.speaker === "operator" ? c.operator : m.speaker === "client" ? "Клиент" : m.speaker === "bot" ? "Бот" : "Система")}</strong><time>${esc(time(m.timestamp))}</time></div><p>${esc(m.text)}</p></article>`).join("")}</div><div class="transcript-footer"><i class="tiny-dot"></i>Исходные реплики и метки времени сохранены</div></section><section class="panel evaluation-panel"><div class="panel-heading"><div class="heading-inline">${icon("checklist")}<h2>Оценка качества</h2></div>${
    c.evaluations.length > 1
      ? `<label class="sr-only" for="evaluation-history">Версия оценки</label><select id="evaluation-history" class="small-select">${[
          ...c.evaluations,
        ]
          .reverse()
          .map(
            (e, i) =>
              `<option value="${esc(e.id)}"${e.id === evaluation?.id ? " selected" : ""}>Оценка ${c.evaluations.length - i}</option>`,
          )
          .join("")}</select>`
      : ""
  }</div>${evaluation ? `<div class="evaluation-summary"><div class="score-ring ${scoreTone(total)}" style="--score:${(total ?? 0) * 3.6}deg"><div><strong>${formatScore(total)}</strong><span>из 100</span></div></div><div><span class="quality-label ${scoreTone(total)}">${total === null ? "Нет применимых критериев" : total >= 85 ? "Хорошее качество" : total >= 70 ? "Есть точки роста" : "Требует внимания"}</span><p>${esc(evaluation.checklist.name)}<br><span>Версия ${evaluation.checklist.version} · ${evaluation.results.length} критериев</span></p>${changed ? `<span class="revised-score">Исходная оценка: ${formatScore(score(evaluation, [], true))}</span>` : ""}</div></div>${criteriaResults(c, evaluation)}<div class="evaluation-footnote">Итог учитывает веса и исключает N/A. Грубые ошибки отмечаются отдельно и не обнуляют результат.</div>` : empty("Диалог готов к оценке", "Выберите чек-лист и запустите демонстрационную оценку.", `<button class="button primary" data-action="evaluate" data-id="${esc(c.id)}">Оценить диалог</button>`)}</section></div>`;
}
function criteriaResults(c: Conversation, e: Evaluation) {
  const { appeals } = getState();
  const totalWeight = e.checklist.criteria.reduce(
    (sum, cr) =>
      sum +
      (cr.type !== "flag" && finalValue(e, cr.id, appeals) !== null
        ? cr.weight
        : 0),
    0,
  );
  const sections = [
    ...new Set(e.checklist.criteria.map((cr) => cr.section || "Критерии")),
  ];
  return `<div class="criterion-list">${sections
    .map((section) => {
      const criteria = e.checklist.criteria.filter(
        (cr) => (cr.section || "Критерии") === section,
      );
      const contribution = criteria.reduce((sum, cr) => {
        const value = finalValue(e, cr.id, appeals);
        return (
          sum +
          (cr.type !== "flag" && value !== null && totalWeight
            ? ((normalized(value, cr) * cr.weight) / totalWeight) * 100
            : 0)
        );
      }, 0);
      return `<div class="result-section-heading"><span>${esc(section)}</span>${criteria.some((cr) => cr.type !== "flag") ? `<small>${formatScore(contribution)} · вклад в итог</small>` : ""}</div>${criteria
        .map((cr) => {
          const result = e.results.find((r) => r.criterionId === cr.id);
          if (!result) return "";
          const value = finalValue(e, cr.id, appeals);
          const appeal = appeals.find(
            (a) => a.evaluationId === e.id && a.criterionId === cr.id,
          );
          const missed =
            value !== null &&
            (cr.type === "flag" ? value === 1 : normalized(value, cr) < 1);
          return `<details class="criterion ${missed ? "criterion-warning" : ""}"${cr.id === "identity" ? " open" : ""}><summary><span class="criterion-icon ${value === null ? "neutral" : missed ? "warning" : "success"}">${value === null ? "—" : missed ? "!" : icon("check", 13)}</span><span class="criterion-name">${esc(cr.name)}<small>${cr.type === "flag" ? "Без баллов · флаг нарушения" : "Вес " + cr.weight + "%"}${appeal ? (appeal.status === "resolved" ? " · Пересмотрено" : " · Апелляция") : ""}</small></span><strong class="criterion-answer ${missed ? "text-warning" : ""}">${esc(answerLabel(value, cr))}</strong>${icon("down", 15, "criterion-chevron")}</summary><div class="criterion-body"><p>${esc(result.explanation)}</p>${value === null ? `<div class="na-note">Условие N/A: ${esc(cr.naCondition)} Вес перераспределён между применимыми критериями.</div>` : ""}${result.evidence.map((i) => (c.transcript[i] ? `<button class="evidence-link" data-action="evidence" data-index="${i}">${icon("corner", 15)}<span>${esc(time(c.transcript[i].timestamp))} · Перейти к реплике</span>${icon("external", 14)}</button>` : "")).join("")}${appeal?.status === "resolved" ? `<div class="decision-inline"><strong>Решение проверяющего</strong><p>${esc(appeal.reason)}</p><span>${esc(answerLabel(appeal.originalValue, cr))} → ${esc(answerLabel(value, cr))}</span></div>` : ""}<div class="criterion-actions"><span>${cr.type === "flag" ? "На балл не влияет" : value === null ? "Не применяется" : formatScore(normalized(value, cr) * cr.weight) + " из " + cr.weight + " базовых баллов до N/A"}</span>${appeal ? `<a class="text-link" href="${href("appeals", appeal.id)}">${appeal.status === "open" ? "На рассмотрении" : "Решение"}${icon("external", 13)}</a>` : `<button class="text-button" data-action="appeal" data-evaluation="${esc(e.id)}" data-criterion="${esc(cr.id)}">${icon("scale", 14)}Оспорить</button>`}</div></div></details>`;
        })
        .join("")}`;
    })
    .join("")}</div>`;
}
export function checklistView(draft: Checklist, dirty: boolean) {
  const { checklists } = getState();
  return (
    heading(
      "НАСТРОЙКА ОЦЕНКИ",
      "Чек-листы",
      "Единые стандарты. Прозрачные критерии. Понятный результат.",
      `<span class="badge neutral">${icon("checklist", 14)}${checklists.length} версий</span>`,
    ) +
    `<div class="checklist-layout"><aside class="checklist-sidebar"><div class="section-kicker">СОХРАНЁННЫЕ ВЕРСИИ</div>${[
      ...checklists,
    ]
      .reverse()
      .map(
        (c) =>
          `<button class="checklist-version ${draft.id === c.id ? "selected" : ""}" data-action="checklist-version" data-id="${esc(c.id)}"><span class="version-icon">${icon("checklist", 19)}</span><span><strong>${esc(c.name)}</strong><small>Версия ${c.version} · ${c.criteria.length} критериев</small><small>${esc(date(c.createdAt, true))}</small></span>${draft.id === c.id ? icon("check", 15) : ""}</button>`,
      )
      .join(
        "",
      )}<div class="sidebar-explanation">${icon("copy")}<p>Изменения сохраняются новой версией. Уже выставленные оценки сохраняют свой чек-лист.</p></div></aside><form id="checklist-form" class="panel checklist-editor"><div class="panel-heading"><div><h2>Редактор чек-листа</h2><p id="draft-status">Версия ${draft.version} · ${dirty ? "Есть изменения" : "Сохранено"}</p></div><span class="badge sage">${draft.version === 1 ? "Чек-лист кейса" : "Настроенная версия"}</span></div><div class="checklist-intro"><div class="field"><label for="checklist-name">Название</label><input id="checklist-name" value="${esc(draft.name)}" maxlength="80" required></div><p class="muted">Начальная версия соответствует чек-листу организаторов. Меняйте правила через настройки — новая версия доступна для следующей оценки.</p></div><div class="criteria-editor-list">${draft.criteria.map((c, i) => editorCriterion(c, i)).join("")}</div><button type="button" class="add-criterion" data-action="add-criterion">${icon("plus", 17)}Добавить критерий</button><p id="checklist-error" class="form-error editor-error" role="alert" hidden></p><div class="editor-savebar"><div><span>Сумма весов</span><strong id="weight-total" class="text-success">${draft.criteria.reduce((sum, cr) => sum + cr.weight, 0)}% <small>/ 100%</small></strong></div><button id="save-checklist" type="submit" class="button primary"${dirty ? "" : " disabled"}>${icon("save", 16)}Сохранить новую версию</button></div></form></div>`
  );
}
export function editorCriterion(c: Criterion, i: number) {
  const id = esc(c.id);
  return `<details class="editor-criterion" data-criterion="${id}"${i === 0 || c.name === "Новый критерий" ? " open" : ""}><summary><span class="criterion-index">${String(i + 1).padStart(2, "0")}</span><span><strong data-title="${id}">${esc(c.name || "Без названия")}</strong><small data-summary="${id}">${c.type === "scale" ? "Шкала " + c.steps.join(" / ") : c.type === "flag" ? "Флаг нарушения · без баллов" : "Да / Нет"}${c.allowNA ? " · Допускается N/A" : ""}</small></span><span class="criterion-weight" data-weight="${id}">${c.weight}%</span>${icon("down", 17)}</summary><div class="editor-fields"><div class="field"><label for="name-${id}">Название критерия</label><input id="name-${id}" data-field="name" data-id="${id}" value="${esc(c.name)}" maxlength="100" required></div><div class="field"><label for="section-${id}">Секция</label><input id="section-${id}" data-field="section" data-id="${id}" value="${esc(c.section)}" maxlength="80"></div><div class="field"><label for="prompt-${id}">Что проверяем</label><textarea id="prompt-${id}" data-field="prompt" data-id="${id}" rows="2" maxlength="1500" required>${esc(c.prompt)}</textarea></div><div class="editor-field-row"><div class="field"><label for="type-${id}">Тип ответа</label><select id="type-${id}" data-field="type" data-id="${id}">${options(
    [
      ["binary", "Да / Нет"],
      ["scale", "Числовая шкала"],
      ["flag", "Флаг нарушения"],
    ],
    c.type,
  )}</select></div><div class="field"><label for="weight-${id}">Вес, %</label><input id="weight-${id}" data-field="weight" data-id="${id}" type="number" min="0" max="100" step="0.1" value="${c.weight}"${c.type === "flag" ? " disabled" : ""}></div></div><div data-scale-fields="${id}"${c.type === "scale" ? "" : " hidden"}><div class="field"><label for="steps-${id}">Ступени шкалы через запятую</label><input id="steps-${id}" data-field="steps" data-id="${id}" value="${esc(c.steps.join(", "))}" placeholder="0, 5, 10, 15, 20"></div><div class="field"><label for="descriptions-${id}">Описание ступеней</label><textarea id="descriptions-${id}" data-field="stepDescriptions" data-id="${id}" rows="4" placeholder="20: Все вопросы закрыты&#10;0: Ответа по существу нет">${esc(
    Object.entries(c.stepDescriptions)
      .sort((a, b) => Number(b[0]) - Number(a[0]))
      .map(([step, desc]) => `${step}: ${desc}`)
      .join("\n"),
  )}</textarea><small>Каждая строка: число, двоеточие, описание.</small></div></div><div class="editor-field-bottom"><label class="checkbox-label"><input type="checkbox" data-field="allowNA" data-id="${id}"${c.allowNA ? " checked" : ""}${c.type === "flag" ? " disabled" : ""}>Разрешить «Не применяется» (N/A)</label><button type="button" class="text-button danger-text" data-action="delete-criterion" data-id="${id}" aria-label="Удалить критерий ${esc(c.name)}">${icon("trash", 15)}Удалить</button></div><div class="field" data-na-field="${id}"${c.allowNA ? "" : " hidden"}><label for="na-${id}">Условие неприменимости</label><textarea id="na-${id}" data-field="naCondition" data-id="${id}" rows="2">${esc(c.naCondition)}</textarea></div></div></details>`;
}
export function appealsView(status = "open", selectedId = "") {
  const { appeals, conversations } = getState();
  const filtered = appeals.filter(
    (a) => status === "all" || a.status === status,
  );
  const selected = appeals.find((a) => a.id === selectedId);
  return (
    heading(
      "ПЕРЕСМОТР РЕЗУЛЬТАТА",
      "Апелляции",
      "Посмотрите на диалог ещё раз. Примите обоснованное решение.",
      `<span class="badge warning">${appeals.filter((a) => a.status === "open").length} на рассмотрении</span>`,
    ) +
    `<div class="appeals-layout"><section class="panel appeals-list-panel"><div class="appeal-tabs segmented"><button data-action="appeal-filter" data-status="open" class="${status === "open" ? "active" : ""}" aria-pressed="${status === "open"}">Открытые</button><button data-action="appeal-filter" data-status="resolved" class="${status === "resolved" ? "active" : ""}" aria-pressed="${status === "resolved"}">Решённые</button><button data-action="appeal-filter" data-status="all" class="${status === "all" ? "active" : ""}" aria-pressed="${status === "all"}">Все</button></div>${
      filtered.length
        ? filtered
            .map((a) => {
              const c = conversations.find((c) => c.id === a.conversationId)!;
              const e = c.evaluations.find((e) => e.id === a.evaluationId)!;
              const cr = e.checklist.criteria.find(
                (cr) => cr.id === a.criterionId,
              )!;
              return `<a href="${href("appeals", a.id)}" class="appeal-list-item ${selectedId === a.id ? "selected" : ""}"><div class="appeal-item-meta"><span class="badge ${a.status === "open" ? "warning" : "success"}">${a.status === "open" ? "На рассмотрении" : "Решено"}</span><small>${esc(date(a.createdAt, true))}</small></div><h3>${esc(cr.name)}</h3><p>${esc(c.operator)} · ${esc(c.id)}</p><span class="appeal-preview">${esc(a.comment)}</span><div class="appeal-list-bottom"><span>Исходная оценка: <strong>${esc(answerLabel(a.originalValue, cr))}</strong></span>${icon("external", 16)}</div></a>`;
            })
            .join("")
        : empty(
            "Всё разобрано",
            "Здесь появятся апелляции с выбранным статусом.",
          )
    }</section><section class="panel appeal-detail-panel">${selected ? appealDetail(selected.id) : `<div class="appeal-welcome"><span class="large-icon">${icon("scale", 36)}</span><h2>Каждая оценка может быть пересмотрена</h2><p>Выберите апелляцию слева, изучите комментарий и фрагмент диалога. Исходная оценка останется в истории.</p><div class="appeal-flow"><span>Обращение</span>${icon("chevron", 14)}<span>Проверка</span>${icon("chevron", 14)}<span>Решение</span></div></div>`}</section></div>`
  );
}
function appealDetail(id: string) {
  const { appeals, conversations } = getState();
  const a = appeals.find((a) => a.id === id)!;
  const c = conversations.find((c) => c.id === a.conversationId)!;
  const e = c.evaluations.find((e) => e.id === a.evaluationId)!;
  const cr = e.checklist.criteria.find((cr) => cr.id === a.criterionId)!;
  const result = e.results.find((r) => r.criterionId === cr.id)!;
  return `<div class="panel-heading"><div><span class="eyebrow">${a.status === "open" ? "НА РАССМОТРЕНИИ" : "РЕШЕНИЕ СОХРАНЕНО"}</span><h2>${esc(cr.name)}</h2></div>${icon("scale", 22)}</div><div class="appeal-detail-content"><a href="${href("dialogues", c.id)}" class="text-link">${esc(c.title)}${icon("external", 15)}</a><div class="appeal-summary"><div><span>Оператор</span><strong>${esc(c.operator)}</strong></div><div><span>Исходная оценка</span><strong>${esc(answerLabel(a.originalValue, cr))}</strong></div></div><div class="appeal-comment"><span class="section-kicker">КОММЕНТАРИЙ К АПЕЛЛЯЦИИ</span><p>${esc(a.comment)}</p><small>${esc(date(a.createdAt))}</small></div><div class="appeal-evidence"><h3>Основание оценки</h3><p>${esc(result.explanation)}</p>${result.evidence.map((i) => (c.transcript[i] ? `<blockquote><div><strong>${esc(c.transcript[i].speaker === "operator" ? c.operator : "Клиент")}</strong><time>${esc(time(c.transcript[i].timestamp))}</time></div><p>${esc(c.transcript[i].text)}</p></blockquote>` : "")).join("")}</div>${a.status === "resolved" ? `<div class="resolution-card"><span class="badge success">${icon("check", 14)}${a.decision === "change" ? "Оценка изменена" : "Оценка подтверждена"}</span><h3>${esc(answerLabel(a.originalValue, cr))} → ${esc(answerLabel(a.value ?? null, cr))}</h3><p>${esc(a.reason)}</p><small>${esc(date(a.resolvedAt!))}</small></div><div class="resolution-total"><span>Итог диалога</span><strong>${formatScore(score(e, appeals))}<small> / 100</small></strong></div>` : `<form id="resolve-form" data-id="${esc(a.id)}"><h3>Решение проверяющего</h3><div class="radio-cards"><label><input type="radio" name="decision" value="confirm" checked><span>Подтвердить оценку</span></label><label><input type="radio" name="decision" value="change"><span>Изменить оценку</span></label></div><div id="new-value-field" class="field" hidden><label for="new-value">Новая оценка</label><select id="new-value" name="value">${valueOptions(cr, a.originalValue)}</select></div><div class="field"><label for="review-reason">Обоснование решения</label><textarea id="review-reason" name="reason" rows="3" required maxlength="2000" placeholder="Укажите, какие реплики и правила повлияли на решение"></textarea></div><p id="review-error" class="form-error" role="alert" hidden></p><button class="button primary" type="submit">${icon("check", 17)}Сохранить решение</button></form>`}</div>`;
}
