export type Language = "RU" | "KZ" | "EN";
export type Channel = "agent chat" | "voice call";
export interface Message {
  id?: string;
  startMs?: number | null;
  timestamp: string;
  speaker: "client" | "operator" | "bot" | "system";
  text: string;
}
export interface Criterion {
  rule?: { type: string; speaker?: string; terms?: Record<string, string[]> };
  critical?: boolean;
  requireEvidence?: boolean;
  id: string;
  name: string;
  section: string;
  prompt: string;
  weight: number;
  type: "binary" | "scale" | "flag";
  min: number;
  max: number;
  steps: number[];
  stepDescriptions: Record<string, string>;
  allowNA: boolean;
  naCondition: string;
}
export interface Checklist {
  id: string;
  name: string;
  version: number | string;
  description?: string;
  criteria: Criterion[];
  createdAt: string;
}
export interface CriterionResult {
  status?: "pass" | "fail" | "scored" | "not_applicable" | "needs_review";
  criterionId: string;
  value: number | null;
  explanation: string;
  evidence: number[];
}
export interface Evaluation {
  revision?: number;
  originalResults?: CriterionResult[];
  serverScore?: number | null;
  serverOriginalScore?: number | null;
  partialScore?: number | null;
  coverage?: number;
  needsReview?: boolean;
  id: string;
  checklist: Checklist;
  results: CriterionResult[];
  createdAt: string;
}
export interface Conversation {
  externalId?: string | null;
  id: string;
  title: string;
  operator: string;
  channel: Channel;
  language: Language;
  date: string;
  duration: string;
  transcript: Message[];
  audioUrl: string | null;
  evaluations: Evaluation[];
  seeded?: boolean;
}
export interface Appeal {
  originalStatus?: CriterionResult["status"];
  originalExplanation?: string;
  originalEvidenceIds?: string[];
  decisionStatus?: CriterionResult["status"];
  id: string;
  conversationId: string;
  evaluationId: string;
  criterionId: string;
  originalValue: number | null;
  comment: string;
  status: "open" | "resolved";
  createdAt: string;
  decision?: "confirm" | "change";
  value?: number | null;
  reason?: string;
  resolvedAt?: string;
}
