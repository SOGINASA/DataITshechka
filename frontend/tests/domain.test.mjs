import test from "node:test";
import assert from "node:assert/strict";
import { initialChecklist } from "../dist/js/checklist.js";
import { createDemoEvaluation, initialConversations } from "../dist/js/data.js";
import { score, validValue } from "../dist/js/scoring.js";
import { parseImport, importExample } from "../dist/js/import.js";
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
  const detect = (language, text) => parseImport(JSON.stringify([{...record, language, transcript: [{timestamp: "00:00", speaker: "client", text}]}]))[0].language;
  assert.equal(detect(undefined, "Қай жерін басамын? Иә, қосыңызшы"), "KZ");
  assert.equal(detect(undefined, "Здравствуйте, где настройки?"), "RU");
  assert.equal(detect(undefined, "Hello, where are settings?"), "EN");
  assert.equal(detect("EN", "Здравствуйте"), "EN");
  const ml2Record = parseImport(JSON.stringify({conversation_id: "p1-kz-010", channel: "chat", language: "kk", messages: [{id: "m1", timestamp: "00:00", speaker: "client", text: "Қай жерін басамын?"}]}))[0];
  assert.equal(ml2Record.language, "KZ");
  assert.equal(ml2Record.channel, "agent chat");
  assert.equal(ml2Record.transcript[0].id, "m1");
  assert.equal(
    parseImport(JSON.stringify({ data: { records: [record] } })).length,
    1,
  );
  assert.equal(parseImport(JSON.stringify(record)).length, 1);
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
test("focused review prioritizes weighted loss and independent gross flag", async () => {
  const { focusCriterion } = await import("../dist/js/review.js");
  const e = fullEvaluation();
  e.results.find((r) => r.criterionId === "identity").value = 0;
  e.results.find((r) => r.criterionId === "consultation").value = 15;
  assert.equal(focusCriterion(e).id, "identity");
  e.results.find((r) => r.criterionId === "identity").value = null;
  assert.equal(focusCriterion(e).id, "consultation");
  e.results.find((r) => r.criterionId === "gross").value = 1;
  assert.equal(focusCriterion(e).id, "gross");
  assert.equal(focusCriterion(e, "closing").id, "closing");
});

test("demo audio attaches only to the unchanged known transcript", async () => {
  const { usesDemoAudio, elapsed } = await import("../dist/js/review.js");
  const c = structuredClone(initialConversations[0]);
  assert.equal(usesDemoAudio(c), true);
  assert.equal(elapsed(c, 7), 138);
  c.transcript[0].text = "Other conversation";
  assert.equal(usesDemoAudio(c), false);
  c.audioUrl = "https://example.com/real-audio.m4a";
  assert.equal(usesDemoAudio(c), false);
});

test("section contributions include custom and blank sections without dropping weight", async () => {
  const { sectionContributions, qualityView } =
    await import("../dist/js/review.js");
  const e = fullEvaluation();
  e.checklist.criteria.forEach((criterion, index) => {
    criterion.section = index === 0 ? "" : `Section ${index}`;
  });
  const sections = sectionContributions(e, []);
  assert.equal(sections.length, 7);
  assert.deepEqual(sections[0], { name: "Критерии", earned: 10, max: 10 });
  assert.equal(
    sections.reduce((sum, section) => sum + section.earned, 0),
    100,
  );
  const markup = qualityView(
    { ...initialConversations[0], evaluations: [e] },
    e,
  );
  assert.match(markup, /Section 6/);
  assert.match(markup, /Ещё секций: 4/);
});

test("appeal route keeps historical evaluation and criterion with validated fallbacks", async () => {
  const { selectionFromQuery } = await import("../dist/js/review.js");
  const old = fullEvaluation();
  const newer = structuredClone(old);
  newer.id = "new-evaluation";
  newer.checklist.criteria = newer.checklist.criteria.filter(
    (c) => c.id !== "identity",
  );
  const conversation = {
    ...initialConversations[0],
    evaluations: [old, newer],
  };
  const query = new URLSearchParams({
    evaluationId: old.id,
    criterionId: "identity",
  }).toString();
  assert.deepEqual(selectionFromQuery(conversation, query), {
    evaluationId: old.id,
    criterionId: "identity",
  });
  assert.deepEqual(
    selectionFromQuery(conversation, "evaluationId=other&criterionId=identity"),
    { evaluationId: "", criterionId: "" },
  );
  assert.deepEqual(
    selectionFromQuery(
      conversation,
      `evaluationId=${old.id}&criterionId=unknown`,
    ),
    { evaluationId: old.id, criterionId: "" },
  );
});
