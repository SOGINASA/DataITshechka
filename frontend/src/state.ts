import type { Appeal, Checklist, Conversation } from "./types.js";
import { validValue } from "./scoring.js";
import { api, apiId } from "./api.js";
import { mapAppeal, mapChecklist, mapConversation, mapEvaluation, checklistPayload, conversationPayload,
  type ApiAppeal, type ApiChecklist, type ApiConversation, type ApiEvaluation, type ApiExport, type ApiReview } from "./api-mapping.js";

const state: { conversations: Conversation[]; checklists: Checklist[]; appeals: Appeal[] } = {
  conversations: [], checklists: [], appeals: [],
};
export const getState = () => state;

async function mapLimited<T, R>(items: T[], task: (item: T) => Promise<R>, concurrency = 4): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let cursor = 0;
  await Promise.all(Array.from({length: Math.min(concurrency, items.length)}, async () => {
    while (cursor < items.length) { const index = cursor++; results[index] = await task(items[index]); }
  }));
  return results;
}
function unpack(data: ApiExport, conversation: Conversation) {
  return { evaluation: mapEvaluation(data.evaluation, mapChecklist(data.checklist), conversation),
    appeals: data.appeals.map(a => mapAppeal(a, conversation.id, data.reviews.find(r => r.id === a.review_id))) };
}
async function fetchConversation(id: string) {
  const [raw, evaluations] = await Promise.all([
    api.request<ApiConversation>(`conversations/${apiId(id)}`),
    api.list<ApiEvaluation>(`conversations/${apiId(id)}/evaluations`),
  ]);
  const conversation = mapConversation(raw);
  const details = await mapLimited(evaluations.reverse(), async e => unpack(await api.request<ApiExport>(`evaluations/${apiId(e.id)}/export`), conversation), 2);
  conversation.evaluations = details.map(d => d.evaluation);
  return {conversation, appeals: details.flatMap(d => d.appeals)};
}
export async function loadWorkspace() {
  const [checklists, summaries] = await Promise.all([
    api.list<ApiChecklist>("checklists"), api.list<{id: string}>("conversations"),
  ]);
  const details = await mapLimited(summaries, c => fetchConversation(c.id));
  // Replace only after every request succeeds: never show an incomplete snapshot as complete.
  state.checklists = checklists.reverse().map(mapChecklist);
  state.conversations = details.map(d => d.conversation);
  state.appeals = details.flatMap(d => d.appeals).sort((a,b) => b.createdAt.localeCompare(a.createdAt));
}
export async function addConversations(records: Conversation[]) {
  if (!records.length || records.length > 100) throw new Error("За один раз можно добавить от 1 до 100 диалогов.");
  const payload = {conversations: records.map(conversationPayload)};
  if (new TextEncoder().encode(JSON.stringify(payload)).length > 4 * 1024 * 1024)
    throw new Error("Размер запроса превышает 4 МиБ. Разделите файл на меньшие части.");
  const response = await api.request<{items: ApiConversation[]; imported: number}>("conversations/import", payload);
  // The import response omits messages; use the exact submitted payload with server IDs.
  const imported = response.items.map((item, index) => mapConversation({...item, messages: payload.conversations[index].messages}));
  state.conversations.unshift(...imported);
  return response.imported;
}
export async function importDataset(groupId: string) {
  const result = await api.request<{imported: number; skipped: number}>("datasets/import", {group_id: groupId}, 180000);
  try { await loadWorkspace(); }
  catch { throw new Error("Импорт выполнен, но не удалось обновить список. Обновите страницу перед повторным импортом."); }
  return result;
}
export async function saveChecklist(draft: Checklist) {
  for (const c of draft.criteria) {
    if (c.type !== "binary" && c.rule && ["contains_any", "contains_none"].includes(c.rule.type))
      throw new Error(`Критерий «${c.name}» использует поиск фраз, доступный только для бинарного ответа.`);
  }
  const numericVersions = state.checklists.filter(c => c.name === draft.name).map(c => Number(c.version));
  const version = numericVersions.every(Number.isFinite) ? String(Math.max(0, ...numericVersions) + 1) : new Date().toISOString();
  const raw = await api.request<ApiChecklist>(draft.id ? `checklists/${apiId(draft.id)}/versions` : "checklists",
    {...checklistPayload(draft), version});
  const saved = mapChecklist(raw);
  state.checklists.push(saved);
  return saved;
}
export async function evaluate(id: string, checklistId: string, engine = "auto") {
  const c = state.conversations.find(c => c.id === id);
  if (!c) throw new Error("Диалог не найден. Обновите данные.");
  const raw = await api.request<ApiEvaluation>(`conversations/${apiId(id)}/evaluations`, {checklist_id: checklistId, engine}, 360000);
  const checklist = state.checklists.find(checklist => checklist.id === raw.checklist_id);
  if (!checklist) throw new Error("Оценка сохранена. Обновите страницу, чтобы загрузить её чек-лист.");
  const evaluation = mapEvaluation(raw, checklist, c);
  const current = state.conversations.find(item => item.id === id);
  if (!current) throw new Error("Оценка сохранена. Обновите список диалогов.");
  current.evaluations.push(evaluation);
  return evaluation;
}
export async function submitAppeal(input: {
  conversationId: string; evaluationId: string; criterionId: string; originalValue: number | null; comment: string; author: string;
}) {
  const evaluation = state.conversations.find(c => c.id === input.conversationId)?.evaluations.find(e => e.id === input.evaluationId);
  if (!evaluation?.revision) throw new Error("Обновите данные перед отправкой апелляции.");
  if (state.appeals.some(a => a.evaluationId === input.evaluationId && a.criterionId === input.criterionId && a.status === "open"))
    throw new Error("По этому критерию уже есть открытая апелляция.");
  const raw = await api.request<ApiAppeal>(`evaluations/${apiId(input.evaluationId)}/appeals`, {
    criterion_id: input.criterionId, expected_revision: evaluation.revision, comment: input.comment, author: input.author,
  });
  const appeal = mapAppeal(raw, input.conversationId);
  state.appeals.unshift(appeal);
  return appeal;
}
export async function resolveAppeal(id: string, decision: "confirm" | "change", value: number | null,
  reason: string, reviewer: string, evidenceNumbers: string, rangeStart: string, rangeEnd: string) {
  const appeal = state.appeals.find(a => a.id === id && a.status === "open");
  const conversation = state.conversations.find(c => c.id === appeal?.conversationId);
  const evaluation = conversation?.evaluations.find(e => e.id === appeal?.evaluationId);
  const criterion = evaluation?.checklist.criteria.find(c => c.id === appeal?.criterionId);
  if (!appeal || !conversation || !evaluation?.revision || !criterion) throw new Error("Обновите данные перед сохранением решения.");
  if (!reason.trim() || !reviewer.trim()) throw new Error("Укажите проверяющего и причину решения.");
  if (decision === "change" && !validValue(value, criterion)) throw new Error("Выберите допустимую оценку.");
  const payload: Record<string, unknown> = {expected_revision: evaluation.revision, decision, reviewer, reason};
  if (decision === "change") {
    const override: Record<string, unknown> = {criterion_id: criterion.id, explanation: reason,
      value: value === null ? null : criterion.type === "scale" ? value : Boolean(value)};
    if (value === null) override.status = "not_applicable";
    const messageId = (raw: string) => {
      const n = Number(raw.trim());
      if (!/^\d+$/.test(raw.trim()) || !Number.isInteger(n) || n < 1 || !conversation.transcript[n - 1]?.id)
        throw new Error("Укажите существующие номера реплик, начиная с 1.");
      return conversation.transcript[n - 1].id!;
    };
    if (evidenceNumbers.trim()) override.evidence_message_ids = evidenceNumbers.split(",").map(messageId);
    if (rangeStart.trim() || rangeEnd.trim()) {
      const start = messageId(rangeStart), end = messageId(rangeEnd);
      if (Number(rangeStart) > Number(rangeEnd)) throw new Error("Начало проверенного диапазона должно быть не позже конца.");
      override.reviewed_range = {start_message_id: start, end_message_id: end};
    }
    payload.override = override;
  }
  const result = await api.request<{appeal: ApiAppeal; review: ApiReview; evaluation: ApiEvaluation}>(`appeals/${apiId(id)}/decision`, payload);
  const current = state.conversations.find(c => c.id === conversation.id);
  if (!current) throw new Error("Решение сохранено. Обновите список диалогов.");
  const index = current.evaluations.findIndex(e => e.id === evaluation.id);
  if (index < 0) throw new Error("Решение сохранено. Обновите данные оценки.");
  current.evaluations[index] = mapEvaluation(result.evaluation, evaluation.checklist, current);
  const currentAppeal = state.appeals.find(a => a.id === id);
  if (currentAppeal) Object.assign(currentAppeal, mapAppeal(result.appeal, current.id, result.review));
  return true;
}
