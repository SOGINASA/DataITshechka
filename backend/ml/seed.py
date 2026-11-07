"""Publish rubric configurations from a reviewed release to the local application DB."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app import create_app
from ml.dataset import adapt_rubric, load_release
from models import Checklist, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parents[2] / 'data/releases/dev-reviewed-v1')
    parser.add_argument('--additional-rubric', type=Path, help='Publish a new policy version without changing the frozen baseline')
    args = parser.parse_args()
    _, _, rubrics, _ = load_release(args.release)
    if args.additional_rubric:
        rubrics['additional'] = json.loads(args.additional_rubric.read_text(encoding='utf-8'))
    app = create_app()
    with app.app_context():
        for source in rubrics.values():
            data = vars(adapt_rubric(source))
            existing = db.session.scalar(select(Checklist).where(Checklist.name == data['name'], Checklist.version == data['version']))
            if existing:
                if any(getattr(existing, key) != value for key, value in data.items()):
                    raise ValueError('Rubric version already exists with different content; do not overwrite it.')
            else:
                db.session.add(Checklist(**data))
        db.session.commit()
    print(f'Available reviewed rubric versions: {len(rubrics)}. Reference labels were not imported as predictions.')


if __name__ == '__main__':
    main()
