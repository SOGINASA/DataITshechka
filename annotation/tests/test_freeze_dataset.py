import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freeze_dataset import freeze_release


class FrozenDatasetTests(unittest.TestCase):
    def bundle(self):
        annotation = {"conversation_id": "one", "language": "RU", "channel": "voice call",
                      "checklist_hash": "rubric", "revision": 3, "reviewed": True,
                      "assessment_context": {"audio_reviewed": True},
                      "labels": [{"verdict": "pass", "human_checked": True, "reason": "reference-only-text"}]}
        return {"checklists": {"rubric": {"criteria": []}}, "annotations": [annotation],
                "records": [{"conversation_id": "one", "language": "RU", "channel": "voice call",
                             "content_hash": "source", "audio_url": "https://recording.invalid/?signature=secret-test",
                             "transcript": [{"turn_id": "t0001", "speaker": "operator", "timestamp": "00:01", "text": "Здравствуйте"}]}]}

    def test_inputs_do_not_contain_labels_or_signed_recording_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            release = freeze_release(self.bundle(), temp, "v1")
            text = (Path(temp) / "v1/inputs.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("reference-only-text", text)
            self.assertNotIn("secret-test", text)
            self.assertNotIn('"audio_url"', text)
            self.assertFalse(json.loads(text)["assessment_scope"]["audio_supplied_to_model"])
            self.assertEqual(release["summary"]["audio_reviewed_calls"], 1)

    def test_same_release_is_idempotent_and_changed_source_needs_new_version(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = self.bundle()
            first = freeze_release(bundle, temp, "v1")
            self.assertEqual(first, freeze_release(bundle, temp, "v1"))
            changed = copy.deepcopy(bundle)
            changed["annotations"][0]["revision"] += 1
            with self.assertRaisesRegex(ValueError, "frozen"):
                freeze_release(changed, temp, "v1")

    def test_tampered_release_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = self.bundle()
            freeze_release(bundle, temp, "v1")
            (Path(temp) / "v1/references.jsonl").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "modified"):
                freeze_release(bundle, temp, "v1")

    def test_version_cannot_escape_release_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            for version in ("../outside", "..", "C:\\outside", "/outside"):
                with self.subTest(version=version), self.assertRaises(ValueError):
                    freeze_release(self.bundle(), temp, version)


if __name__ == "__main__":
    unittest.main()
