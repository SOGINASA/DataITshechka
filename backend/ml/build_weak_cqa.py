"""Build a multilingual, weakly supervised CQA SFT pilot from public QA seeds.

The 65 organizer DEV dialogues are never read by this builder. Every label comes
from a controlled synthetic behavior variant, not from upstream dataset labels.
This is an experimental seed corpus, not human gold or proof of evaluator quality.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

import pyarrow.parquet as pq

from ml.dataset import adapt_rubric
from services.ollama import SYSTEM


ROOT = Path(__file__).resolve().parents[2]
MANGI = ROOT / 'data/public_sources/mangi-kazakh-support/dataaqparatfullemes.jsonl'
TRANSLATIONS = ROOT / 'data/public_sources/mangi-kazakh-support/translations.ru-en.jsonl'
RU_PARQUET = ROOT / 'data/public_sources/support-json-ru/selected/train.parquet'
OUT = ROOT / 'data/training/weak-cqa-v1'
CHECKLIST = json.loads((ROOT / 'annotation/checklist.official.json').read_text(encoding='utf-8'))
RUBRIC = adapt_rubric(CHECKLIST)
TEST_IDS = set(json.loads((Path(__file__).with_name('protected_test_ids.json')).read_text(encoding='utf-8')))

WORDS = {
    'ru': {
        'greet': 'Здравствуйте! Меня зовут Анна, я оператор поддержки.',
        'close': 'Если появятся вопросы, напишите нам. Хорошего дня!',
        'vague': 'У меня вопрос по приложению, помогите разобраться.',
        'clarify': 'Уточните, пожалуйста, что именно вы хотите сделать?',
        'frustrated': 'Я уже давно пытаюсь разобраться, это неудобно. ',
        'neutral_ignored': 'Прочитайте ответ выше, дальше разберитесь самостоятельно.',
        'generic': 'Попробуйте посмотреть настройки приложения.',
        'second': 'И ещё подскажите, где проверить актуальные условия?',
        'thanks': 'Спасибо за ответ.',
        'bad7': 'Откройте нужный раздел, возможно, это поможет.',
        'bad4': 'Сделайте там это, потом перейдите туда и повторите.',
        'bad0': 'Откройте настройки. Не открывайте настройки. Сначала сохраните, потом ничего не сохраняйте.',
        'side': 'Могу помочь лично за отдельную оплату — переведите деньги мне напрямую.',
        'personal': 'На вашем счёте 143 000 тенге.',
        'system_ok': 'Проверка личности успешно пройдена.',
        'acct_q': 'Здравствуйте, сколько денег сейчас на моём счёте?',
        'unknown': 'У меня вопрос, помогите.',
    },
    'kk': {
        'greet': 'Сәлеметсіз бе! Менің атым Әлия, қолдау операторы боламын.',
        'close': 'Тағы сұрақтарыңыз болса, жазыңыз. Күніңіз сәтті өтсін!',
        'vague': 'Қосымша бойынша сұрағым бар, көмектесіңізші.',
        'clarify': 'Нақты нені жасағыңыз келетінін айта аласыз ба?',
        'frustrated': 'Мұны ұзақ уақыттан бері шеше алмай жүрмін, ыңғайсыз екен. ',
        'neutral_ignored': 'Жоғарыдағы жауапты оқыңыз, ары қарай өзіңіз анықтаңыз.',
        'generic': 'Қосымшаның баптауларын қарап көріңіз.',
        'second': 'Тағы да өзекті шарттарды қайдан тексеруге болатынын айтыңызшы.',
        'thanks': 'Жауап үшін рақмет.',
        'bad7': 'Қажетті бөлімді ашыңыз, көмектесуі мүмкін.',
        'bad4': 'Соны жасаңыз, содан кейін ана жаққа өтіп, қайталаңыз.',
        'bad0': 'Баптауларды ашыңыз. Ашпаңыз. Алдымен сақтаңыз, кейін ештеңе сақтамаңыз.',
        'side': 'Жеке ақылы көмегімді ұсынамын — ақшаны маған тікелей аударыңыз.',
        'personal': 'Шотыңызда 143 000 теңге бар.',
        'system_ok': 'Жеке басыңыз сәтті расталды.',
        'acct_q': 'Сәлеметсіз бе, шотымда қазір қанша ақша бар?',
        'unknown': 'Сұрағым бар, көмектесіңізші.',
    },
    'en': {
        'greet': 'Hello! My name is Aliya, and I am a support operator.',
        'close': 'If you have more questions, please write to us. Have a good day!',
        'vague': 'I have a question about the app. Could you help me?',
        'clarify': 'Could you clarify what exactly you would like to do?',
        'frustrated': 'I have been trying to resolve this for a while, and it is inconvenient. ',
        'neutral_ignored': 'Read the answer above and figure out the rest yourself.',
        'generic': 'Try checking the application settings.',
        'second': 'Also, where can I check the current terms?',
        'thanks': 'Thank you for the answer.',
        'bad7': 'Open the relevant section; that might help.',
        'bad4': 'Do that there, then go over there and repeat it.',
        'bad0': 'Open settings. Do not open settings. Save first, then do not save anything.',
        'side': 'I can help privately for a fee; transfer the money directly to me.',
        'personal': 'Your account balance is 143,000 tenge.',
        'system_ok': 'Identity verification has been completed successfully.',
        'acct_q': 'Hello, what is my current account balance?',
        'unknown': 'I have a question. Please help me.',
    },
}

VARIANTS = (
    'baseline', 'contact_fail', 'needs_pass', 'needs_fail', 'consult_0', 'consult_5',
    'consult_10', 'consult_15', 'empathy_fail', 'management_0', 'management_4',
    'management_7', 'closing_fail', 'critical_violation', 'identification_fail',
    'identification_pass',
)


def read_seeds(limit_kk: int, limit_ru: int):
    kz_rows = [json.loads(line) for line in MANGI.read_text(encoding='utf-8').splitlines() if line.strip()]
    translated = {row['id']: row for row in (json.loads(line) for line in TRANSLATIONS.read_text(encoding='utf-8').splitlines() if line.strip())}
    seeds = []
    kz_pool = random.Random(20261108).sample(kz_rows, min(48, len(kz_rows)))
    selected_kz = [row for row in kz_pool if row['id'] in translated][:limit_kk]
    if len(selected_kz) < limit_kk:
        raise ValueError(f'Only {len(selected_kz)} translated KZ seed rows are available; requested {limit_kk}.')
    for source in selected_kz:
        tx = translated[source['id']]
        group = f'mangi:{source["id"]}'
        for lang, question, answer in (
            ('kk', source['question'], source['answer']),
            ('ru', tx['ru_question'], tx['ru_answer']),
            ('en', tx['en_question'], tx['en_answer']),
        ):
            seeds.append({'group': group, 'lang': lang, 'question': question,
                          'answer': answer, 'source': 'Mäñgi ÜTM CC BY 4.0',
                          'source_id': source['id']})
    ru_rows = pq.read_table(RU_PARQUET).to_pylist()
    rows = random.Random(20261109).sample(ru_rows, min(limit_ru, len(ru_rows)))
    for source in rows:
        seeds.append({'group': f'support-json-ru:{source["id"]}', 'lang': 'ru',
                      'question': source['message'], 'answer': source['reply'],
                      'source': 'A11Sunday Support-JSON-RU CC BY 4.0',
                      'source_id': source['id']})
    return seeds


def make_dialog(seed, variant):
    lang, w = seed['lang'], WORDS[seed['lang']]
    question, answer = seed['question'].strip(), seed['answer'].strip()
    if variant == 'needs_pass':
        messages = [
            ('client', w['vague']), ('operator', w['greet']),
            ('operator', w['clarify']), ('client', question),
            ('operator', answer), ('operator', w['close']),
        ]
    elif variant == 'needs_fail':
        messages = [('client', w['vague']), ('operator', w['greet']),
                    ('operator', w['generic']), ('operator', w['close'])]
    elif variant in ('identification_fail', 'identification_pass'):
        messages = [('client', w['acct_q']), ('operator', w['greet'])]
        if variant == 'identification_pass':
            messages.append(('system', w['system_ok']))
        messages += [('operator', w['personal']), ('operator', w['close'])]
    elif variant == 'contact_fail':
        messages = [('client', question), ('operator', answer), ('operator', w['close'])]
    elif variant == 'consult_0':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', 'К сожалению, помочь не могу.' if lang == 'ru' else
                     'Кешіріңіз, көмектесе алмаймын.' if lang == 'kk' else 'Sorry, I cannot help.'),
                    ('operator', w['close'])]
    elif variant == 'consult_5':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', w['generic']), ('operator', w['close'])]
    elif variant in ('consult_10', 'consult_15'):
        messages = [('client', question + ' ' + w['second']), ('operator', w['greet']),
                    ('operator', answer), ('operator', w['close'])]
    elif variant == 'empathy_fail':
        messages = [('client', w['frustrated'] + question), ('operator', w['greet']),
                    ('operator', w['neutral_ignored']), ('operator', w['close'])]
    elif variant == 'management_0':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', w['bad0']), ('operator', w['close'])]
    elif variant == 'management_4':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', w['bad4']), ('client', w['clarify']),
                    ('operator', w['bad4']), ('operator', w['close'])]
    elif variant == 'management_7':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', w['bad7']), ('operator', w['close'])]
    elif variant == 'closing_fail':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', answer), ('client', w['thanks'])]
    elif variant == 'critical_violation':
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', w['side']), ('operator', w['close'])]
    else:
        messages = [('client', question), ('operator', w['greet']),
                    ('operator', answer), ('operator', w['close'])]
    transcript = [{'id': f'm{i+1}', 'speaker': speaker, 'text': text}
                  for i, (speaker, text) in enumerate(messages)]
    return transcript


def labels_for(variant, transcript):
    ids = [m['id'] for m in transcript]
    first, last = ids[0], ids[-1]
    reviewed = {'start_message_id': first, 'end_message_id': last}
    result = {}

    def binary(name, value, reason, evidence=()):
        result[name] = {'status': 'pass' if value else 'fail', 'value': bool(value),
                        'explanation': reason, 'evidence_message_ids': list(evidence),
                        'reviewed_range': reviewed}

    def score(name, value, reason, evidence=()):
        result[name] = {'status': 'scored', 'value': value, 'explanation': reason,
                        'evidence_message_ids': list(evidence), 'reviewed_range': reviewed}

    def na(name, reason):
        result[name] = {'status': 'not_applicable', 'value': None, 'explanation': reason,
                        'evidence_message_ids': [], 'reviewed_range': reviewed}

    if variant == 'contact_fail':
        binary('contact', False, 'В первом ответе оператора нет приветствия и представления.')
    else:
        op = next((m['id'] for m in transcript if m['speaker'] == 'operator'), None)
        binary('contact', True, 'Оператор поздоровался и представился в первом ответе.', [op])

    if variant == 'needs_pass':
        clarify_id = next(m['id'] for m in transcript if m['speaker'] == 'operator' and
                          m['text'] in (WORDS['ru']['clarify'], WORDS['kk']['clarify'], WORDS['en']['clarify']))
        binary('needs', True, 'Оператор уточнил запрос до предоставления ответа.', [clarify_id])
    elif variant == 'needs_fail':
        binary('needs', False, 'Оператор ответил на неопределённый запрос без нужного уточнения.')
    else:
        na('needs', 'Запрос клиента содержит достаточно данных для ответа.')

    if variant == 'identification_fail':
        disclosure = ids[-2]
        binary('identification', False, 'Сведения счёта раскрыты до подтверждения идентификации.', [disclosure])
    elif variant == 'identification_pass':
        verified = next(m['id'] for m in transcript if m['speaker'] == 'system')
        binary('identification', True, 'Система подтвердила проверку до раскрытия сведений.', [verified])
    else:
        na('identification', 'Общий вопрос не требует доступа к данным счёта.')

    consult = {'consult_0': (0, 'Содержательного ответа или корректного следующего шага нет.'),
               'consult_5': (5, 'Дана только общая подсказка без понятного плана действий.'),
               'consult_10': (10, 'Ответ закрывает часть запроса, существенный вопрос остаётся.'),
               'consult_15': (15, 'Основной вопрос закрыт, пропущена второстепенная деталь.'),
               'needs_fail': (5, 'Общий ответ не позволяет клиенту понять, что делать.'),
               'management_0': (20, 'Содержание ответа полное, но противоречивое изложение оценено отдельно.'),
               'management_4': (20, 'Ответ содержит решение; понятность оценивается отдельно.'),
               'management_7': (20, 'Существенный вопрос закрыт; мелкий сбой оценён в ведении.'),
               'empathy_fail': (20, 'По существу запрос закрыт; реакция на неудобство оценена отдельно.'),
               'closing_fail': (20, 'Ответ по существу дан; отсутствие завершения оценено отдельно.'),
               'contact_fail': (20, 'Вопрос клиента получил полный ответ.'),
               'critical_violation': (0, 'Ключевой ответ заменён предложением личной платной услуги.'),
               'identification_fail': (20, 'Ответ предоставлен, но защищённые данные раскрыты неправомерно.'),
               'identification_pass': (20, 'Запрос закрыт после подтверждённой проверки личности.')}
    if variant in consult:
        value, reason = consult[variant]
    else:
        value, reason = 20, 'Дан полный ответ или корректный следующий шаг.'
    response_id = next((m['id'] for m in transcript if m['speaker'] == 'operator' and
                        m['text'] not in (WORDS['ru']['greet'], WORDS['kk']['greet'], WORDS['en']['greet'],
                                          WORDS['ru']['close'], WORDS['kk']['close'], WORDS['en']['close'])), ids[-1])
    score('consultation', value, reason, [response_id])

    if variant == 'empathy_fail':
        binary('empathy', False, 'Оператор не отреагировал на прямо выраженное неудобство.')
    else:
        binary('empathy', True, 'Оператор отвечает вежливо; клиент не выражал неудобства.', [response_id])

    management = {'management_0': 0, 'management_4': 4, 'management_7': 7}.get(variant, 10)
    management_reasons = {0: 'Противоречивые указания делают ход диалога непонятным.',
                          4: 'Клиенту приходится переспрашивать из-за неясной формулировки.',
                          7: 'Есть один заметный сбой, но дальнейший шаг понятен.',
                          10: 'Ответы ясные и связные.'}
    score('dialogue_management', management, management_reasons[management], [response_id])

    if variant == 'closing_fail':
        binary('closing', False, 'Оператор мог завершить разговор, но не попрощался.')
    else:
        closing_id = ids[-1]
        binary('closing', True, 'Оператор предложил дальнейшую помощь и попрощался.', [closing_id])

    if variant in ('critical_violation', 'identification_fail'):
        evidence = ids[-2] if variant == 'identification_fail' else ids[-2]
        result['gross_errors'] = {'status': 'fail', 'value': True,
            'explanation': 'Выявлено раскрытие конфиденциальных данных или личная платная услуга.',
            'evidence_message_ids': [evidence], 'reviewed_range': reviewed}
    else:
        result['gross_errors'] = {'status': 'pass', 'value': False,
            'explanation': 'В проверенном диалоге нет перечисленных грубых нарушений.',
            'evidence_message_ids': [], 'reviewed_range': reviewed}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit-kk', type=int, default=16)
    parser.add_argument('--limit-ru', type=int, default=128)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--seed', type=int, default=20261108)
    args = parser.parse_args()
    if not TRANSLATIONS.exists():
        raise SystemExit('Missing machine translations. Run: backend/.venv/bin/python backend/ml/translate_kazakh_support.py')
    seeds = read_seeds(args.limit_kk, args.limit_ru)
    rng = random.Random(args.seed)
    grouped = {}
    for seed in seeds:
        # All variants and translations of one source question share one split.
        digest = int(hashlib.sha256(seed['group'].encode()).hexdigest()[:8], 16) % 100
        split = 'train' if digest < 80 else 'valid' if digest < 90 else 'test'
        grouped.setdefault(split, []).append(seed)
    destination = args.out.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    counts, groups_by_split = {}, {}
    for split in ('train', 'valid', 'test'):
        examples = []
        source_seeds = grouped.get(split, [])
        for seed in source_seeds:
            variants = list(VARIANTS)
            rng.shuffle(variants)
            for variant in variants:
                transcript = make_dialog(seed, variant)
                conversation_id = f"weak-{seed['lang']}-{seed['source_id']}-{variant}"
                if conversation_id in TEST_IDS:
                    raise ValueError(f'Protected DEV ID collision: {conversation_id}')
                context = {'rubric_description': RUBRIC.description, 'criteria': RUBRIC.criteria,
                           'language': seed['lang'], 'channel': 'chat', 'messages': transcript}
                target = {'results': labels_for(variant, transcript)}
                examples.append({'messages': [
                    {'role': 'system', 'content': SYSTEM},
                    {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)},
                    {'role': 'assistant', 'content': json.dumps(target, ensure_ascii=False)},
                ]})
        path = destination / f'{split}.jsonl'
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in examples), encoding='utf-8')
        counts[split] = len(examples)
        groups_by_split[split] = sorted({seed['group'] for seed in source_seeds})
    if set(groups_by_split['train']) & set(groups_by_split['valid']) or set(groups_by_split['train']) & set(groups_by_split['test']) or set(groups_by_split['valid']) & set(groups_by_split['test']):
        raise ValueError('Source groups leaked across splits')
    manifest = {'schema_version': 1, 'corpus': 'weak-cqa-v1', 'label_provenance': 'programmatic labels from controlled synthetic behavior variants',
        'not_human_gold': True, 'protected_dev_ids_used': 0,
        'sources': ['mangi-llm/kazakh-customer-support-qa (CC BY 4.0)', 'A11Sunday/support-json-ru (CC BY 4.0; train split only)'],
        'seed_groups': {k: len(v) for k, v in groups_by_split.items()}, 'counts': counts,
        'variants': list(VARIANTS), 'warning': 'Synthetic weak labels, template-shaped conversations; for pilot only. Do not claim as validated QA accuracy.'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in manifest.items() if k != 'seed_groups'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
