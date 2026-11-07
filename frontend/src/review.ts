import type { Appeal, Conversation, Criterion, Evaluation } from "./types.js";
import { getState } from "./state.js";
import { initialChecklist } from "./checklist.js";
import { initialConversations } from "./data.js";
import { demoWaveform } from "./media.js";
import {
  answerLabel,
  finalValue,
  formatScore,
  normalized,
  score,
  scoreTone,
} from "./scoring.js";
import { empty, esc, href, icon, time, brandArt } from "./ui.js";
const labels: Record<string, string> = {
  greeting: "Контакт",
  need: "Потребность",
  identity: "Идентификация",
  consultation: "Консультация",
  empathy: "Эмпатия",
  management: "Ведение диалога",
  closing: "Завершение",
  gross: "Грубые ошибки",
};
export function criterionLabel(c: Criterion) {
  return initialChecklist.criteria.find((x) => x.id === c.id)?.name === c.name
    ? labels[c.id] || c.name
    : c.name;
}
export function currentEvaluation(c: Conversation, id = "") {
  return (
    c.evaluations.find((e) => e.id === id) ||
    c.evaluations[c.evaluations.length - 1]
  );
}
export function selectionFromQuery(c: Conversation, query: string) {
  const params = new URLSearchParams(query);
  const evaluation = c.evaluations.find(
    (e) => e.id === params.get("evaluationId"),
  );
  const active = evaluation || currentEvaluation(c);
  const criterion = active?.checklist.criteria.find(
    (item) => item.id === params.get("criterionId"),
  );
  return {
    evaluationId: evaluation?.id || "",
    criterionId: criterion?.id || "",
  };
}
export function sectionContributions(e: Evaluation, appeals: Appeal[]) {
  const applicable = e.checklist.criteria.filter(
    (c) => c.type !== "flag" && (e.revision !== undefined
      ? e.results.find(r => r.criterionId === c.id)?.status !== "not_applicable"
      : finalValue(e, c.id, appeals) !== null),
  );
  const totalWeight = applicable.reduce((sum, c) => sum + c.weight, 0);
  const names = [
    ...new Set(
      e.checklist.criteria
        .filter((c) => c.type !== "flag")
        .map((c) => c.section || "Критерии"),
    ),
  ];
  return names.map((name) => {
    const criteria = applicable.filter(
      (c) => (c.section || "Критерии") === name,
    );
    const earned = criteria.reduce(
      (sum, c) => sum + normalized(finalValue(e, c.id, appeals) ?? 0, c) * c.weight,
      0,
    );
    const max = criteria.reduce((sum, c) => sum + c.weight, 0);
    return {
      name,
      earned: totalWeight ? (earned / totalWeight) * 100 : 0,
      max: totalWeight ? (max / totalWeight) * 100 : 0,
    };
  });
}
export function focusCriterion(e: Evaluation, id = "") {
  const selected = e.checklist.criteria.find((c) => c.id === id);
  if (selected) return selected;
  const { appeals } = getState();
  return [...e.checklist.criteria].sort((a, b) => {
    const loss = (c: Criterion) => {
      const value = finalValue(e, c.id, appeals);
      return c.type === "flag"
        ? value === 1
          ? Infinity
          : -1
        : value === null
          ? -1
          : c.weight * (1 - normalized(value, c));
    };
    return loss(b) - loss(a);
  })[0];
}
export function usesDemoAudio(c: Conversation) {
  const seed = initialConversations.find(
    (x) => x.id === demoWaveform.conversationId,
  );
  return (
    c.id === demoWaveform.conversationId &&
    !c.audioUrl &&
    !!seed &&
    c.transcript.map((m) => m.text).join("\n") ===
      seed.transcript.map((m) => m.text).join("\n")
  );
}
export function elapsed(c: Conversation, index: number) {
  if (usesDemoAudio(c))
    return demoWaveform.messages.find((m) => m.index === index)?.start ?? 0;
  const value = c.transcript[index]?.timestamp || "";
  if (value.includes("T"))
    return Math.max(
      0,
      (new Date(value).valueOf() -
        new Date(c.transcript[0].timestamp).valueOf()) /
        1000,
    );
  const parts = value.split(":").map(Number);
  return parts.length === 2 ? parts[0] * 60 + parts[1] : 0;
}
export function clock(seconds: number) {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}
function waveform(values: number[]) {
  const path = values
    .map((v, i) => `M${i * 2 + 1} ${14 - v * 12}v${Math.max(1, v * 24)}`)
    .join(" ");
  return `<svg viewBox="0 0 620 28" preserveAspectRatio="none" aria-hidden="true"><path d="${path}" stroke="currentColor" stroke-width="1.2"/></svg>`;
}
function player(c: Conversation) {
  if (c.channel !== "voice call") return "";
  if (usesDemoAudio(c))
    return `<section class="conversation-player demo-player" aria-label="Запись разговора"><audio id="conversation-audio" preload="metadata" src="./assets/media/demo-call.m4a"></audio><div class="waveform-roles"><span>Клиент</span><span>Оператор</span></div><div class="waveforms"><div class="waveform-track client-wave">${waveform(demoWaveform.client)}</div><div class="waveform-track operator-wave">${waveform(demoWaveform.operator)}</div><div id="waveform-selection" class="waveform-selection"></div><div id="waveform-cursor" class="waveform-cursor"></div></div><div class="player-controls"><button class="player-play" data-action="audio-play" aria-label="Воспроизвести запись">${icon("play", 22)}</button><output id="player-time">00:00 / ${clock(demoWaveform.duration)}</output><input id="player-seek" type="range" min="0" max="${demoWaveform.duration}" step="0.1" value="0" aria-label="Позиция в записи"><span class="recording-label">Демо-запись</span><span id="audio-error" role="status" hidden></span></div></section>`;
  return `<section class="conversation-player simple-player">${icon("headphones", 22)}<span>${c.audioUrl ? "Запись разговора" : "Запись недоступна"}</span>${c.audioUrl ? `<audio id="conversation-audio" controls preload="metadata" src="${esc(c.audioUrl)}"></audio>` : `<span class="muted">${esc(c.duration)}</span>`}</section>`;
}
export function detailView(
  c: Conversation,
  evaluationId = "",
  criterionId = "",
) {
  const e = currentEvaluation(c, evaluationId);
  const cr = e ? focusCriterion(e, criterionId) : null;
  const index = e?.results.find((r) => r.criterionId === cr?.id)?.evidence[0];
  const { checklists } = getState();
  return `<div class="conversation-page ${c.channel === "voice call" ? "has-player" : "chat-page"}"><div class="conversation-header"><div><h1 class="page-title">${brandArt("dialogues")}Анализ разговора</h1><p class="conversation-meta"><span>${esc(c.id)}</span><span>${c.language === "RU" ? "Русский" : c.language === "KZ" ? "Қазақша" : "English"}</span><span>${esc(c.operator)}</span><span>${usesDemoAudio(c) ? clock(demoWaveform.duration) : esc(c.duration)}</span></p></div><div class="conversation-controls"><label class="sr-only" for="evaluation-checklist">Чек-лист для оценки</label><select id="evaluation-checklist">${[
    ...checklists,
  ]
    .reverse()
    .map(
      (list) =>
        `<option value="${esc(list.id)}">${esc(list.name)} · v${esc(list.version)}</option>`,
    )
    .join(
      "",
    )}</select><label class="sr-only" for="evaluation-engine">Способ оценки</label><select id="evaluation-engine"><option value="auto">AI-оценка</option><option value="baseline">Ручная проверка</option></select><button class="button primary" data-action="evaluate" data-id="${esc(c.id)}" title="Оценить диалог на сервере">Оценить</button></div></div>${player(c)}<div class="mobile-detail-tabs segmented"><button data-action="detail-tab" data-tab="transcript" aria-pressed="false">Расшифровка</button><button data-action="detail-tab" data-tab="evaluation" class="active" aria-pressed="true">Оценка</button></div><div id="detail-grid" class="review-workspace mobile-show-evaluation"><section class="transcript-panel"><div class="panel-heading"><h2>Расшифровка</h2><span class="muted">${c.transcript.length} реплик</span></div><div class="transcript-messages">${c.transcript.map((m, i) => `<article id="message-${i}" tabindex="-1" class="transcript-row message ${m.speaker}${i === index ? " highlighted" : ""}"><time>${esc(usesDemoAudio(c) ? clock(elapsed(c, i)) : time(m.timestamp))}</time><div><span class="muted">№${i + 1}</span><strong class="message-role">${m.speaker === "operator" ? "Оператор" : m.speaker === "client" ? "Клиент" : m.speaker === "bot" ? "Бот" : "Система"}</strong><p>${esc(m.text)}</p></div></article>`).join("")}</div></section><section class="quality-workbench">${e ? qualityView(c, e, criterionId) : `<div class="panel-heading"><h2>Оценка качества</h2></div>${empty("Оценка ещё не выполнена", "Выберите чек-лист и запустите оценку.", `<button class="button primary" data-action="evaluate" data-id="${esc(c.id)}">Оценить диалог</button>`)}`}</section></div></div>`;
}
export function qualityView(c: Conversation, e: Evaluation, criterionId = "") {
  const { appeals } = getState();
  const total = score(e, appeals);
  const cr = focusCriterion(e, criterionId);
  if (!cr) return empty("Нет критериев", "Добавьте критерии в чек-лист.");
  const result = e.results.find((r) => r.criterionId === cr.id)!;
  const value = finalValue(e, cr.id, appeals);
  const appeal = appeals.find(
    (a) => a.evaluationId === e.id && a.criterionId === cr.id,
  );
  const changed = appeals.some(
    (a) => a.evaluationId === e.id && a.status === "resolved",
  );
  const problem =
    value !== null &&
    (cr.type === "flag" ? value === 1 : normalized(value, cr) < 1);
  const sectionLabels: Record<string, string> = {
    "Начало и понимание запроса": "Начало диалога",
    "Безопасность и решение": "Решение запроса",
    "Ведение и завершение диалога": "Ведение диалога",
  };
  const sections = sectionContributions(e, appeals);
  const sectionRow = (section: (typeof sections)[number]) =>
    `<div title="Вклад секции в общий итог после N/A"><span>${esc(sectionLabels[section.name] || section.name)}</span><strong>${formatScore(section.earned)}<small> / ${formatScore(section.max)}</small></strong></div>`;
  const flag = e.checklist.criteria.find(
    (c) => c.type === "flag" && finalValue(e, c.id, appeals) === 1,
  );
  return `<div class="panel-heading"><h2>Оценка качества</h2>${
    c.evaluations.length > 1
      ? `<label class="sr-only" for="evaluation-history">Версия оценки</label><select id="evaluation-history" class="small-select">${[
          ...c.evaluations,
        ]
          .reverse()
          .map(
            (item, i) =>
              `<option value="${esc(item.id)}"${item.id === e.id ? " selected" : ""}>Оценка ${c.evaluations.length - i}</option>`,
          )
          .join("")}</select>`
      : ""
  }</div>${e.needsReview ? `<div class="notice-box">Есть неоценённые или требующие проверки критерии. Покрытие: ${formatScore(e.coverage ?? null)}%.</div>` : ""}<div class="quality-summary"><div class="score-ring ${scoreTone(total)}" style="--score:${(total ?? 0) * 3.6}deg"><div><strong>${formatScore(total)}</strong><span>/ 100</span></div></div><div class="section-mini-list">${sections.slice(0, 3).map(sectionRow).join("")}${sections.length > 3 ? `<details class="section-extra"><summary>Ещё секций: ${sections.length - 3}</summary><div class="section-mini-list">${sections.slice(3).map(sectionRow).join("")}</div></details>` : ""}${changed ? `<p class="original-score">Исходная: ${formatScore(score(e, [], true))}</p>` : ""}</div></div>${flag ? `<div class="gross-alert">${icon("alert", 16)}Грубое нарушение · флаг без баллов</div>` : ""}<div class="focused-criterion"><span>${esc(criterionLabel(cr))}</span><strong class="${problem ? "text-warning" : "text-success"}">${esc(answerLabel(value, cr, result?.status))}</strong></div><div class="reason-panel"><h3>${result.status === "needs_review" ? "Требует проверки" : value === null ? "Почему не применяется" : cr.type === "flag" && problem ? "Грубое нарушение" : problem ? "Почему снижена оценка" : "Что выполнено"}</h3><p>${esc(appeal?.status === "resolved" ? appeal.reason || result.explanation : result.explanation)}</p></div><div class="quality-actions">${result.evidence.length ? `<button class="button primary" data-action="evidence" data-index="${result.evidence[0]}">К фрагменту${icon("arrow", 17)}</button>` : '<span class="muted">Нет реплики-доказательства</span>'}${appeal ? `<a class="button secondary" href="${href("appeals", appeal.id)}">${appeal.status === "open" ? "Апелляция" : "Решение"}</a>` : `<button class="button secondary" data-action="appeal" data-evaluation="${esc(e.id)}" data-criterion="${esc(cr.id)}">Оспорить оценку</button>`}</div><button class="all-criteria-button" data-action="all-criteria" data-evaluation="${esc(e.id)}">Все ${e.checklist.criteria.length} критериев${icon("chevron", 17)}</button>`;
}
export function allCriteriaView(c: Conversation, e: Evaluation) {
  const { appeals } = getState();
  return `<div class="all-criteria-list">${e.checklist.criteria
    .map((cr, i) => {
      const result = e.results.find((r) => r.criterionId === cr.id);
      const value = finalValue(e, cr.id, appeals);
      const appeal = appeals.find(
        (a) => a.evaluationId === e.id && a.criterionId === cr.id,
      );
      return `<article class="all-criterion"><button data-action="focus-criterion" data-id="${esc(cr.id)}" class="all-criterion-heading"><span>${String(i + 1).padStart(2, "0")}</span><strong>${esc(cr.name)}</strong><b>${esc(answerLabel(value, cr, result?.status))}</b>${icon("chevron", 16)}</button><div><p>${esc(result?.explanation)}</p><span class="criterion-rules">${cr.type === "flag" ? "Без баллов · не обнуляет итог" : `Вес ${cr.weight}%${value !== null ? ` · ${formatScore(normalized(value, cr) * cr.weight)} из ${cr.weight} базовых баллов до N/A` : ""}`}</span>${value === null && result?.status !== "needs_review" ? `<p class="na-note">N/A: ${esc(cr.naCondition)}</p>` : ""}${appeal?.status === "resolved" ? `<p class="decision-inline">Исходная: ${esc(answerLabel(appeal.originalValue, cr))}. Решение: ${esc(appeal.reason)}</p>` : ""}<details class="criterion-rule-details"><summary>Правило${icon("down", 16)}</summary><p>${esc(cr.prompt)}</p>${cr.type === "scale" ? `<dl class="scale-rubric">${cr.steps.map((step) => `<div><dt>${step}</dt><dd>${esc(cr.stepDescriptions[step])}</dd></div>`).join("")}</dl>` : ""}${cr.allowNA ? `<p>N/A: ${esc(cr.naCondition)}</p>` : ""}</details><button class="text-button" data-action="focus-criterion" data-id="${esc(cr.id)}">Показать в разговоре${icon("arrow", 15)}</button></div></article>`;
    })
    .join("")}</div>`;
}
