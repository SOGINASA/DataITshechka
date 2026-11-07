#!/usr/bin/env python3
"""Search the bundled canonical ECC catalog without loading all skill bodies."""
import argparse
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ALIASES = {'фронтенд':'frontend', 'реакт':'react', 'дизайн':'design', 'доступность':'accessibility a11y', 'accessibility':'accessibility a11y',
           'анимация':'motion', 'тесты':'testing', 'тестирование':'testing', 'проверка':'verification',
           'безопасность':'security', 'бэкенд':'backend', 'данные':'data', 'база':'database',
           'исследование':'research', 'видео':'video', 'текст':'writing', 'деплой':'deployment',
           'производительность':'performance', 'документация':'documentation', 'скиллы':'skill',
           'мл':'machine learning', 'ml':'machine learning', 'машинное':'machine', 'обучение':'learning',
           'пайторч':'pytorch', 'бёкенд':'backend', 'бекенд':'backend', 'бэкенда':'backend',
           'сервер':'backend server', 'апи':'api'}

def search(query, category=None, limit=12):
    rows = json.loads((ROOT / 'catalog/ecc-skills.json').read_text())
    words = re.findall(r'[\w-]+', query.casefold())
    words = [part for word in words for part in ALIASES.get(word, word).split()]
    ranked = []
    for row in rows:
        if category and row['category'] != category:
            continue
        name = row['name'].casefold()
        desc = str(row['description']).casefold()
        score = sum(10 * (w == name) + 5 * (w in name) + 2 * (w in desc) for w in words)
        if score or not words:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (-item[0], item[1]['name']))
    return [dict(row, absolute_path=str(ROOT / row['path'])) for _, row in ranked[:limit]]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', nargs='?', default='')
    parser.add_argument('--category')
    parser.add_argument('--limit', type=int, default=12)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.limit < 1:
        parser.error('--limit must be positive')
    results = search(args.query, args.category, args.limit)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif not results:
        print('No matches. Try an English term or a broader query. No skill was executed.')
    else:
        for row in results:
            print(f"{row['name']} [{row['category']}; {row['review_depth']}]")
            print('  ' + str(row['description']))
            print('  ' + row['absolute_path'])
            if row['dependency_hints']:
                print('  Static hints: ' + ', '.join(row['dependency_hints']))
    return 0

if __name__ == '__main__':
    main()
