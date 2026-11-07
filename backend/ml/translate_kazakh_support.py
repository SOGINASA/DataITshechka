"""Translate public Kazakh QA seeds locally for weak synthetic CQA data.

Only the 406-record CC BY 4.0 Mäñgi source is read. Outputs are explicitly
machine-translated and remain local under ignored data/public_sources/.
"""
import json
import argparse
import random
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'data/public_sources/mangi-kazakh-support/dataaqparatfullemes.jsonl'
TARGET = ROOT / 'data/public_sources/mangi-kazakh-support/translations.ru-en.jsonl'
MODEL = 'qwen3:8b'
BATCH_SIZE = 4


def translate_batch(rows):
    task = {
        'model': MODEL, 'stream': False, 'format': 'json',
        'messages': [
            {'role': 'system', 'content': (
                'Translate each Kazakh customer-support question and answer into natural Russian and English. '
                'Preserve meaning, qualifications, negation, numbers and all {{PLACEHOLDER}} tokens exactly. '
                'Do not add facts or improve the answer. Return only JSON: '
                '{"translations":[{"id":"same id","ru_question":"...","ru_answer":"...",'
                '"en_question":"...","en_answer":"..."}]}. Include every input ID exactly once.' )},
            {'role': 'user', 'content': json.dumps([
                {k: row[k] for k in ('id', 'question', 'answer')} for row in rows
            ], ensure_ascii=False)},
        ],
        'options': {'temperature': 0, 'num_predict': 8192}, 'think': False,
    }
    req = Request('http://127.0.0.1:11434/api/chat',
                  data=json.dumps(task, ensure_ascii=False).encode(),
                  headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=240) as response:
        envelope = json.load(response)
    if envelope.get('done') is not True or envelope.get('done_reason') == 'length':
        raise RuntimeError('Translation response was incomplete')
    parsed = json.loads(envelope['message']['content'])
    translated = parsed.get('translations')
    if not isinstance(translated, list) or len(translated) != len(rows):
        raise RuntimeError(f'Translation response has {len(translated) if isinstance(translated, list) else "no"} rows; expected {len(rows)}')
    # Some instruct models normalize IDs. Preserve identity by the requested order,
    # while still requiring exactly one complete translation object per source row.
    for row, source in zip(translated, rows):
        row['id'] = source['id']
        for key in ('ru_question', 'ru_answer', 'en_question', 'en_answer'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise RuntimeError(f'Missing translation field {key} for {row.get("id")}')
        source = next(item for item in rows if item['id'] == row['id'])
        for field in ('question', 'answer'):
            placeholders = set(__import__('re').findall(r'\{\{[^{}]+\}\}', source[field]))
            for language_field in (f'ru_{field}', f'en_{field}'):
                found = set(__import__('re').findall(r'\{\{[^{}]+\}\}', row[language_field]))
                if found != placeholders:
                    raise RuntimeError(f'Placeholder mismatch for {row["id"]}:{language_field}')
    return translated, envelope.get('eval_count'), envelope.get('total_duration')


def translate_with_backoff(rows):
    try:
        return translate_batch(rows)
    except Exception as exc:
        if len(rows) == 1:
            # Retry the isolated item once; callers can resume from already saved rows.
            try:
                return translate_batch(rows)
            except Exception:
                raise exc
        middle = len(rows) // 2
        left, left_tokens, left_duration = translate_with_backoff(rows[:middle])
        right, right_tokens, right_duration = translate_with_backoff(rows[middle:])
        return (left + right, (left_tokens or 0) + (right_tokens or 0),
                (left_duration or 0) + (right_duration or 0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=48, help='Number of source rows to translate for this pilot')
    args = parser.parse_args()
    rows = [json.loads(line) for line in SOURCE.read_text(encoding='utf-8').splitlines() if line.strip()]
    saved = {}
    if TARGET.exists():
        saved = {row['id']: row for row in (
            json.loads(line) for line in TARGET.read_text(encoding='utf-8').splitlines() if line.strip())}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    rows = random.Random(20261108).sample(rows, min(args.limit, len(rows)))
    todo = [row for row in rows if row['id'] not in saved]
    print(f'{len(saved)} translated, {len(todo)} remaining; model={MODEL}', flush=True)
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        translated, tokens, duration = translate_with_backoff(batch)
        with TARGET.open('a', encoding='utf-8') as output:
            for row in translated:
                output.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(f'{min(start + len(batch), len(todo))}/{len(todo)} rows translated; '
              f'eval_tokens={tokens}; wall_ms={round(duration / 1e6) if duration else "?"}', flush=True)
        time.sleep(0.1)
    final_rows = {row['id']: row for row in (
        json.loads(line) for line in TARGET.read_text(encoding='utf-8').splitlines() if line.strip())}
    ordered = [final_rows[row['id']] for row in rows]
    TARGET.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in ordered), encoding='utf-8')
    print(f'Wrote {len(rows)} translation records to {TARGET.relative_to(ROOT)}', flush=True)


if __name__ == '__main__':
    main()
