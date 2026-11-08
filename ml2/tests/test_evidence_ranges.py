import json
import unittest

from ml2.contracts import ContractError, validate_results
from ml2.decoding import decode, schema_for
from ml2.engine import Evaluator
from test_ml2 import checklist, dialog, wire_answers


def assessment(schema, cid):
    row = schema['properties']['results']['properties'][cid]
    if '$ref' in row:
        row = schema['$defs'][row['$ref'].split('/')[-1]]
    return row


class EvidenceRangeTests(unittest.TestCase):
    def test_schema_limits_evidence_to_server_range(self):
        schema = schema_for(checklist(), dialog(), [])
        ids = lambda cid: assessment(schema, cid)['properties']['evidence_message_ids']['items']['enum']
        self.assertEqual(ids('contact'), ['m1', 'm2'])
        self.assertEqual(ids('closing'), ['m1', 'm2', 'm3'])
        self.assertEqual(ids('gross_errors'), ['m1', 'm2', 'm3'])

    def test_closing_range_uses_positions_not_id_sort_order(self):
        d = dialog()
        d['messages'].extend([
            {'id': 'z', 'speaker': 'client', 'text': 'Спасибо'},
            {'id': 'a', 'speaker': 'operator', 'text': 'До свидания'},
        ])
        schema = schema_for(checklist(), d, [])
        ids = assessment(schema, 'closing')['properties']['evidence_message_ids']['items']['enum']
        self.assertEqual(ids, ['m3', 'z', 'a'])

    def test_out_of_range_evidence_still_rejected(self):
        raw = wire_answers()
        raw['results']['contact']['evidence_message_ids'] = ['m3']
        with self.assertRaisesRegex(ContractError, 'Evidence falls outside'):
            validate_results(decode(raw, checklist(), dialog()), checklist(), dialog(), [])

    def test_prompt_exposes_same_range_as_decoder(self):
        class Provider:
            def complete(self, messages, schema):
                self.task = json.loads(messages[1]['content'])
                return json.dumps(wire_answers()), {}
        provider = Provider()
        result = Evaluator(provider, checklist()).evaluate(dialog())
        ranges = {row['criterion_id']: row['reviewed_range'] for row in result['results']}
        for criterion in provider.task['rubric']['criteria']:
            self.assertEqual(criterion['reviewed_range'], ranges[criterion['id']])
            self.assertIn('review_scope', criterion)


if __name__ == '__main__':
    unittest.main()
