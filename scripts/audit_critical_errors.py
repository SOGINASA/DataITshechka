"""Create a private rare-error report and optional subtype annotation queue; no model calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from ml.critical import audit
from ml.run import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'data/runs/full-compare-20261107/local-v1')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/runs/critical-audit-20261107/report.json')
    args = parser.parse_args()
    refs = json.loads((args.run_dir / 'references.json').read_text(encoding='utf-8'))
    predictions = json.loads((args.run_dir / 'predictions.json').read_text(encoding='utf-8'))
    result = audit(refs, predictions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('review_queue', 'limitations')}))


if __name__ == '__main__':
    main()
