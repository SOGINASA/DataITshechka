"""Export an immutable reviewed release and fixed splits for MLX chat SFT.

Run from backend: python -m ml.export_sft --release ../data/releases/dev-reviewed-v1 \
  --splits ../data/splits/scenario-v1.json --out ../data/training/scenario-v1
"""
import argparse
import json
from pathlib import Path

from ml.dataset import adapt_input, adapt_reference, adapt_rubric, load_release, sha256
from services.ollama import SYSTEM

ROOT = Path(__file__).resolve().parents[2]
PROTECTED_TEST_IDS = set(json.loads((Path(__file__).with_name('protected_test_ids.json')).read_text(encoding='utf-8')))


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n' for row in rows),
                    encoding='utf-8')


def export(release, splits_path, target):
    inputs, references, rubrics, manifest = load_release(release)
    splits = json.loads(Path(splits_path).read_text(encoding='utf-8'))
    if set(splits) != {'train', 'valid', 'test'} or any(not isinstance(splits[k], list) for k in splits):
        raise ValueError('Split file must contain train, valid and test arrays of conversation IDs.')
    flat = [cid for values in splits.values() for cid in values]
    known = {row['conversation_id'] for row in inputs}
    overlap = known & PROTECTED_TEST_IDS
    if overlap:
        raise ValueError(f'Protected DEV test conversations cannot be used for fine-tuning: {sorted(overlap)}')
    if len(flat) != len(set(flat)) or set(flat) != known:
        raise ValueError('Splits must assign every release conversation exactly once; no duplicates or unknown IDs.')
    by_input = {row['conversation_id']: row for row in inputs}
    rubrics_by_hash = {key: adapt_rubric(value) for key, value in rubrics.items()}
    exported = {}
    for split, ids in splits.items():
        examples = []
        for cid in ids:
            row, reference = by_input[cid], references[cid]
            if reference.get('eligible_for_reference') is not True:
                raise ValueError(f'{cid} is not eligible as a reviewed training reference.')
            if row['checklist_hash'] not in rubrics_by_hash:
                raise ValueError(f'{cid} refers to an unknown checklist hash.')
            conversation = adapt_input(row)
            rubric = rubrics_by_hash[row['checklist_hash']]
            gold = adapt_reference(reference, conversation, rubric)
            request = {'rubric_description': rubric.description, 'criteria': rubric.criteria,
                       'language': conversation.language, 'channel': conversation.channel,
                       'messages': conversation.messages}
            results = {}
            for result in gold:
                item = {'status': result['status'], 'value': result.get('value'),
                        'explanation': result['explanation'],
                        'evidence_message_ids': [e['message_id'] for e in result.get('evidence', [])]}
                span = result.get('reviewed_range')
                if span:
                    item['reviewed_range'] = span
                results[result['criterion_id']] = item
            examples.append({'messages': [
                {'role': 'system', 'content': SYSTEM},
                {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)},
                {'role': 'assistant', 'content': json.dumps({'results': results}, ensure_ascii=False)},
            ]})
        exported[split] = examples
    destination = Path(target).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for split, examples in exported.items():
        write_jsonl(destination / f'{split}.jsonl', examples)
    metadata = {'schema_version': 1, 'release_version': manifest['release_version'],
                'release_manifest_sha256': sha256(Path(release) / 'manifest.json'),
                'split_file_sha256': sha256(splits_path), 'counts': {k: len(v) for k, v in exported.items()},
                'warning': 'Only for experiments. Keep scenario families together; test.jsonl is evaluation only.'}
    (destination / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--splits', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.release, args.splits, args.out), ensure_ascii=False))


if __name__ == '__main__':
    main()
