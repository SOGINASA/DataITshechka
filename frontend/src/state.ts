import type { Appeal, Checklist, Conversation } from "./types.js";
import { validValue } from "./scoring.js";
import { api, apiId } from "./api.js";
import { mapAppeal, mapChecklist, mapConversation, mapEvaluation, checklistPayload, conversationPayload,
  type ApiAppeal, type ApiChecklist, type ApiConversation, type ApiEvaluation, type ApiReview } from "./api-mapping.js";

export interface Pagination { page: number; per_page: number; total: number; pages: number }
export interface Summary extends Omit<ApiConversation, "messages" | "recording_url"> {
  evaluation_id: string | null; assessed: boolean; final_score: number | null; open_appeals: number;
}
interface AppealRow {
  id: string; evaluation_id: string; criterion_id: string; status: "open" | "resolved"; created_at: string;
  conversation_id: string; operator_name: string | null; criterion_name: string;
}
export interface Overview {
  total: number; assessed: number; attention: number; average: number | null; open_appeals: number;
  recent: Summary[]; appeals: AppealRow[];
  trend: {date: string; value: number | null}[]; criteria: {name: string; value: number | null}[];
}
interface Bundle {
  conversation: ApiConversation; evaluations: ApiEvaluation[]; checklists: ApiChecklist[];
  appeals: ApiAppeal[]; reviews: ApiReview[];
}
export interface LoadOptions { page?: number; search?: string; language?: string; channel?: string; status?: string }
const state = {
  conversations: [] as Conversation[], checklists: [] as Checklist[], appeals: [] as Appeal[],
  overview: null as Overview | null, openAppeals: 0,
  pagination: {page: 1, per_page: 20, total: 0, pages: 0} as Pagination,
  appealRows: [] as AppealRow[], selectedAppeal: "", appealStatus: "open",
};
export const getState = () => state;
let loadVersion = 0;
export function cancelWorkspaceLoad() { loadVersion++; }

function mapSummary(raw: Summary): Conversation {
  return {...mapConversation({...raw, messages: [], recording_url: null}),
    summary: {score: raw.final_score, assessed: raw.assessed, evaluationId: raw.evaluation_id, openAppeals: raw.open_appeals}};
}
function mapBundle(data: Bundle) {
  const checklists = data.checklists.map(mapChecklist);
  const conversation = mapConversation(data.conversation);
  conversation.evaluations = data.evaluations.map(raw => {
    const checklist = checklists.find(c => c.id === raw.checklist_id);
    if (!checklist) throw new Error("В ответе сервера отсутствует чек-лист оценки.");
    return mapEvaluation(raw, checklist, conversation);
  });
  const appeals = data.appeals.map(a => mapAppeal(a, conversation.id, data.reviews.find(r => r.id === a.review_id)));
  return {checklists, conversation, appeals};
}
export async function loadWorkspace(section = "overview", id = "", options: LoadOptions = {}) {
  const version = ++loadVersion;
  const params = new URLSearchParams({page: String(options.page || 1), per_page: "20"});
  let next: Partial<typeof state>;
  if (section === "dialogues" && id) {
    const data = await api.request<Bundle & {open_appeals: number}>(`workspace/conversations/${apiId(id)}`);
    const bundle = mapBundle(data);
    next = {checklists: bundle.checklists, conversations: [bundle.conversation], appeals: bundle.appeals, openAppeals: data.open_appeals};
  } else if (section === "dialogues") {
    params.set("search", options.search || "");
    params.set("language", ({RU:"ru", KZ:"kk", EN:"en"} as Record<string,string>)[options.language || ""] || "all");
    params.set("channel", ({"agent chat":"chat", "voice call":"call"} as Record<string,string>)[options.channel || ""] || "all");
    params.set("status", options.status || "all");
    const data = await api.request<{items: Summary[]; pagination: Pagination; open_appeals: number}>(`workspace/conversations?${params}`);
    next = {conversations: data.items.map(mapSummary), appeals: [], pagination: data.pagination, openAppeals: data.open_appeals};
  } else if (section === "appeals") {
    params.set("status", options.status || "open");
    if (id) params.set("selected", id);
    const data = await api.request<{items: AppealRow[]; pagination: Pagination; open_appeals: number;
      status: string; selected_id: string | null; detail: Bundle | null}>(`workspace/appeals?${params}`);
    const bundle = data.detail ? mapBundle(data.detail) : null;
    // List metadata stays lightweight; only the selected conversation has evidence/history.
    next = {conversations: bundle ? [bundle.conversation] : [], checklists: bundle?.checklists || [], appeals: bundle?.appeals || [],
      appealRows: data.items, selectedAppeal: data.selected_id || "", appealStatus: data.status,
      pagination: data.pagination, openAppeals: data.open_appeals};
  } else if (section === "checklists") {
    const [checklists, stats] = await Promise.all([api.list<ApiChecklist>("checklists"), api.request<{open_appeals: number}>("stats")]);
    next = {checklists: checklists.reverse().map(mapChecklist), openAppeals: stats.open_appeals};
  } else {
    const overview = await api.request<Overview>("workspace/overview");
    next = {overview, conversations: overview.recent.map(mapSummary), appeals: [], openAppeals: overview.open_appeals};
  }
  if (version !== loadVersion) return false;
  Object.assign(state, next);
  return true;
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
  state.openAppeals++;
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
  state.openAppeals = Math.max(0, state.openAppeals - 1);
  return true;
}
