"""Create a separate voice-v2 workspace; never overwrite reviewed voice-v1 labels."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from server import ROOT, Store, atomic_json, read_json
from import_voice_preannotations import AUTHOR


def migrate(source, target, cid):
    old = source.load(cid, AUTHOR)
    if not old:
        raise ValueError(f'Missing source annotation: {cid}')
    if target.load(cid, AUTHOR):
        return target.load(cid, AUTHOR)
    payload = deepcopy(old)
    payload.update(checklist_hash=target.checklist_hash, revision=0)
    # Only this case has an already documented missing greeting / delayed recording start.
    # This is a proposal under the new rule, not a newly claimed human confirmation.
    if cid == 'p4-ru-002':
        contact = next(x for x in payload['labels'] if x['criterion_id'] == 'contact')
        contact.update(verdict='na', score=None, human_checked=False, confidence='medium',
                       reason='По новому правилу предложен N/A: в t0003 есть представление без приветствия, '
                              'а событие запуска записи находится позднее, в t0005. '
                              'Полное начало не подтверждено; проверить по аудио перед подтверждением N/A.',
                       evidence_turn_ids=['t0003', 't0005'],
                       checked_span={'start_turn_id': 't0001', 'end_turn_id': 't0006'})
        payload.update(status='draft', reviewed=False, reviewer='')
    saved = target.save(payload)
    previous = {x['criterion_id']: x for x in old['labels']}
    for label in saved['labels']:
        before = previous[label['criterion_id']]
        if label.get('human_checked') and all(label.get(k) == before.get(k) for k in
                ('verdict', 'score', 'reason', 'confidence', 'evidence_turn_ids', 'checked_span')):
            for key in ('human_checked_at', 'human_checked_by', 'review_basis'):
                if key in before:
                    label[key] = before[key]
    saved['policy_migration'] = {'source_checklist_hash': source.checklist_hash,
                                'source_annotation_revision': old['revision'],
                                'recorded_at': datetime.now(timezone.utc).isoformat(),
                                'new_human_review_claimed': False}
    saved['review_baseline'] = {'revision': old['revision'], 'labels': deepcopy(old['labels']),
                                'assessment_context': deepcopy(old.get('assessment_context'))}
    atomic_json(target.annotation_path(cid, AUTHOR), saved)
    return saved


def main():
    directory = Path(__file__).resolve().parent
    source = Store(ROOT / 'data/raw/dev.json', ROOT / 'data/annotations', directory / 'checklist.voice.json', use_active_checklist=False)
    target = Store(ROOT / 'data/raw/dev.json', ROOT / 'data/annotations', directory / 'checklist.voice.v2.json', use_active_checklist=False)
    annotations = [migrate(source, target, cid) for cid, r in source.records.items() if r['channel'] == 'voice call']
    atomic_json(ROOT / 'data/exports/voice-v2-review-queue.json', [
        {'conversation_id': a['conversation_id'], 'criterion_id': label['criterion_id'],
         'checklist_hash': target.checklist_hash, 'verdict': label['verdict'], 'reason': label['reason']}
        for a in annotations for label in a['labels'] if not label.get('human_checked')])
    print(f'Voice v2: {len(annotations)} calls copied; pending labels: '
          f'{sum(not x.get("human_checked") for a in annotations for x in a["labels"])}. Voice v1 unchanged.')


if __name__ == '__main__':
    main()
