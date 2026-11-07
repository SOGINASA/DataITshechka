export type Language = "RU" | "KZ" | "EN";
export type Channel = "agent chat" | "voice call";
export interface Message {
  timestamp: string;
  speaker: "client" | "operator" | "bot" | "system";
  text: string;
}
export interface Criterion {
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
  version: number;
  criteria: Criterion[];
  createdAt: string;
}
export interface CriterionResult {
  criterionId: string;
  value: number | null;
  explanation: string;
  evidence: number[];
}
export interface Evaluation {
  id: string;
  checklist: Checklist;
  results: CriterionResult[];
  createdAt: string;
}
export interface Conversation {
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
