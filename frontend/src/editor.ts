import type { Checklist, Criterion } from "./types.js";
import { getState } from "./state.js";
import { esc, icon, options } from "./ui.js";
import { criterionLabel } from "./review.js";
export function criterionMaster(draft: Checklist, selectedId: string) {
  return `<div class="criteria-master-list">${draft.criteria.map((c, i) => `<button type="button" class="criterion-master-item ${c.id === selectedId ? "selected" : ""}" data-action="select-editor-criterion" data-id="${esc(c.id)}" aria-pressed="${c.id === selectedId}"><span class="criterion-index">${String(i + 1).padStart(2, "0")}</span><strong data-title="${esc(c.id)}">${esc(criterionLabel(c))}</strong><span data-weight="${esc(c.id)}">${c.type === "flag" ? "Флаг" : `${Number.isFinite(c.weight) ? c.weight : "—"}%`}</span></button>`).join("")}</div>`;
}
export function checklistView(
  draft: Checklist,
  dirty: boolean,
  selectedId = "",
  mobileDetail = false,
) {
  const { checklists } = getState();
  const selected =
    draft.criteria.find((c) => c.id === selectedId) || draft.criteria[0];
  return `<div class="page-heading"><h1>Чек-листы</h1><div class="checklist-toolbar"><label for="checklist-version" class="sr-only">Сохранённая версия чек-листа</label><select id="checklist-version">${[
    ...checklists,
  ]
    .reverse()
    .map(
      (c) =>
        `<option value="${esc(c.id)}"${c.id === draft.id ? " selected" : ""}>${esc(c.name)} · v${esc(c.version)}</option>`,
    )
    .join(
      "",
    )}</select><button id="save-checklist" form="checklist-form" type="submit" class="button primary"${dirty ? "" : " disabled"}>Сохранить версию</button></div></div><form id="checklist-form" class="checklist-workspace ${mobileDetail ? "editor-show-detail" : "editor-show-list"}"><aside class="criteria-master"><div class="master-heading"><h2>Критерии</h2><span>${draft.criteria.length}</span></div><div id="criteria-master-items">${criterionMaster(draft, selected?.id || "")}</div><button type="button" class="add-criterion" data-action="add-criterion">${icon("plus", 18)}Добавить критерий</button><div class="weight-summary"><span>Сумма весов</span><strong id="weight-total">${draft.criteria.reduce((sum, c) => sum + (Number.isFinite(c.weight) ? c.weight : 0), 0)}% <small>/ 100%</small></strong></div><details class="checklist-settings"><summary>Название чек-листа${icon("down", 16)}</summary><label for="checklist-name" class="sr-only">Название чек-листа</label><input id="checklist-name" maxlength="80" value="${esc(draft.name)}" required></details><span id="draft-status" class="draft-status">${dirty ? "Есть изменения" : `Версия ${esc(draft.version)} сохранена`}</span></aside><section id="criterion-editor" class="criterion-editor">${selected ? editorCriterion(selected, draft.criteria.indexOf(selected)) : "<p>Добавьте первый критерий.</p>"}</section><p id="checklist-error" class="form-error editor-error" role="alert" hidden></p></form>`;
}
export function editorCriterion(c: Criterion, i: number) {
  const id = esc(c.id);
  return `<div class="criterion-editor-header"><button type="button" class="text-button editor-back" data-action="editor-back">${icon("back", 18)}Критерии</button><h2>${esc(criterionLabel(c))}</h2><span class="muted">${String(i + 1).padStart(2, "0")}</span></div><div class="editor-fields" data-criterion="${id}"><div class="field"><label for="name-${id}">Название</label><input id="name-${id}" data-field="name" data-id="${id}" value="${esc(c.name)}" maxlength="100" required></div><div class="field"><label for="prompt-${id}">Что проверяем</label><textarea id="prompt-${id}" data-field="prompt" data-id="${id}" rows="3" maxlength="1500" required>${esc(c.prompt)}</textarea></div><div class="editor-field-row"><div class="field"><label for="type-${id}">Тип ответа</label><select id="type-${id}" data-field="type" data-id="${id}">${options(
    [
      ["binary", "Да / Нет"],
      ["scale", "Числовая шкала"],
      ["flag", "Флаг нарушения"],
    ],
    c.type,
  )}</select></div><div class="field"><label for="weight-${id}">Вес, %</label><input id="weight-${id}" data-field="weight" data-id="${id}" type="number" min="0" max="100" step="0.1" value="${c.weight}"${c.type === "flag" ? " disabled" : ""}></div></div><details class="editor-extra"${c.type === "scale" ? " open" : ""}><summary>Шкала и применимость${icon("down", 18)}</summary><div data-scale-fields="${id}"${c.type === "scale" ? "" : " hidden"}><div class="field"><label for="steps-${id}">Ступени шкалы через запятую</label><input id="steps-${id}" data-field="steps" data-id="${id}" value="${esc(c.steps.join(", "))}" placeholder="0, 5, 10, 15, 20"></div><div class="field"><label for="descriptions-${id}">Описание ступеней</label><textarea id="descriptions-${id}" data-field="stepDescriptions" data-id="${id}" rows="5">${esc(
    Object.entries(c.stepDescriptions)
      .sort((a, b) => Number(b[0]) - Number(a[0]))
      .map(([step, desc]) => `${step}: ${desc}`)
      .join("\n"),
  )}</textarea></div></div><label class="checkbox-label"><input type="checkbox" data-field="allowNA" data-id="${id}"${c.allowNA ? " checked" : ""}${c.type === "flag" ? " disabled" : ""}>Разрешить N/A</label><div class="field" data-na-field="${id}"${c.allowNA ? "" : " hidden"}><label for="na-${id}">Когда критерий не применяется</label><textarea id="na-${id}" data-field="naCondition" data-id="${id}" rows="2">${esc(c.naCondition)}</textarea></div></details><details class="editor-extra"><summary>Секция${icon("down", 18)}</summary><div class="field"><label for="section-${id}" class="sr-only">Секция</label><input id="section-${id}" data-field="section" data-id="${id}" value="${esc(c.section)}" maxlength="80"></div></details><div class="editor-delete"><button type="button" class="text-button danger-text" data-action="delete-criterion" data-id="${id}">${icon("trash", 17)}Удалить критерий</button></div></div>`;
}
