import type { Appeal, Criterion, Evaluation, CriterionResult } from "./types.js";
export function normalized(value: number, criterion: Criterion) {
  return criterion.max > 0
    ? Math.max(0, Math.min(1, value / criterion.max))
    : 0;
}
export function isAssessed(evaluation: Evaluation | undefined) {
  return !!evaluation && !evaluation.results.some(r => r.status === "needs_review");
}
export function finalValue(
  evaluation: Evaluation,
  criterionId: string,
  appeals: Appeal[],
) {
  const original =
    evaluation.results.find((r) => r.criterionId === criterionId)?.value ??
    null;
  if (evaluation.revision !== undefined) return original;
  const decision = appeals.find(
    (a) =>
      a.evaluationId === evaluation.id &&
      a.criterionId === criterionId &&
      a.status === "resolved",
  );
  return decision?.decision === "change" ? (decision.value ?? null) : original;
}
export function score(
  evaluation: Evaluation | undefined,
  appeals: Appeal[] = [],
  original = false,
): number | null {
  if (!evaluation) return null;
  if (evaluation.revision !== undefined)
    return original ? evaluation.serverOriginalScore ?? null : evaluation.serverScore ?? null;
  let weight = 0,
    total = 0;
  for (const criterion of evaluation.checklist.criteria) {
    if (criterion.type === "flag" || criterion.weight <= 0) continue;
    const value = original
      ? (evaluation.results.find((r) => r.criterionId === criterion.id)
          ?.value ?? null)
      : finalValue(evaluation, criterion.id, appeals);
    if (value !== null) {
      weight += criterion.weight;
      total += normalized(value, criterion) * criterion.weight;
    }
  }
  return weight > 0
    ? Math.round(((total / weight) * 100 + Number.EPSILON) * 100) / 100
    : null;
}
export const formatScore = (value: number | null) =>
  value === null
    ? "—"
    : value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
export const scoreTone = (value: number | null) =>
  value === null
    ? "neutral"
    : value >= 85
      ? "success"
      : value >= 70
        ? "warning"
        : "danger";
export function answerLabel(value: number | null, criterion: Criterion, status?: CriterionResult["status"]) {
  if (status === "needs_review") return "Не оценено";
  return value === null
    ? "N/A"
    : criterion.type === "flag"
      ? value === 1
        ? "Нарушение"
        : "Не выявлено"
      : criterion.type === "binary"
        ? value === 1
          ? "Да"
          : "Нет"
        : `${value} из ${criterion.max}`;
}
export function validValue(value: number | null, criterion: Criterion) {
  return value === null
    ? criterion.allowNA
    : Number.isFinite(value) && criterion.steps.includes(value);
}
