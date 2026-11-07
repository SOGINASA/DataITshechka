"""Versioned missing-greeting policy and preservation of previous human review."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Store, calculate_score, read_json
from upgrade_voice_policy import migrate
from import_voice_preannotations import AUTHOR

DIRECTORY = Path(__file__).resolve().parents[1]


class VoicePolicyTests(unittest.TestCase):
    def test_na_excludes_contact_weight_without_changing_chat_policy(self):
        voice = read_json(DIRECTORY / 'checklist.voice.v2.json')
        old = read_json(DIRECTORY / 'checklist.voice.json')
        chat = read_json(DIRECTORY / 'checklist.official.json')
        self.assertTrue(voice['criteria'][0]['na_allowed'])
        self.assertFalse(old['criteria'][0]['na_allowed'])
        self.assertFalse(chat['criteria'][0]['na_allowed'])
        self.assertIn('полностью', voice['criteria'][0]['na_rule'])
        self.assertNotIn('???', json.dumps(voice, ensure_ascii=False))
        labels = [{'criterion_id': c['id'], 'verdict': 'score' if c['type'] == 'ordinal' else 'fail',
                   'score': max(c['allowed_scores']) if c['type'] == 'ordinal' else None} for c in voice['criteria']]
        labels[0]['verdict'] = 'na'
        summary = calculate_score(voice, labels)
        self.assertEqual(summary['applicable_weight'], 90)

    def test_migration_never_claims_confirmation_of_proposed_na(self):
        # Existing fixture release is private; skip only this local integration check if absent.
        dataset = DIRECTORY.parent / 'data/raw/dev.json'
        annotations = DIRECTORY.parent / 'data/annotations'
        if not dataset.exists():
            self.skipTest('Private dataset not available')
        source = Store(dataset, annotations, DIRECTORY / 'checklist.voice.json', use_active_checklist=False)
        original = source.load('p4-ru-002', AUTHOR)
        if original is None:
            self.skipTest('Private annotation not available')
        with tempfile.TemporaryDirectory() as output:
            target = Store(dataset, output, DIRECTORY / 'checklist.voice.v2.json', use_active_checklist=False)
            saved = migrate(source, target, 'p4-ru-002')
            contact = saved['labels'][0]
            self.assertEqual(contact['verdict'], 'na')
            self.assertFalse(contact['human_checked'])
            self.assertFalse(saved['reviewed'])
            self.assertFalse(target.eligibility(saved))
            self.assertEqual(saved['labels'][1:], original['labels'][1:])
            self.assertEqual(source.load('p4-ru-002', AUTHOR), original)
            self.assertEqual(migrate(source, target, 'p4-ru-002'), saved)


if __name__ == '__main__':
    unittest.main()
