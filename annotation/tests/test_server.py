import copy
from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Store, ThreadingHTTPServer, calculate_score, handler_for, read_json, validate_checklist
from build_voice_checklist import build_voice_checklist
from review import build_queue, open_task


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = self.root / "dev.json"
        self.record = {
            "conversation_id": "dialogue/../one", "language": "RU", "channel": "agent chat",
            "audio_url": None, "transcript": [
                {"speaker": "bot", "timestamp": "00:00", "text": "Здравствуйте, я бот"},
                {"speaker": "operator", "timestamp": "00:01", "text": "Здравствуйте, я Алия"},
                {"speaker": "client", "timestamp": "00:02", "text": "Спасибо"},
            ]}
        self.dataset.write_text(json.dumps({"isSuccess": True, "data": {"records": [self.record]}}), encoding="utf-8")
        self.example = Path(__file__).resolve().parents[1] / "checklist.example.json"
        self.store = Store(self.dataset, self.root / "labels", self.example)
        self.checklist = read_json(self.example)
        self.checklist["criteria"] = [self.checklist["criteria"][0]]
        self.store.set_checklist(self.checklist)

    def tearDown(self):
        self.temp.cleanup()

    def payload(self, **changes):
        p = {"conversation_id": self.record["conversation_id"], "annotator": "Алия",
             "checklist_hash": self.store.checklist_hash,
             "content_hash": self.store.record(self.record["conversation_id"])["content_hash"],
             "revision": 0, "status": "complete", "reviewed": False, "reviewer": "",
             "labels": [{"criterion_id": "opening", "verdict": "pass", "score": None,
                         "reason": "Оператор приветствовал и представился.", "confidence": "high",
                         "evidence_turn_ids": ["t0002"], "checked_span": None}]}
        p.update(changes)
        return p

    def test_utf8_evidence_round_trip_and_hashed_paths(self):
        saved = self.store.save(self.payload())
        loaded = self.store.load(self.record["conversation_id"], "Алия")
        self.assertEqual(saved, loaded)
        self.assertEqual(loaded["labels"][0]["evidence"][0]["text"], "Здравствуйте, я Алия")
        path = self.store.annotation_path(self.record["conversation_id"], "Алия")
        self.assertTrue(path.is_relative_to(self.root / "labels"))
        self.assertNotIn("..", str(path.relative_to(self.root / "labels")))

    def test_positive_answer_cannot_credit_bot_only(self):
        p = self.payload()
        p["labels"][0]["evidence_turn_ids"] = ["t0001"]
        with self.assertRaisesRegex(ValueError, "operator"):
            self.store.save(p)

    def test_cannot_invent_evidence(self):
        p = self.payload()
        p["labels"][0]["evidence_turn_ids"] = ["t9999"]
        with self.assertRaisesRegex(ValueError, "несуществующую"):
            self.store.save(p)

    def test_missing_action_needs_searched_span(self):
        p = self.payload()
        label = p["labels"][0]
        label.update(verdict="fail", evidence_turn_ids=[], reason="Представление пропущено.")
        with self.assertRaisesRegex(ValueError, "участок"):
            self.store.save(p)
        label["checked_span"] = {"start_turn_id": "t0001", "end_turn_id": "t0003"}
        self.assertEqual(self.store.save(p)["labels"][0]["verdict"], "fail")

    def test_reverse_span_is_rejected(self):
        p = self.payload(status="draft")
        p["labels"][0]["checked_span"] = {"start_turn_id": "t0003", "end_turn_id": "t0001"}
        with self.assertRaisesRegex(ValueError, "границы"):
            self.store.save(p)

    def test_na_is_not_allowed_when_criterion_forbids_it(self):
        self.checklist["criteria"][0]["na_allowed"] = False
        self.store.set_checklist(self.checklist)
        p = self.payload()
        p["labels"][0]["verdict"] = "na"
        with self.assertRaisesRegex(ValueError, "Недопустимый"):
            self.store.save(p)

    def test_draft_can_be_empty_but_complete_cannot(self):
        p = self.payload(status="draft")
        p["labels"][0].update(verdict="", reason="", evidence_turn_ids=[])
        saved = self.store.save(p)
        p.update(status="complete", revision=saved["revision"])
        with self.assertRaisesRegex(ValueError, "Заполните"):
            self.store.save(p)

    def test_stale_revision_rejected_and_history_preserved(self):
        first = self.store.save(self.payload())
        with self.assertRaisesRegex(ValueError, "другой вкладке"):
            self.store.save(self.payload())
        second = self.store.save(self.payload(revision=1))
        self.assertEqual(second["revision"], 2)
        path = self.store.annotation_path(self.record["conversation_id"], "Алия")
        self.assertEqual(read_json(path.parent / "history" / f"{path.stem}-1.json"), first)
        self.assertEqual(len(self.store.all_annotations()), 1)

    def test_changed_transcript_or_checklist_cannot_reuse_labels(self):
        p = self.payload(content_hash="obsolete")
        with self.assertRaisesRegex(ValueError, "Транскрипт изменился"):
            self.store.save(p)
        p = self.payload(checklist_hash="obsolete")
        with self.assertRaisesRegex(ValueError, "Чек-лист изменился"):
            self.store.save(p)

    def test_demo_and_uncertain_annotations_never_become_reference(self):
        saved = self.store.save(self.payload(reviewed=True, reviewer="Данияр"))
        self.assertFalse(self.store.eligibility(saved))
        self.checklist["status"] = "official"
        self.store.set_checklist(self.checklist)
        p = self.payload()
        p["labels"][0].update(verdict="uncertain", reason="Нужен официальный источник.", evidence_turn_ids=[])
        saved = self.store.save(p)
        self.assertFalse(self.store.eligibility(saved))
        p.update(reviewed=True, reviewer="Данияр", revision=1)
        with self.assertRaisesRegex(ValueError, "спорные"):
            self.store.save(p)

    def test_reference_requires_independent_review_and_current_content(self):
        self.checklist["status"] = "official"
        self.store.set_checklist(self.checklist)
        with self.assertRaisesRegex(ValueError, "другой человек"):
            self.store.save(self.payload(reviewed=True, reviewer="АЛИЯ"))
        saved = self.store.save(self.payload(reviewed=True, reviewer="Данияр"))
        self.assertTrue(self.store.eligibility(saved))
        exported = self.store.export()
        self.assertTrue(exported["annotations"][0]["eligible_for_reference"])
        saved["content_hash"] = "old"
        self.assertFalse(self.store.eligibility(saved))

    def test_ai_example_never_claims_human_reference(self):
        self.checklist["status"] = "official"
        self.store.set_checklist(self.checklist)
        for origin in ("ai_example", "ai_preannotation"):
            with self.subTest(origin=origin):
                saved = self.store.save(self.payload(origin=origin, annotator=origin, reviewed=True, reviewer="Данияр"))
                self.assertEqual(saved["origin"], origin)
                self.assertFalse(self.store.eligibility(saved))

    def test_checklist_for_other_channel_is_not_reference(self):
        self.checklist.update(status="official", applicable_channels=["voice call"])
        self.store.set_checklist(self.checklist)
        saved = self.store.save(self.payload(reviewed=True, reviewer="Данияр"))
        self.assertFalse(self.store.eligibility(saved))

    def test_identification_can_use_system_confirmation(self):
        self.record["transcript"][0]["speaker"] = "system"
        self.dataset.write_text(json.dumps({"isSuccess": True, "data": {"records": [self.record]}}), encoding="utf-8")
        self.store = Store(self.dataset, self.root / "labels", self.example)
        self.checklist["criteria"][0]["positive_evidence_roles"] = ["operator", "system"]
        self.store.set_checklist(self.checklist)
        p = self.payload()
        p["labels"][0]["evidence_turn_ids"] = ["t0001"]
        self.assertEqual(self.store.save(p)["labels"][0]["verdict"], "pass")

    def test_separate_annotators_and_checklist_versions(self):
        self.store.save(self.payload())
        self.store.save(self.payload(annotator="Данияр"))
        self.assertEqual(len(self.store.all_annotations()), 2)
        old_hash = self.store.checklist_hash
        self.checklist["version"] = "demo-2"
        self.store.set_checklist(self.checklist)
        self.assertNotEqual(old_hash, self.store.checklist_hash)
        self.assertIsNone(self.store.load(self.record["conversation_id"], "Алия"))
        self.assertTrue((self.root / "labels" / old_hash).exists())

    def test_zero_score_is_valid_but_boolean_score_is_not(self):
        c = self.checklist["criteria"][0]
        c.update(type="ordinal", allowed_scores=[0, 1, 2])
        self.store.set_checklist(self.checklist)
        p = self.payload()
        p["labels"][0].update(verdict="score", score=False)
        with self.assertRaisesRegex(ValueError, "шкале"):
            self.store.save(p)
        p["labels"][0].update(score=0, evidence_turn_ids=[], checked_span={"start_turn_id": "t0001", "end_turn_id": "t0003"})
        self.assertEqual(self.store.save(p)["labels"][0]["score"], 0)

    def test_bad_checklists_are_rejected(self):
        for scores in ([0], [0, 0], [2, 1], [0, True], [0, float("nan")]):
            candidate = copy.deepcopy(self.checklist)
            candidate["criteria"][0].update(type="ordinal", allowed_scores=scores)
            with self.assertRaises(ValueError):
                validate_checklist(candidate)

    def test_http_endpoints_and_local_origin_boundary(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            for path in ("/", "/app.js", "/style.css", "/api/bootstrap", "/api/export"):
                connection.request("GET", path)
                response = connection.getresponse()
                self.assertEqual(response.status, 200, path)
                self.assertTrue(response.read())
            connection.request("GET", "/.env")
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            connection.request("POST", "/api/annotation", body=json.dumps(self.payload()),
                               headers={"Content-Type": "application/json", "Origin": "https://unrelated.example"})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.request("POST", "/api/annotation", body=json.dumps(self.payload()).encode("utf-8"),
                               headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())["revision"], 1)
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()

    def test_explicit_import_can_ignore_ui_active_checklist(self):
        self.assertEqual(len(self.store.checklist["criteria"]), 1)
        explicit = Store(self.dataset, self.root / "labels", self.example, use_active_checklist=False)
        self.assertEqual(len(explicit.checklist["criteria"]), 8)
        self.assertEqual(len(self.store.checklist["criteria"]), 1)

    def test_profile_switch_preserves_other_namespace(self):
        self.store.save(self.payload())
        old_checklist = copy.deepcopy(self.store.checklist)
        old_hash = self.store.checklist_hash
        self.store.select_profile("voice")
        self.assertEqual(self.store.checklist["applicable_channels"], ["voice call"])
        self.assertNotEqual(self.store.checklist_hash, old_hash)
        self.assertIsNone(self.store.load(self.record["conversation_id"], "Алия"))
        self.assertEqual({p["id"] for p in self.store.profiles()}, {"chat", "voice"})
        with self.assertRaises(ValueError):
            self.store.select_profile("../.env")
        self.store.set_checklist(old_checklist)
        self.assertIsNotNone(self.store.load(self.record["conversation_id"], "Алия"))

    def assessment(self):
        return {"basis": "transcript_only", "audio_reviewed": False,
                "acoustic_observations": {"diction": "not_assessed"},
                "limitations": ["ASR не равен речи оператора"], "excluded_turn_spans": []}

    def test_assessment_basis_round_trip(self):
        context = self.assessment()
        saved = self.store.save(self.payload(assessment_context=context))
        self.assertEqual(saved["assessment_context"], context)
        self.assertEqual(self.store.load(self.record["conversation_id"], "Алия")["assessment_context"], context)

    def test_acoustic_claim_without_listening_rejected(self):
        context = self.assessment()
        context["acoustic_observations"]["diction"] = "плохая"
        with self.assertRaisesRegex(ValueError, "без прослушивания"):
            self.store.save(self.payload(assessment_context=context))
        context = self.assessment()
        context["audio_reviewed"] = True
        with self.assertRaisesRegex(ValueError, "противоречит"):
            self.store.save(self.payload(assessment_context=context))

    def test_internal_hold_evidence_not_credited_as_client_speech(self):
        context = self.assessment()
        context["excluded_turn_spans"] = [{"start_turn_id": "t0002", "end_turn_id": "t0002", "reason": "Внутренний разговор"}]
        with self.assertRaisesRegex(ValueError, "Внутренний"):
            self.store.save(self.payload(assessment_context=context))

    def ai_annotation(self, verdict="pass"):
        self.checklist["status"] = "official"
        self.store.set_checklist(self.checklist)
        p = self.payload(annotator="AI seed", origin="ai_preannotation")
        p["labels"][0]["verdict"] = verdict
        if verdict == "uncertain":
            p["labels"][0]["reason"] = "Нужно проверить по записи."
        return self.store.save(p)

    def confirmation(self, saved):
        p = copy.deepcopy(saved)
        p["human_verification"] = {"basis": "user_confirmation_in_chat", "reviewer": "Пользователь", "independent_second_review_claimed": False}
        p["labels"][0]["human_checked"] = True
        return p

    def test_confirmation_preserves_ai_version_and_original_history(self):
        original = self.ai_annotation()
        saved = self.store.save(self.confirmation(original))
        self.assertEqual(saved["annotator"], original["annotator"])
        self.assertEqual(saved["origin"], "ai_preannotation")
        self.assertEqual(saved["review_baseline"]["labels"], original["labels"])
        self.assertTrue(saved["reviewed"])
        self.assertTrue(self.store.eligibility(saved))
        path = self.store.annotation_path(original["conversation_id"], original["annotator"])
        self.assertEqual(read_json(path.parent / "history" / f"{path.stem}-1.json"), original)
        queue = build_queue(self.store)
        self.assertEqual(queue["counts"]["confirmed"], 1)
        self.assertEqual(queue["tasks"], [])

    def test_uncertain_cannot_be_confirmed_without_final_answer_and_new_reason(self):
        original = self.ai_annotation("uncertain")
        p = self.confirmation(original)
        with self.assertRaisesRegex(ValueError, "Нельзя подтвердить"):
            self.store.save(p)
        p["labels"][0]["verdict"] = "pass"
        with self.assertRaisesRegex(ValueError, "Обновите объяснение"):
            self.store.save(p)
        p["labels"][0]["reason"] = "По проверенной реплике оператор поздоровался и представился."
        self.assertTrue(self.store.save(p)["labels"][0]["human_checked"])

    def test_checked_draft_still_requires_valid_evidence(self):
        original = self.ai_annotation()
        p = self.confirmation(original)
        p["status"] = "draft"
        p["labels"][0].update(evidence_turn_ids=[], checked_span=None)
        with self.assertRaisesRegex(ValueError, "участок"):
            self.store.save(p)

    def test_progress_resumes_and_edit_reopens_only_changed_criterion(self):
        saved = self.store.save(self.confirmation(self.ai_annotation()))
        saved["labels"][0].update(human_checked=False, reason="Проверяю повторно")
        saved["status"] = "draft"
        reopened = self.store.save(saved)
        self.assertFalse(reopened["reviewed"])
        restarted = Store(self.dataset, self.root / "labels", self.example)
        uncertain = build_queue(restarted, "uncertain")
        rest = build_queue(restarted, "remaining")
        self.assertEqual(uncertain["tasks"], [])
        self.assertEqual(len(rest["tasks"]), 1)
        self.assertEqual(rest["counts"]["other_pending"], 1)

    def test_opening_review_does_not_copy_or_modify_annotation(self):
        original = self.ai_annotation("uncertain")
        queue = build_queue(self.store)
        self.assertEqual(len(queue["tasks"]), 1)
        opened = open_task(self.store, queue["tasks"][0])
        self.assertEqual(opened["annotation"], original)
        self.assertEqual(len(self.store.all_annotations()), 1)

    def test_unchecked_confirmation_cannot_complete_dialogue(self):
        original = self.ai_annotation()
        p = self.confirmation(original)
        p["labels"][0]["human_checked"] = False
        with self.assertRaisesRegex(ValueError, "неподтверждённые"):
            self.store.save(p)

    def test_recording_index_and_redirect_use_dataset_link(self):
        cid = self.record["conversation_id"]
        target = "https://audio.example.invalid/recording?token=test-only"
        self.store.records[cid]["audio_url"] = target
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request("GET", "/audio")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            body = response.read().decode("utf-8")
            self.assertIn(quote(cid, safe=""), body)
            self.assertNotIn("token=test-only", body)
            connection.request("GET", "/audio/" + quote(cid, safe=""))
            response = connection.getresponse()
            self.assertEqual(response.status, 302)
            self.assertEqual(response.getheader("Location"), target)
            response.read()
            connection.request("GET", "/api/review/queue?phase=invalid")
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.checklist = validate_checklist(read_json(Path(__file__).resolve().parents[1] / "checklist.official.json"))
        self.labels = []
        for c in self.checklist["criteria"]:
            self.labels.append({"criterion_id": c["id"],
                                "verdict": "fail" if c.get("is_critical") else "pass" if c["type"] == "binary" else "score",
                                "score": max(c["allowed_scores"]) if c["type"] == "ordinal" else None})

    def change(self, cid, **kwargs):
        next(x for x in self.labels if x["criterion_id"] == cid).update(kwargs)

    def test_full_score_and_separate_critical_flag(self):
        self.assertEqual(calculate_score(self.checklist, self.labels)["total"], 100)
        self.change("critical_errors", verdict="pass")
        result = calculate_score(self.checklist, self.labels)
        self.assertEqual(result["total"], 100)
        self.assertTrue(result["critical_errors"])

    def test_voice_adaptation_preserves_weights_and_chat_source(self):
        original = copy.deepcopy(self.checklist)
        voice = build_voice_checklist(self.checklist)
        self.assertEqual(self.checklist, original)
        self.assertEqual(voice["applicable_channels"], ["voice call"])
        self.assertEqual([c["weight"] for c in voice["criteria"]], [c["weight"] for c in original["criteria"]])
        self.assertEqual([c.get("allowed_scores") for c in voice["criteria"]], [c.get("allowed_scores") for c in original["criteria"]])
        self.assertTrue(voice["adaptation_status"].startswith("team_adaptation"))

    def test_na_redistribution_and_two_decimal_rounding(self):
        self.change("needs", verdict="na")
        self.change("identification", verdict="na")
        self.change("closing", verdict="fail")
        result = calculate_score(self.checklist, self.labels)
        self.assertEqual(result["applicable_weight"], 65)
        self.assertEqual(result["earned_before_na"], 60)
        self.assertEqual(result["total"], 92.31)

    def test_raw_management_score_is_scaled_to_weight(self):
        self.change("management", score=7)
        self.assertEqual(calculate_score(self.checklist, self.labels)["total"], 95.5)
        self.change("management", score=0)
        self.assertEqual(calculate_score(self.checklist, self.labels)["total"], 85)

    def test_uncertain_weighted_label_has_no_total(self):
        self.change("consultation", verdict="uncertain", score=None)
        result = calculate_score(self.checklist, self.labels)
        self.assertIsNone(result["total"])
        self.assertEqual(result["pending_criteria"], ["consultation"])

    def test_no_applicable_weights_has_no_total(self):
        checklist = copy.deepcopy(self.checklist)
        checklist["criteria"] = [next(c for c in checklist["criteria"] if c["id"] == "needs")]
        self.change("needs", verdict="na")
        self.assertIsNone(calculate_score(checklist, self.labels)["total"])

    def test_invalid_weights_and_weighted_critical_flag_rejected(self):
        for weight in (-1, True, float("nan")):
            candidate = copy.deepcopy(self.checklist)
            candidate["criteria"][0]["weight"] = weight
            with self.assertRaises(ValueError):
                validate_checklist(candidate)
        candidate = copy.deepcopy(self.checklist)
        candidate["criteria"][-1]["weight"] = 10
        with self.assertRaises(ValueError):
            validate_checklist(candidate)


if __name__ == "__main__":
    unittest.main()
