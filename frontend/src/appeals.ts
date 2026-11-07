import { getState } from "./state.js";
import { answerLabel, finalValue, formatScore, score } from "./scoring.js";
import { date, empty, esc, href, icon, valueOptions, brandArt } from "./ui.js";
import { criterionLabel, elapsed, clock, usesDemoAudio } from "./review.js";
export function appealsView(status = "open", selectedId = "") {
  const { appeals, conversations } = getState();
  const filtered = appeals.filter(
    (a) => status === "all" || a.status === status,
  );
  const selected = appeals.find((a) => a.id === selectedId) || filtered[0];
  return `<div class="page-heading"><h1 class="page-title">${brandArt("appeals")}Апелляции</h1><span class="muted">${appeals.filter((a) => a.status === "open").length} на рассмотрении</span></div><div class="appeals-layout ${selectedId ? "appeal-show-detail" : "appeal-show-list"}"><section class="appeals-list-panel"><div class="appeal-tabs segmented"><button data-action="appeal-filter" data-status="open" class="${status === "open" ? "active" : ""}" aria-pressed="${status === "open"}">Открытые</button><button data-action="appeal-filter" data-status="resolved" class="${status === "resolved" ? "active" : ""}" aria-pressed="${status === "resolved"}">Решённые</button><button data-action="appeal-filter" data-status="all" class="${status === "all" ? "active" : ""}" aria-pressed="${status === "all"}">Все</button></div>${
    filtered.length
      ? filtered
          .map((a) => {
            const c = conversations.find((c) => c.id === a.conversationId)!;
            const e = c.evaluations.find((e) => e.id === a.evaluationId)!;
            const cr = e.checklist.criteria.find(
              (cr) => cr.id === a.criterionId,
            )!;
            return `<a href="${href("appeals", a.id)}" class="appeal-list-item ${selected?.id === a.id ? "selected" : ""}"><strong>${esc(c.operator)}</strong><span>${esc(criterionLabel(cr))}</span><div class="appeal-item-meta"><span class="badge ${a.status === "open" ? "warning" : "success"}">${a.status === "open" ? "Открыта" : "Решена"}</span><time>${esc(date(a.createdAt, true))}</time></div></a>`;
          })
          .join("")
      : empty("Нет апелляций", "Все обращения с этим статусом разобраны.")
  }</section><section class="appeal-detail-panel">${selected ? appealDetail(selected.id) : '<div class="empty-state"><h2>Нет открытых обращений</h2></div>'}</section></div>`;
}
function appealDetail(id: string) {
  const { appeals, conversations } = getState();
  const a = appeals.find((a) => a.id === id)!;
  const c = conversations.find((c) => c.id === a.conversationId)!;
  const e = c.evaluations.find((e) => e.id === a.evaluationId)!;
  const cr = e.checklist.criteria.find((cr) => cr.id === a.criterionId)!;
  const currentResult = e.results.find((r) => r.criterionId === cr.id)!;
  const result = {...currentResult, explanation: a.originalExplanation ?? currentResult.explanation,
    evidence: a.originalEvidenceIds?.map(id => c.transcript.findIndex(m => m.id === id)).filter(i => i >= 0) ?? currentResult.evidence};
  const evidenceIndex = result.evidence[0];
  const query = new URLSearchParams({ evaluationId: e.id, criterionId: cr.id });
  if (evidenceIndex !== undefined) query.set("evidence", String(evidenceIndex));
  const conversationHref = `${href("dialogues", c.id)}?${query.toString()}`;
  return `<div class="appeal-detail-header"><a href="#/appeals" class="text-button appeal-back">${icon("back", 18)}Апелляции</a><h2>${esc(criterionLabel(cr))}</h2><a href="${esc(conversationHref)}" class="text-link">${esc(c.id)}${icon("external", 17)}</a></div><div class="appeal-detail-content"><div class="appeal-score-line"><div><span>Исходная оценка</span><strong>${esc(answerLabel(a.originalValue, cr, a.originalStatus))}</strong></div>${a.status === "resolved" ? `<div><span>После пересмотра</span><strong>${esc(answerLabel(a.value === undefined ? a.originalValue : a.value, cr, a.decisionStatus))}</strong></div>` : ""}</div><section class="appeal-comment"><h3>Комментарий</h3><p>${esc(a.comment)}</p></section><section class="appeal-evidence"><div class="section-line"><h3>Фрагмент</h3><a href="${esc(conversationHref)}" class="text-link">Весь разговор${icon("external", 16)}</a></div>${result.evidence.map((i) => (c.transcript[i] ? `<blockquote><div><strong>${c.transcript[i].speaker === "operator" ? "Оператор" : "Клиент"}</strong><time>${esc(usesDemoAudio(c) ? clock(elapsed(c, i)) : c.transcript[i].timestamp)}</time></div><p>${esc(c.transcript[i].text)}</p></blockquote>` : "")).join("")}<details class="appeal-reason"><summary>Обоснование исходной оценки${icon("down", 16)}</summary><p>${esc(result.explanation)}</p></details></section>${a.status === "resolved" ? `<section class="resolution-card"><h3>Решение</h3><strong>${a.decision === "change" ? "Оценка изменена" : "Оценка подтверждена"}</strong><p>${esc(a.reason)}</p><div class="resolution-total"><span>Текущий итог диалога</span><strong>${formatScore(score(e, appeals))}<small> / 100</small></strong></div></section>` : `<form id="resolve-form" data-id="${esc(a.id)}"><h3>Решение</h3><div class="field"><label for="reviewer-name">Имя проверяющего</label><input id="reviewer-name" name="reviewer" required maxlength="120" autocomplete="name"></div><div class="radio-cards"><label><input type="radio" name="decision" value="confirm" checked><span>Подтвердить</span></label><label><input type="radio" name="decision" value="change"><span>Изменить</span></label></div><div id="new-value-field" class="field" hidden><label for="new-value">Новая оценка</label><select id="new-value" name="value">${valueOptions(cr, a.originalValue)}</select></div><div class="field"><label for="review-evidence">Номера реплик-доказательств через запятую</label><input id="review-evidence" name="evidence" placeholder="Например: 2, 5" value="${esc(result.evidence.map(i => i + 1).join(", "))}"></div><details><summary>Проверенный диапазон реплик</summary><p>Укажите его, если вывод основан на отсутствии действия в просмотренном участке.</p><div class="field"><label for="range-start">От реплики</label><input id="range-start" name="range-start" type="number" min="1" max="${c.transcript.length}"></div><div class="field"><label for="range-end">До реплики</label><input id="range-end" name="range-end" type="number" min="1" max="${c.transcript.length}"></div></details><div class="field"><label for="review-reason">Причина решения</label><textarea id="review-reason" name="reason" rows="2" required maxlength="2000" placeholder="На какие реплики и правила вы опираетесь?"></textarea></div><p id="review-error" class="form-error" role="alert" hidden></p><button class="button primary" type="submit">Сохранить решение</button></form>`}</div>`;
}
