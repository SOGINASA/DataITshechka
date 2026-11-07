import type { Appeal, Checklist, Conversation, Criterion, CriterionResult, Evaluation } from "./types.js";

export interface ApiCriterion {
  id: string; title: string; description: string; section: string; weight: number;
  answer_type: Criterion["type"]; allow_na: boolean; na_condition: string;
  scale: {value: number; label: string}[];
  rule: NonNullable<Criterion["rule"]>; critical: boolean; require_evidence: boolean;
}
export interface ApiChecklist {
  id: string; name: string; version: string; description: string; created_at: string; criteria: ApiCriterion[];
}
export interface ApiConversation {
  id: string; external_id: string | null; title: string; operator_name: string | null;
  channel: "chat" | "call"; language: "ru" | "kk" | "en"; recording_url: string | null; created_at: string;
  messages: {id: string; speaker: Conversation["transcript"][number]["speaker"]; text: string; start_ms: number | null}[];
}
export interface ApiResult {
  criterion_id: string; value: number | boolean | null; status: CriterionResult["status"];
  explanation: string; evidence: {message_id: string}[];
}
export interface ApiEvaluation {
  id: string; checklist_id: string; conversation_id: string; revision: number; created_at: string;
  results: ApiResult[]; original_results: ApiResult[]; final_score: number | null;
  score: number | null; coverage: number; needs_review: boolean;
  original_summary: {final_score: number | null};
}
export interface ApiReview {
  id: string; comment: string; changes: {criterion_id: string; after: ApiResult}[];
}
export interface ApiAppeal {
  id: string; evaluation_id: string; criterion_id: string; disputed_result: ApiResult;
  comment: string; status: Appeal["status"]; created_at: string; resolved_at: string | null;
  decision: Appeal["decision"] | null; review_id: string | null;
}
export interface ApiExport {
  conversation: ApiConversation; checklist: ApiChecklist; evaluation: ApiEvaluation;
  appeals: ApiAppeal[]; reviews: ApiReview[];
}
export const numericValue = (value: ApiResult["value"]) => typeof value === "boolean" ? Number(value) : value;
export function mapChecklist(raw: ApiChecklist): Checklist {
  return { id: raw.id, name: raw.name, version: raw.version, description: raw.description, createdAt: raw.created_at,
    criteria: raw.criteria.map(c => ({ id: c.id, name: c.title, prompt: c.description, section: c.section,
      weight: c.weight, type: c.answer_type, min: 0,
      max: c.answer_type === "scale" ? Math.max(...c.scale.map(s => s.value)) : 1,
      steps: c.answer_type === "scale" ? c.scale.map(s => s.value) : [0, 1],
      stepDescriptions: Object.fromEntries(c.scale.map(s => [String(s.value), s.label])),
      allowNA: c.allow_na, naCondition: c.na_condition, rule: structuredClone(c.rule),
      critical: c.critical, requireEvidence: c.require_evidence })) };
}
export function checklistPayload(draft: Checklist) {
  return { name: draft.name, description: draft.description || "", criteria: draft.criteria.map(c => ({
    id: c.id, title: c.name, description: c.prompt, section: c.section, weight: c.weight,
    answer_type: c.type, allow_na: c.allowNA, na_condition: c.naCondition,
    scale: c.type === "scale" ? [...c.steps].sort((a,b) => a-b).map(value => ({value, label: c.stepDescriptions[value]})) : [],
    critical: c.critical ?? c.type === "flag", require_evidence: c.requireEvidence ?? true,
    rule: c.rule || {type: "semantic"},
  })) };
}
function clock(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
export function mapConversation(raw: ApiConversation): Conversation {
  return { id: raw.id, externalId: raw.external_id, title: raw.title, operator: raw.operator_name || "Не указан",
    channel: raw.channel === "call" ? "voice call" : "agent chat",
    language: ({ru: "RU", kk: "KZ", en: "EN"} as const)[raw.language], date: raw.created_at,
    audioUrl: safeAudioUrl(raw.recording_url), duration: raw.messages.length && raw.messages[raw.messages.length - 1]?.start_ms != null ? clock(raw.messages[raw.messages.length - 1]!.start_ms!) : "—",
    transcript: raw.messages.map(m => ({id: m.id, speaker: m.speaker, text: m.text, startMs: m.start_ms,
      timestamp: m.start_ms === null ? "—" : clock(m.start_ms)})), evaluations: [] };
}
function safeAudioUrl(value: string | null) {
  if (!value) return null;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}
export function mapEvaluation(raw: ApiEvaluation, checklist: Checklist, conversation: Conversation): Evaluation {
  const results = (items: ApiResult[]): CriterionResult[] => items.map(r => ({
    criterionId: r.criterion_id, value: numericValue(r.value), status: r.status, explanation: r.explanation,
    evidence: r.evidence.map(e => conversation.transcript.findIndex(m => m.id === e.message_id)).filter(i => i >= 0),
  }));
  return { id: raw.id, checklist, createdAt: raw.created_at, revision: raw.revision,
    results: results(raw.results), originalResults: results(raw.original_results),
    serverScore: raw.final_score, serverOriginalScore: raw.original_summary.final_score,
    partialScore: raw.score, coverage: raw.coverage, needsReview: raw.needs_review };
}
export function mapAppeal(raw: ApiAppeal, conversationId: string, review?: ApiReview): Appeal {
  const after = review?.changes.find(c => c.criterion_id === raw.criterion_id)?.after;
  return {id: raw.id, conversationId, evaluationId: raw.evaluation_id, criterionId: raw.criterion_id,
    originalValue: numericValue(raw.disputed_result.value), originalStatus: raw.disputed_result.status,
    originalExplanation: raw.disputed_result.explanation, originalEvidenceIds: raw.disputed_result.evidence.map(e => e.message_id),
    decisionStatus: after?.status,
    comment: raw.comment, status: raw.status, createdAt: raw.created_at,
    decision: raw.decision || undefined, value: after ? numericValue(after.value) : undefined,
    reason: review?.comment, resolvedAt: raw.resolved_at || undefined};
}
export function conversationPayload(c: Conversation) {
  const clockKinds = new Set(c.transcript.filter(m => m.startMs === undefined).map(m => m.timestamp.includes("T") ? "iso" : "relative"));
  if (clockKinds.size > 1) throw new Error("В одном диалоге нельзя смешивать ISO-даты и относительное время.");
  let firstIso: number | undefined;
  let previous = -1;
  return { external_id: c.externalId || c.id, title: c.title, operator_name: c.operator,
    channel: c.channel === "voice call" ? "call" : "chat", language: ({RU:"ru", KZ:"kk", EN:"en"} as const)[c.language],
    recording_url: c.audioUrl, messages: c.transcript.map((m, index) => {
      let start: number | null = m.startMs ?? null;
      if (m.startMs === undefined) {
        if (/^\d+:\d{2}(?::\d{2})?$/.test(m.timestamp)) {
          const parts = m.timestamp.split(":").map(Number);
          if (parts.slice(1).some(n => n >= 60)) throw new Error(`Некорректное время реплики ${index + 1}.`);
          start = parts.reduce((n, p) => n * 60 + p, 0) * 1000;
        } else if (/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(m.timestamp)) {
          const time = Date.parse(m.timestamp);
          if (!Number.isFinite(time)) throw new Error(`Некорректная дата реплики ${index + 1}.`);
          firstIso ??= time; start = time - firstIso;
        } else throw new Error(`Реплика ${index + 1}: укажите время MM:SS, HH:MM:SS или ISO с часовым поясом.`);
      }
      if (start !== null) {
        if (!Number.isInteger(start) || start < previous || start < 0 || start > 86400000)
          throw new Error("Реплики должны идти по возрастанию времени в пределах суток.");
        previous = start;
      }
      return {id: m.id || String(index + 1), speaker: m.speaker, text: m.text, start_ms: start};
    }) };
}
