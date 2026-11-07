import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/ml-engineering/scripts/audit_splits.py'
spec = importlib.util.spec_from_file_location('ml_audit', SCRIPT)
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)


class SplitAuditTest(unittest.TestCase):
    def run_audit(self, csv_text, **options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.csv'
            path.write_text(csv_text)
            before = path.read_bytes()
            report = ml.audit(path, **options)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            return report

    def codes(self, report):
        return {i['code'] for i in report['issues']}

    def test_synthetic_manifest_all_checks(self):
        result = ml.audit(ROOT / 'skills/ml-engineering/assets/split-manifest.example.csv',
                          group_column='entity_id', fingerprint_column='content_hash',
                          time_column='prediction_at', gap_seconds=86400, require_validation=True)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['valid_rows_by_split'], {'train': 2, 'validation': 1, 'test': 1})

    def test_duplicate_observation_fails_across_and_within_partitions(self):
        for splits in ('train\nsecret-id,train\nother,test', 'train\nsecret-id,test'):
            result = self.run_audit('row_id,split\nsecret-id,' + splits + '\n')
            self.assertIn('duplicate_row_id', self.codes(result))
            self.assertNotIn('secret-id', json.dumps(result))

    def test_groups_optional_for_known_entity_forecast(self):
        data = 'row_id,split,g\na,train,user-1\nb,test,user-1\n'
        self.assertEqual(self.run_audit(data)['status'], 'PASS')
        result = self.run_audit(data, group_column='g')
        self.assertIn('group_overlap', self.codes(result))
        self.assertNotIn('user-1', json.dumps(result))

    def test_fingerprint_detects_new_ids_for_copied_content(self):
        result = self.run_audit('row_id,split,hash\na,train,same\nb,test,same\n', fingerprint_column='hash')
        self.assertIn('fingerprint_overlap', self.codes(result))

    def test_repeated_group_inside_partition_is_allowed(self):
        data = 'row_id,split,g\na,train,one\nb,train,one\nc,test,two\n'
        self.assertEqual(self.run_audit(data, group_column='g')['status'], 'PASS')

    def test_time_checks_actual_instants_not_lexical_dates(self):
        data = 'row_id,split,t\na,train,2026-01-02T01:00:00+05:00\nb,test,2026-01-01T22:00:00Z\n'
        self.assertEqual(self.run_audit(data, time_column='t', gap_seconds=7200)['status'], 'PASS')
        self.assertIn('time_gap_train_to_test', self.codes(self.run_audit(data, time_column='t', gap_seconds=7201)))

    def test_unsorted_rows_and_overlapping_time_extrema(self):
        data = 'row_id,split,t\na,train,2026-01-05T00:00:00Z\nb,test,2026-01-04T00:00:00Z\nc,train,2026-01-01T00:00:00Z\n'
        self.assertIn('time_order_train_to_test', self.codes(self.run_audit(data, time_column='t')))

    def test_naive_invalid_and_equal_timestamps_fail(self):
        for time in ('2026-01-02', '2026-01-02T00:00:00', 'tomorrow'):
            data = 'row_id,split,t\na,train,' + time + '\nb,test,2026-01-03T00:00:00Z\n'
            self.assertIn('invalid_timestamp', self.codes(self.run_audit(data, time_column='t')))
        data = 'row_id,split,t\na,train,2026-01-01T00:00:00Z\nb,test,2026-01-01T00:00:00Z\n'
        self.assertIn('time_order_train_to_test', self.codes(self.run_audit(data, time_column='t')))

    def test_validation_alias_and_required_validation(self):
        data = 'row_id,split\na,train\nb,test\n'
        self.assertEqual(self.run_audit(data)['status'], 'PASS')
        self.assertIn('missing_validation_rows', self.codes(self.run_audit(data, require_validation=True)))
        self.assertEqual(self.run_audit(data + 'c, VAL \n', require_validation=True)['status'], 'PASS')

    def test_bad_headers_rows_blank_and_unknown_partitions(self):
        cases = [('', 'invalid_header'), ('row_id,row_id,split\n', 'invalid_header'),
                 ('id,split\na,train\n', 'missing_required_column'),
                 ('row_id,split\na,train,extra\n', 'malformed_record'),
                 ('row_id,split\na\n', 'malformed_record'),
                 ('row_id,split\n,train\n', 'empty_required_value'),
                 ('row_id,split\na,holdout\n', 'unknown_split'),
                 ('row_id,split\n', 'missing_train_rows')]
        for data, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, self.codes(self.run_audit(data)))

    def test_missing_file_and_malformed_quoted_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(ml.audit(Path(directory) / 'absent')['status'], 'FAIL')
        self.assertIn('unreadable_or_invalid_csv', self.codes(self.run_audit('row_id,split\n"unclosed,train\n')))

    def test_invalid_options_rejected(self):
        for gap in (float('nan'), float('inf'), -1, True):
            with self.assertRaises(ValueError):
                ml.audit('unused', time_column='t', gap_seconds=gap)
        with self.assertRaises(ValueError):
            ml.audit('unused', gap_seconds=1)
        with self.assertRaises(ValueError):
            ml.audit('unused', group_column='row_id')

    def test_cli_exit_codes_and_no_raw_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.csv'
            path.write_text('row_id,split\na,train\nb,test\n')
            def command(*args):
                return subprocess.run([sys.executable, str(SCRIPT), str(path), *args], capture_output=True, text=True)
            self.assertEqual(command().returncode, 0)
            self.assertEqual(command('--gap-seconds', 'nan').returncode, 2)
            path.write_text('row_id,split\nprivate-id,train\nprivate-id,test\n')
            failed = command()
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)['status'], 'FAIL')
            self.assertNotIn('private-id', failed.stdout + failed.stderr)


if __name__ == '__main__':
    unittest.main()
