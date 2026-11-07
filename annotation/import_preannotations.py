"""Validate and import transcript-specific AI decisions; no model/API calls or heuristics."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from server import ROOT, Store, atomic_json, digest, read_json


AUTHOR = "AI-разметка DEV v1 (проверить)"
CRITERIA = ("contact", "needs", "identification", "consultation", "empathy", "management", "closing", "critical_errors")


def payload_for(store, cid, decisions):
    record = store.record(cid)
    operators = [t["turn_id"] for t in record["transcript"] if t["speaker"] == "operator"]
    if not operators:
        operators = [record["transcript"][0]["turn_id"], record["transcript"][-1]["turn_id"]]
    if len(decisions) != len(CRITERIA):
        raise ValueError(f"{cid}: need exactly eight criterion decisions")
    labels = []
    for criterion_id, decision in zip(CRITERIA, decisions):
        answer, evidence, reason, *extra = decision
        verdict = "score" if type(answer) in (int, float) else answer
        labels.append({"criterion_id": criterion_id, "verdict": verdict,
                       "score": answer if verdict == "score" else None,
                       "reason": reason, "confidence": extra[0] if extra else "high",
                       "evidence_turn_ids": [f"t{i:04d}" for i in evidence],
                       "checked_span": {"start_turn_id": operators[0], "end_turn_id": operators[-1]}})
    return {"conversation_id": cid, "annotator": AUTHOR, "origin": "ai_preannotation",
            "checklist_hash": store.checklist_hash, "content_hash": record["content_hash"],
            "revision": 0, "status": "complete", "reviewed": False, "reviewer": "", "labels": labels}


def import_decisions(source_path, decisions_path, output):
    source, decisions = read_json(source_path), read_json(decisions_path)
    checklist = Path(__file__).with_name("checklist.official.json")
    dataset = ROOT / "data/raw/dev.json"
    store = Store(dataset, output, checklist, use_active_checklist=False)
    if store.checklist_hash != source["checklist_hash"] or store.checklist_hash != digest(read_json(checklist)):
        raise ValueError("Checklist differs from the one used while reading transcripts")
    expected = {cid for cid, r in store.records.items() if r["channel"] == "agent chat"}
    if set(decisions) != expected:
        raise ValueError(f"Decision coverage mismatch. Missing: {sorted(expected-set(decisions))}; extra: {sorted(set(decisions)-expected)}")
    for cid in expected:
        if source["record_hashes"].get(cid) != store.record(cid)["content_hash"]:
            raise ValueError(f"Transcript changed: {cid}")
    # Validate the entire batch before writing to the user's annotation directory.
    with tempfile.TemporaryDirectory(prefix="cqa-preannotation-") as stage:
        validator = Store(dataset, Path(stage), checklist, use_active_checklist=False)
        for cid in sorted(expected):
            validator.save(payload_for(validator, cid, decisions[cid]))
    annotations = []
    for cid in sorted(expected):
        previous = store.load(cid, AUTHOR)
        if previous:
            if previous["content_hash"] != store.record(cid)["content_hash"]:
                raise ValueError(f"Existing annotation has obsolete transcript: {cid}")
            saved = previous  # Never overwrite edits/review made after this import.
        else:
            saved = store.save(payload_for(store, cid, decisions[cid]))
        saved["eligible_for_reference"] = store.eligibility(saved)
        annotations.append(saved)
    excluded = [{"conversation_id": r["conversation_id"], "channel": r["channel"],
                 "reason": "Эта выгрузка содержит только чаты. Звонки размечены отдельно по checklist.voice.json; см. ai-voice-preannotations.json и общую ai-dev-all-preannotations.json."}
                for r in store.records.values() if r["channel"] != "agent chat"]
    review_queue = []
    for annotation in annotations:
        for label in annotation["labels"]:
            if not label.get("human_checked") and (label["verdict"] == "uncertain" or label["confidence"] != "high" or (label["criterion_id"] == "critical_errors" and label["verdict"] == "pass")):
                review_queue.append({"conversation_id": annotation["conversation_id"], "language": annotation["language"],
                                     "criterion_id": label["criterion_id"], "verdict": label["verdict"],
                                     "confidence": label["confidence"], "reason": label["reason"],
                                     "evidence_turn_ids": label["evidence_turn_ids"]})
    review_queue.sort(key=lambda x: (0 if x["criterion_id"] == "critical_errors" and x["verdict"] == "pass"
                                    else 1 if x["verdict"] == "uncertain" else 2,
                                    x["conversation_id"], x["criterion_id"]))
    report = {"annotator": AUTHOR, "origin": "ai_preannotation", "human_verified": all(a["eligible_for_reference"] for a in annotations),
              "annotated_dialogues": len(annotations), "criterion_decisions": sum(len(a["labels"]) for a in annotations),
              "languages": dict(Counter(a["language"] for a in annotations)),
              "computed_totals": sum(a["score_summary"]["total"] is not None for a in annotations),
              "human_confirmed_decisions": sum(x.get("human_checked") is True for a in annotations for x in a["labels"]),
              "human_verified_dialogues": sum(a["eligible_for_reference"] for a in annotations),
              "no_independent_test": True,
              "uncertain_decisions": sum(x["verdict"] == "uncertain" for a in annotations for x in a["labels"]),
              "flagged_critical_errors": [a["conversation_id"] for a in annotations if a["score_summary"]["critical_errors"] is True],
              "priority_review_decisions": len(review_queue), "excluded": excluded,
              "warning": "Исходная разметка ИИ с сохранёнными человеческими подтверждениями. Пригодность каждой записи указана в eligible_for_reference. Независимый test не выделен."}
    export_dir = ROOT / "data/exports"
    atomic_json(export_dir / "ai-dev-preannotations.json", {"schema_version": 1, "report": report,
                "checklist": store.checklist, "checklist_hash": store.checklist_hash,
                "records": [store.record(a["conversation_id"]) for a in annotations], "annotations": annotations})
    atomic_json(export_dir / "ai-dev-review-queue.json", review_queue)
    atomic_json(export_dir / "ai-dev-report.json", report)
    (export_dir / "ai-dev-preannotations.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False, allow_nan=False) + "\n" for a in annotations), encoding="utf-8")
    summary = ["# Предварительная разметка DEV", "", report["warning"], "",
               f"Автор в интерфейсе: **{AUTHOR}**.", "",
               f"Размечено {len(annotations)} чатов: RU 30, KZ 15, EN 15; {report['criterion_decisions']} решений по критериям.",
               f"Итог вычислен для {report['computed_totals']} диалогов; в остальных есть спорные взвешенные ответы.",
               f"Не уверен: {report['uncertain_decisions']} решений. Приоритетная проверка: {len(review_queue)} решений в {len({x['conversation_id'] for x in review_queue})} диалогах.", "",
               "Эта выгрузка содержит только чаты. Пять звонков находятся в ai-voice-preannotations.json; объединение всех 65 диалогов — ai-dev-all-preannotations.json. Аудио не оценивалось.", "",
               "## Как использовать", "",
               "1. Откройте локальный инструмент и выберите указанного автора из подсказки поля имени.",
               "2. Проверьте все грубые флаги, все uncertain и среднюю уверенность из ai-dev-review-queue.json.",
               "3. Проверьте также случайную часть уверенных решений, а KZ отдайте владеющему языком разметчику.",
               "4. Доступность языков форм, правила логинов, D-счёта и вывода сверяйте с внутренними источниками.",
               "5. Согласуйте краткие итоги при завершении и границы между эмпатией и полнотой ответа.",
               "6. Для независимого эталона создайте человеческую разметку под отдельным именем и проведите вторую проверку.",
               "7. Стройте UI, хранение, апелляции и интеграцию модели на этой предварительной версии; не называйте совпадение с ней точностью на человеческом эталоне.", "",
               "Все 60 диалогов уже просмотрены ИИ: независимого test здесь нет. Похожие шаблоны и переводы держите вместе при будущем разделении данных.", "",
               "Уверенность high/medium/low — качественная отметка разметчика, а не измеренная вероятность корректности.", "",
               "## Диалоги", "", "| ID | Язык | Предварительный итог | Грубая ошибка | Ответы на проверку |", "| --- | --- | ---: | --- | ---: |"]
    for a in annotations:
        score = a["score_summary"]["total"]
        total = "не рассчитан" if score is None else f"{score:.2f}"
        n = sum(x["conversation_id"] == a["conversation_id"] for x in review_queue)
        flag = a["score_summary"]["critical_errors"]
        summary.append(f"| {a['conversation_id']} | {a['language']} | {total} | {'Да' if flag is True else 'Нет' if flag is False else 'Не определено'} | {n} |")
    (export_dir / "ai-dev-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/annotations/ai-dev-v1.source.json")
    parser.add_argument("--decisions", type=Path, default=ROOT / "data/annotations/ai-dev-v1.decisions.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/annotations")
    args = parser.parse_args()
    report = import_decisions(args.source, args.decisions, args.output)
    print(f"Imported {report['annotated_dialogues']} chats / {report['criterion_decisions']} criterion decisions")
    print(f"Uncertain: {report['uncertain_decisions']}; priority review: {report['priority_review_decisions']}; excluded calls: {len(report['excluded'])}")
    print(f"View author: {AUTHOR}")


if __name__ == "__main__":
    main()
