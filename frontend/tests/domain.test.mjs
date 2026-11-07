import test from "node:test";
import assert from "node:assert/strict";
import { initialChecklist } from "../dist/js/checklist.js";
import { createDemoEvaluation, initialConversations } from "../dist/js/data.js";
import { score, validValue } from "../dist/js/scoring.js";
import { parseImport, importExample } from "../dist/js/import.js";
import {
  getState,
  resolveAppeal,
  saveChecklist,
  persist,
  getPersistenceWarning,
} from "../dist/js/state.js";
function fullEvaluation() {
  return {
    id: "test-eval",
    checklist: structuredClone(initialChecklist),
    results: initialChecklist.criteria.map((c) => ({
      criterionId: c.id,
      value: c.type === "flag" ? 0 : c.max,
      explanation: "",
      evidence: [],
    })),
    createdAt: "2026-11-07T12:00:00+05:00",
  };
}
test("official weights, discrete steps and unscored flag are preserved", () => {
  assert.deepEqual(
    initialChecklist.criteria.map((c) => c.weight),
    [10, 15, 20, 20, 15, 15, 5, 0],
  );
  const management = initialChecklist.criteria.find(
    (c) => c.id === "management",
  );
  assert.deepEqual(management.steps, [0, 4, 7, 10]);
  assert.equal(validValue(8, management), false);
  assert.equal(validValue(7, management), true);
  assert.equal(validValue(null, management), false);
  const identity = initialChecklist.criteria.find((c) => c.id === "identity");
  assert.equal(validValue(null, identity), true);
});
test("N/A redistributes weight, scales normalize and result rounds to two decimals", () => {
  const e = fullEvaluation();
  e.results.find((r) => r.criterionId === "need").value = null;
  e.results.find((r) => r.criterionId === "identity").value = null;
  e.results.find((r) => r.criterionId === "management").value = 7;
  assert.equal(score(e), 93.08);
  e.results.find((r) => r.criterionId === "gross").value = 1;
  assert.equal(score(e), 93.08, "gross violation must not zero the total");
});
test("no applicable weighted criteria gives null", () => {
  const e = fullEvaluation();
  e.results.forEach((r) => {
    r.value = null;
  });
  assert.equal(score(e), null);
});
test("appeal changes final score without changing original result", () => {
  const e = fullEvaluation();
  e.results.find((r) => r.criterionId === "management").value = 7;
  const appeal = {
    id: "a",
    conversationId: "c",
    evaluationId: e.id,
    criterionId: "management",
    originalValue: 7,
    status: "resolved",
    decision: "change",
    value: 10,
    comment: "Check",
    reason: "Reviewed",
  };
  assert.equal(score(e, [appeal]), 100);
  assert.equal(score(e, [appeal], true), 95.5);
  assert.equal(e.results.find((r) => r.criterionId === "management").value, 7);
});
test("evaluation config is an immutable snapshot including N/A and scale rubrics", () => {
  const checklist = structuredClone(initialChecklist);
  const e = createDemoEvaluation(initialConversations[0], checklist);
  checklist.criteria[1].naCondition = "Changed";
  checklist.criteria[3].stepDescriptions["20"] = "Changed";
  checklist.criteria[3].steps.push(17);
  assert.notEqual(e.checklist.criteria[1].naCondition, "Changed");
  assert.notEqual(e.checklist.criteria[3].stepDescriptions["20"], "Changed");
  assert.equal(e.checklist.criteria[3].steps.includes(17), false);
});
test("imports accept organizer envelope and reject malformed roles, duplicates, unsafe audio", () => {
  const record = JSON.parse(importExample)[0];
  assert.equal(
    parseImport(JSON.stringify({ data: { records: [record] } })).length,
    1,
  );
  assert.throws(
    () => parseImport(JSON.stringify([record, record])),
    /повторяется/,
  );
  assert.throws(
    () =>
      parseImport(
        JSON.stringify([{ ...record, audio_url: "javascript:alert(1)" }]),
      ),
    /audio_url/,
  );
  assert.throws(
    () =>
      parseImport(
        JSON.stringify([
          {
            ...record,
            transcript: [
              { timestamp: "00:00", speaker: "admin", text: "Hello" },
            ],
          },
        ]),
      ),
    /speaker/,
  );
  assert.throws(() => parseImport("{}"), /массив/);
});
test("review decision rejects unsupported scale steps and protects resolved appeals", () => {
  const state = getState();
  const a = state.appeals.find((a) => a.criterionId === "consultation");
  assert.equal(resolveAppeal(a.id, "change", 17, "Invalid step"), false);
  assert.equal(a.status, "open");
  assert.equal(
    resolveAppeal(a.id, "change", 20, "Полный ответ подтверждён контекстом."),
    true,
  );
  assert.equal(resolveAppeal(a.id, "change", 0, "Overwrite"), false);
  assert.equal(a.value, 20);
});
test("saving checklist creates a separate version without mutating old config", () => {
  const before = structuredClone(getState().checklists[0]);
  const draft = structuredClone(before);
  draft.criteria[0].name = "Updated";
  const saved = saveChecklist(draft);
  draft.criteria[0].name = "Another change";
  assert.equal(saved.version, 2);
  assert.equal(saved.criteria[0].name, "Updated");
  assert.deepEqual(getState().checklists[0], before);
});

test("storage failures are exposed as an explicit nonpersistent warning", () => {
  const descriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    "localStorage",
  );
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      setItem() {},
      getItem() {
        return null;
      },
    },
  });
  assert.equal(persist(), true);
  assert.equal(getPersistenceWarning(), null);
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      setItem() {
        throw new Error("Quota exceeded");
      },
    },
  });
  assert.equal(persist(), false);
  assert.match(getPersistenceWarning(), /только в этой вкладке/);
  if (descriptor) Object.defineProperty(globalThis, "localStorage", descriptor);
  else Reflect.deleteProperty(globalThis, "localStorage");
});
