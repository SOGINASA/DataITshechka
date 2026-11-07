#!/usr/bin/env python3
"""Read-only CSV split audit. Python 3.9+, standard library; no model/data uploads."""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

SPLITS = ('train', 'validation', 'test')
LIMITATIONS = [
    'PASS covers only enabled manifest checks; it does not prove absence of leakage.',
    'No feature lineage, label-window, preprocessing, near-duplicate or metric audit.',
    'Timestamps are prediction/event times; gaps do not certify label availability.',
]


def timestamp(value):
    """Require an explicit timezone; compare actual UTC instants."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Timezone required')
    return parsed.astimezone(timezone.utc)


def audit(path, id_column='row_id', split_column='split', group_column=None,
          fingerprint_column=None, time_column=None, gap_seconds=0.0,
          require_validation=False):
    if isinstance(gap_seconds, bool) or not math.isfinite(gap_seconds) or gap_seconds < 0:
        raise ValueError('gap_seconds must be finite and nonnegative')
    if gap_seconds and not time_column:
        raise ValueError('A time column is required for a nonzero gap')
    columns = [id_column, split_column] + [c for c in (group_column, fingerprint_column, time_column) if c is not None]
    if any(not isinstance(c, str) or not c.strip() for c in columns) or len(columns) != len(set(columns)):
        raise ValueError('Configured column names must be nonempty and distinct')
    counts = dict.fromkeys(SPLITS, 0)
    issues = {}
    total = 0
    seen = {'id': {}, 'group': {}, 'fingerprint': {}}
    bounds = {}

    def issue(code, row=None):
        item = issues.setdefault(code, {'code': code, 'count': 0, 'example_records': []})
        item['count'] += 1
        if row is not None and len(item['example_records']) < 10:
            item['example_records'].append(row)

    def result():
        return {
            'status': 'FAIL' if issues else 'PASS',
            'rows_read': total, 'valid_rows_by_split': counts,
            'checks': {'unique_row_ids': True, 'group_disjoint': bool(group_column),
                       'fingerprint_disjoint': bool(fingerprint_column),
                       'time_order': bool(time_column), 'gap_seconds': gap_seconds,
                       'validation_required': require_validation},
            'issues': list(issues.values()), 'limitations': LIMITATIONS,
        }

    try:
        with Path(path).open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames
            if not header or len(header) != len(set(header)) or any(not h.strip() for h in header):
                issue('invalid_header')
                return result()
            if not set(columns).issubset(header):
                issue('missing_required_column')
                return result()
            for number, row in enumerate(reader, start=1):
                total += 1
                if None in row or any(v is None for v in row.values()):
                    issue('malformed_record', number)
                    continue
                if any(not row[c].strip() for c in columns):
                    issue('empty_required_value', number)
                    continue
                split = row[split_column].strip().casefold()
                if split == 'val':
                    split = 'validation'
                if split not in SPLITS:
                    issue('unknown_split', number)
                    continue
                instant = None
                if time_column:
                    try:
                        instant = timestamp(row[time_column].strip())
                    except (ValueError, OverflowError):
                        issue('invalid_timestamp', number)
                        continue
                counts[split] += 1
                for kind, column in [('id', id_column), ('group', group_column), ('fingerprint', fingerprint_column)]:
                    if column is None:
                        continue
                    key = row[column].strip()
                    previous = seen[kind].get(key)
                    if previous is not None and (kind == 'id' or previous != split):
                        issue('duplicate_row_id' if kind == 'id' else kind + '_overlap', number)
                    else:
                        seen[kind][key] = split
                if instant is not None:
                    low, high = bounds.get(split, (instant, instant))
                    bounds[split] = (min(low, instant), max(high, instant))
    except (OSError, UnicodeError, csv.Error):
        issue('unreadable_or_invalid_csv')
        return result()

    for required in ('train', 'test') + (('validation',) if require_validation else ()):
        if counts[required] == 0:
            issue('missing_' + required + '_rows')
    ordered = [split for split in SPLITS if split in bounds]
    for left, right in zip(ordered, ordered[1:]):
        delta = (bounds[right][0] - bounds[left][1]).total_seconds()
        if delta <= 0:
            issue('time_order_' + left + '_to_' + right)
        elif delta < gap_seconds:
            issue('time_gap_' + left + '_to_' + right)
    return result()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--id-column', default='row_id')
    parser.add_argument('--split-column', default='split')
    parser.add_argument('--group-column', help='Enable disjoint-group check for unseen-entity evaluation')
    parser.add_argument('--fingerprint-column', help='Enable exact-content fingerprint overlap check')
    parser.add_argument('--time-column', help='Enable strict train < validation < test time ordering')
    parser.add_argument('--gap-seconds', type=float, default=0.0)
    parser.add_argument('--require-validation', action='store_true')
    args = parser.parse_args(argv)
    options = vars(args).copy()
    path = options.pop('manifest')
    try:
        report = audit(path, **options)
    except (ValueError, TypeError):
        print(json.dumps({'status': 'ERROR', 'error': 'Invalid options: use distinct columns and a finite nonnegative gap with --time-column.'}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
