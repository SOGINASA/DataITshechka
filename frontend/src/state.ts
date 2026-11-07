import type { Appeal, Checklist, Conversation } from "./types.js";
import { validValue } from "./scoring.js";
import {
  initialConversations,
  initialChecklist,
  initialAppeals,
  createDemoEvaluation,
} from "./data.js";
const STORAGE_KEY = "freedom-cqa-vanilla-v1";
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const defaults = () => ({
  conversations: clone(initialConversations),
  checklists: [clone(initialChecklist)],
  appeals: clone(initialAppeals),
});
let state = defaults();
let persistenceWarning: string | null = null;
const storageWarning =
  "Изменения доступны только в этой вкладке: хранилище браузера недоступно или заполнено. После перезагрузки они могут быть потеряны.";
export function getPersistenceWarning() {
  return persistenceWarning;
}
try {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
  if (
    saved &&
    Array.isArray(saved.conversations) &&
    Array.isArray(saved.checklists) &&
    saved.checklists.length &&
    Array.isArray(saved.appeals)
  )
    state = saved;
} catch {
  persistenceWarning = storageWarning;
}
export function getState() {
  return state;
}
export function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    persistenceWarning = null;
    return true;
  } catch {
    persistenceWarning = storageWarning;
    return false;
  }
}
export function addConversations(records: Conversation[]) {
  const ids = new Set(state.conversations.map((c) => c.id));
  const fresh = records.filter((c) => !ids.has(c.id));
  state.conversations = [...fresh, ...state.conversations];
  persist();
  return fresh.length;
}
export function saveChecklist(draft: Checklist) {
  const version = Math.max(...state.checklists.map((c) => c.version)) + 1;
  const saved = {
    ...clone(draft),
    id: `checklist-${Date.now()}`,
    version,
    createdAt: new Date().toISOString(),
  };
  state.checklists.push(saved);
  persist();
  return saved;
}
export function evaluate(id: string, checklistId: string) {
  const c = state.conversations.find((c) => c.id === id);
  const checklist = state.checklists.find((c) => c.id === checklistId);
  if (!c || !checklist) return null;
  const evaluation = createDemoEvaluation(c, checklist, c.evaluations.length);
  c.evaluations.push(evaluation);
  persist();
  return evaluation;
}
export function submitAppeal(
  input: Omit<Appeal, "id" | "createdAt" | "status">,
) {
  if (
    state.appeals.some(
      (a) =>
        a.evaluationId === input.evaluationId &&
        a.criterionId === input.criterionId,
    )
  )
    return null;
  const appeal: Appeal = {
    ...input,
    id: `appeal-${Date.now()}`,
    status: "open",
    createdAt: new Date().toISOString(),
  };
  state.appeals.unshift(appeal);
  persist();
  return appeal;
}
export function resolveAppeal(
  id: string,
  decision: "confirm" | "change",
  value: number | null,
  reason: string,
) {
  const a = state.appeals.find((a) => a.id === id && a.status === "open");
  if (!a || !reason.trim()) return false;
  const c = state.conversations.find((c) => c.id === a.conversationId);
  const e = c?.evaluations.find((e) => e.id === a.evaluationId);
  const criterion = e?.checklist.criteria.find((c) => c.id === a.criterionId);
  if (!criterion) return false;
  if (decision === "change" && !validValue(value, criterion)) return false;
  Object.assign(a, {
    status: "resolved",
    decision,
    value: decision === "change" ? value : a.originalValue,
    reason: reason.trim(),
    resolvedAt: new Date().toISOString(),
  });
  persist();
  return true;
}
