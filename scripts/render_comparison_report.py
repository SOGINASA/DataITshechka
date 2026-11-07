"""Render the completed comparison without exposing dialogue texts or private URLs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'data/runs/full-compare-20261107'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def number(value, digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def percentage(value):
    return '—' if value is None else number(100 * value) + '%'


def value(row):
    if not row:
        return 'нет ответа'
    if row['status'] == 'not_applicable':
        return 'N/A'
    if row['status'] == 'needs_review':
        return 'не оценено'
    return str(row['value'])


def render(run, output):
    comparison = read(run / 'comparison-metrics.json')
    if not comparison['complete']:
        raise ValueError('Final report requires both complete runs')
    a, b = comparison['a'], comparison['b']
    pa, pb = [read(run / folder / 'predictions.json') for folder in ['local-v1', 'ml2-8b']]
    gold = read(run / 'common-gold.json')
    if set(pa) != set(pb) or set(pa) != set(gold) or len(gold) != 65:
        raise ValueError('Final report requires all 65 original dialogue IDs for each candidate')
    aa, ab = [m['breakdown']['all']['accuracy'] for m in (a, b)]
    if ab > aa:
        conclusion = 'По совпадению с подтверждённой DEV-разметкой лучше ML2 на 8B.'
    elif aa > ab:
        conclusion = 'В этом полном прогоне локальная версия на 4B точнее ML2 на 8B.'
    else:
        conclusion = 'Общая точность двух кандидатов совпала; выбор требует учёта покрытия, C8 и скорости.'
    lines = ['# Полный DEV-прогон: локальная версия против ML2', '', conclusion, '',
             'Оба кандидата проверены на 65 одинаковых диалогах и 520 подтверждённых решениях. '
             'Это development; независимого контрольного теста нет. Использованы одинаковые определения '
             'критериев из замороженного v1, собственные промпты и валидаторы каждого кандидата.', '',
             '| Показатель | A: локальная 4B | B: ML2 8B |', '| --- | --- | --- |']
    summary = [
        ('Точные решения', *[f'{m["breakdown"]["all"]["correct"]}/520 ({percentage(m["breakdown"]["all"]["accuracy"])})' for m in (a, b)]),
        ('Технически успешные ответы / ошибки', *[f'{m["completed"]} / {m["errors"]}' for m in (a, b)]),
        ('Итоговый балл рассчитан', *[str(m['score_comparable_dialogues']) + '/65' for m in (a, b)]),
        ('Все 8 решений окончательные', *[str(sum(p['state'] == 'ok' and all(r['status'] != 'needs_review' for r in p.get('results', [])) for p in ps.values())) + '/65' for ps in (pa, pb)]),
        ('MAE итогового балла на доступных полных оценках', *[number(m['score_mae']) for m in (a, b)]),
        ('MAE на общем наборе полных пар', number(comparison['paired_score_mae_a']), number(comparison['paired_score_mae_b'])),
        ('Медиана / p95 времени, сек', *[number(m['latency_median_seconds']) + ' / ' + number(m['latency_p95_seconds']) for m in (a, b)]),
        ('Сумма времени отдельных оценок, мин', *[number(sum(p['elapsed_seconds'] for p in ps.values()) / 60) for ps in (pa, pb)]),
        ('Верные N/A / эталонные N/A', *[f'{m["na_counts"]["correct_na"]} / {m["na_counts"]["reference_na"]}' for m in (a, b)]),
        ('Предсказано N/A всего', *[str(m['na_counts']['predicted_na']) for m in (a, b)]),
    ]
    for name, va, vb in summary:
        lines.append(f'| {name} | {va} | {vb} |')
    lines += ['', f'Общих полных пар для MAE: {comparison["score_pairs_with_both_complete"]}. '
              'Ошибки и needs_review остаются в знаменателе точности; частичные баллы не выдаются за полные.', '',
              '## Грубые нарушения', '', '| Показатель | A | B |', '| --- | --- | --- |']
    for name, field in [('Верно обнаружено', 'tp'), ('Ложных тревог', 'fp'), ('Пропущено / не оценено среди нарушений', 'fn')]:
        lines.append(f'| {name} | {a["violation_metrics"]["gross_errors"][field]} | {b["violation_metrics"]["gross_errors"][field]} |')
    for name, field in [('Precision', 'precision'), ('Recall', 'recall')]:
        lines.append(f'| {name} | {percentage(a["violation_metrics"]["gross_errors"][field])} | {percentage(b["violation_metrics"]["gross_errors"][field])} |')
    lines += ['', 'Флаг C8 передаётся отдельно и не обнуляет итоговый балл.', '',
              '## Критерии и срезы', '', '| Критерий / срез | A | B |', '| --- | --- | --- |']
    for key in a['breakdown']:
        if key.startswith(('criterion:', 'language:', 'channel:', 'reference_audio:')):
            va, vb = a['breakdown'][key], b['breakdown'][key]
            lines.append(f'| {key} | {va["correct"]}/{va["expected"]} ({percentage(va["accuracy"])}) | {vb["correct"]}/{vb["expected"]} ({percentage(vb["accuracy"])}) |')
    pairs = comparison['paired_decisions']
    lines += ['', '## Попарное сравнение', '',
              f'- Оба правы: {pairs.get("both_correct", 0)}.',
              f'- Только A права: {pairs.get("only_a_correct", 0)}.',
              f'- Только B права: {pairs.get("only_b_correct", 0)}.',
              f'- Оба ошиблись / не оценили: {pairs.get("both_wrong_or_missing", 0)}.', '',
              '## Примеры расхождений', '', '| Диалог | Критерий | Эталон | A | B |', '| --- | --- | --- | --- | --- |']
    shown = set()
    for changed in comparison['changed_correctness']:
        cid, criterion = changed['conversation_id'], changed['criterion_id']
        key = criterion, changed['b_correct']
        if key in shown or len(shown) >= 8:
            continue
        shown.add(key)
        lookup = lambda rows: next((r for r in rows if r['criterion_id'] == criterion), None)
        lines.append(f'| {cid} | {criterion} | {value(lookup(gold[cid]["results"]))} | '
                     f'{value(lookup(pa[cid].get("results", [])))} | {value(lookup(pb[cid].get("results", [])))} |')
    lines += ['', 'Примеры иллюстрируют расхождения и не заменяют метрики по всем 520 решениям.', '',
              '## Технические ошибки', '']
    for label, records in [('A', pa), ('B', pb)]:
        errors = [(cid, p.get('error', '')) for cid, p in records.items() if p['state'] == 'error']
        if not errors:
            lines.append(f'- {label}: технических ошибок нет.')
        for cid, error in errors:
            lines.append(f'- {label}, {cid}: {error}')
    lines += ['', '## Ограничения и воспроизведение', '',
              '- В эталонах — первоначальная AI-разметка с подтверждением пользователя; независимой повторной экспертизы нет.',
              '- Различаются размеры моделей и thinking: это сравнение полных кандидатов, а не доказательство превосходства одного кода на одинаковых весах.',
              '- Модель 8B имеет тот же digest, что в приложенном архиве. Контекст ML2 увеличен, чтобы вместить одинаковые полные входы; архивные собственные рубрики заменены общей замороженной версией.',
              '- Модели не получали эталонных ответов, человеческих объяснений, аудио или базы знаний. Три эталонных звонка проверялись человеком с аудио; этот срез выделен отдельно.',
              '- Голосовая политика v2 с новым N/A не подменяла метки v1 в середине эксперимента.',
              '- Валидные ID и точные цитаты не доказывают смысловую правильность объяснения.',
              '- Суммарное время не включает ожидание второй моделью свободного GPU. Доступные токены при незавершённых генерациях могут быть неполными.',
              '- Это DEV, не десять контрольных PROD-чатов и не готовые файлы официальной сдачи.', '',
              'Протокол: [ML_COMPARISON_PROTOCOL_RU.md](ML_COMPARISON_PROTOCOL_RU.md). '
              'Приватные артефакты: `data/runs/full-compare-20261107/`; общий отчёт — `comparison-metrics.json`, '
              'предсказания и снимки кода — в каталогах обоих кандидатов. Исходные диалоги и подписанные URL '
              'в этот документ не включены.', '']
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp')
    temp.write_text('\n'.join(lines), encoding='utf-8')
    temp.replace(output)
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=RUN)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/ML_FULL_COMPARISON_RU.md')
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    while True:
        path = args.run / 'comparison-metrics.json'
        data = read(path) if path.exists() else {}
        if data.get('complete'):
            result = render(args.run, args.output)
            print('Final report saved:', args.output, flush=True)
            print('A:', result['a']['breakdown']['all'], 'B:', result['b']['breakdown']['all'], flush=True)
            return
        if not args.wait:
            raise SystemExit('Both full runs are not complete; no final report written.')
        saved = data.get('b', {}).get('completed', 0) + data.get('b', {}).get('errors', 0)
        print(f'Waiting for final comparison: ML2 saved {saved}/65', flush=True)
        time.sleep(45)


if __name__ == '__main__':
    main()
