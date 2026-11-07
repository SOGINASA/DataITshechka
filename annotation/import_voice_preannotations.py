"""Import five transcript-based voice annotations and produce a versioned 65-dialogue bundle."""
from collections import Counter
from pathlib import Path
import tempfile

from import_preannotations import AUTHOR as CHAT_AUTHOR, payload_for
from server import ROOT, Store, atomic_json, digest, read_json


AUTHOR = "AI-разметка звонков v1 (только транскрипт)"


def voice_payload(store, cid, decision):
    payload = payload_for(store, cid, decision["labels"])
    payload["annotator"] = AUTHOR
    payload["assessment_context"] = {
        "basis": "transcript_only", "audio_reviewed": False,
        "acoustic_observations": {"tempo": "not_assessed", "diction": "not_assessed", "intelligibility": "not_assessed", "intonation": "not_assessed"},
        "limitations": decision.get("limitations", []),
        "excluded_turn_spans": [{"start_turn_id": f"t{x[0]:04d}", "end_turn_id": f"t{x[1]:04d}", "reason": x[2]} for x in decision.get("excluded_spans", [])]
    }
    return payload


def main():
    dataset, output = ROOT / "data/raw/dev.json", ROOT / "data/annotations"
    directory = Path(__file__).resolve().parent
    decisions = read_json(output / "ai-voice-v1.decisions.json")
    source = read_json(output / "ai-dev-v1.source.json")
    voice = Store(dataset, output, directory / "checklist.voice.json", use_active_checklist=False)
    chat = Store(dataset, output, directory / "checklist.official.json", use_active_checklist=False)
    expected = {cid for cid, r in voice.records.items() if r["channel"] == "voice call"}
    if set(decisions) != expected:
        raise ValueError("Voice decisions must cover exactly the voice calls")
    for cid in expected:
        if source["record_hashes"][cid] != voice.record(cid)["content_hash"]:
            raise ValueError(f"Voice transcript changed: {cid}")
    chat_annotations = [chat.load(cid, CHAT_AUTHOR) for cid, r in chat.records.items() if r["channel"] == "agent chat"]
    if len(chat_annotations) != 60 or not all(chat_annotations):
        raise ValueError("Expected the existing 60 chat annotations in their original checklist namespace")
    for a in chat_annotations:
        if a["content_hash"] != chat.record(a["conversation_id"])["content_hash"]:
            raise ValueError("An existing chat annotation is stale")
    with tempfile.TemporaryDirectory(prefix="cqa-voice-") as stage:
        validator = Store(dataset, Path(stage), directory / "checklist.voice.json", use_active_checklist=False)
        for cid in sorted(expected):
            validator.save(voice_payload(validator, cid, decisions[cid]))
    annotations = []
    for cid in sorted(expected):
        previous = voice.load(cid, AUTHOR)
        if previous and previous["content_hash"] != voice.record(cid)["content_hash"]:
            raise ValueError(f"Stale saved voice annotation: {cid}")
        saved = previous or voice.save(voice_payload(voice, cid, decisions[cid]))
        saved["eligible_for_reference"] = voice.eligibility(saved)
        annotations.append(saved)
    queue = [{"conversation_id": a["conversation_id"], "criterion_id": x["criterion_id"],
              "verdict": x["verdict"], "confidence": x["confidence"], "reason": x["reason"],
              "evidence_turn_ids": x["evidence_turn_ids"], "checklist_hash": a["checklist_hash"]}
             for a in annotations for x in a["labels"] if not x.get("human_checked") and (x["verdict"] == "uncertain" or x["confidence"] != "high")]
    audio_count = sum(a.get("assessment_context", {}).get("audio_reviewed") is True for a in annotations)
    bases = {a.get("assessment_context", {}).get("basis", "transcript_only") for a in annotations}
    report = {"annotator": AUTHOR, "annotated_calls": len(annotations), "criterion_decisions": sum(len(a["labels"]) for a in annotations),
              "basis": next(iter(bases)) if len(bases) == 1 else "mixed", "audio_reviewed_calls": audio_count,
              "uncertain_decisions": sum(x["verdict"] == "uncertain" for a in annotations for x in a["labels"]),
              "computed_totals": sum(a["score_summary"]["total"] is not None for a in annotations),
              "priority_review_decisions": len(queue), "human_verified": all(a["eligible_for_reference"] for a in annotations),
              "warning": "Голосовая адаптация команды по разрешению организаторов. Источник исходных ответов — ИИ; человеческая проверка и факт прослушивания указаны в каждой аннотации."}
    exports = ROOT / "data/exports"
    atomic_json(output / "ai-voice-v1.source.json", {"checklist_hash": voice.checklist_hash,
                "record_hashes": {cid: voice.record(cid)["content_hash"] for cid in sorted(expected)}, "basis": "transcript_only"})
    atomic_json(exports / "ai-voice-preannotations.json", {"schema_version": 1, "report": report,
                "checklist": voice.checklist, "checklist_hash": voice.checklist_hash,
                "records": [voice.record(a["conversation_id"]) for a in annotations], "annotations": annotations})
    atomic_json(exports / "ai-voice-review-queue.json", queue)
    atomic_json(exports / "ai-voice-report.json", report)
    combined = chat_annotations + annotations
    for a in chat_annotations:
        a["eligible_for_reference"] = chat.eligibility(a)
    combined_queue = [{"conversation_id": a["conversation_id"], "language": a["language"],
                       "criterion_id": x["criterion_id"], "verdict": x["verdict"],
                       "confidence": x["confidence"], "reason": x["reason"],
                       "evidence_turn_ids": x["evidence_turn_ids"], "checklist_hash": a["checklist_hash"]}
                      for a in combined for x in a["labels"]
                      if not x.get("human_checked") and (x["verdict"] == "uncertain" or x["confidence"] != "high"
                      or (x["criterion_id"] == "critical_errors" and x["verdict"] == "pass"))]
    combined_report = {"annotated_dialogues": len(combined), "criterion_decisions": sum(len(a["labels"]) for a in combined),
                       "channels": dict(Counter(a["channel"] for a in combined)), "languages": dict(Counter(a["language"] for a in combined)),
                       "checklist_versions": 2, "human_verified": all(a["eligible_for_reference"] for a in combined), "voice_audio_reviewed": audio_count,
                       "uncertain_decisions": sum(x["verdict"] == "uncertain" for a in combined for x in a["labels"]),
                       "computed_totals": sum(a["score_summary"]["total"] is not None for a in combined),
                       "priority_review_decisions": len(combined_queue),
                       "human_confirmed_decisions": sum(x.get("human_checked") is True for a in combined for x in a["labels"]),
                       "human_verified_dialogues": sum(a["eligible_for_reference"] for a in combined),
                       "no_independent_test": True,
                       "warning": "Разметка с исходными ответами ИИ и последующей человеческой проверкой. У звонков разные основания оценки; смотрите assessment_context. Независимый test не выделен."}
    atomic_json(exports / "ai-dev-all-preannotations.json", {"schema_version": 1, "report": combined_report,
                "checklists": {chat.checklist_hash: chat.checklist, voice.checklist_hash: voice.checklist},
                "records": list(voice.records.values()), "annotations": combined})
    atomic_json(exports / "ai-dev-all-review-queue.json", combined_queue)
    atomic_json(exports / "ai-dev-all-report.json", combined_report)
    summary = ["# Звонки: текущее состояние разметки", "", report["warning"], "",
               f"Размечено {len(annotations)} звонков / {report['criterion_decisions']} критериев. Неопределённых решений: {report['uncertain_decisions']}.",
               f"Рассчитанных итогов: {report['computed_totals']}. Неопределённые взвешенные критерии не заменялись нулями и не исключались как N/A.", "",
               "## Как открыть", "", "В инструменте выберите голосовой чек-лист, затем автора:", "", f"**{AUTHOR}**", "",
               "## Что проверить", "", "1. Прослушать записи и отделить реальные речевые сбои от ASR.",
               "2. Сверить правила услуг, торговых ограничений и регистрации с материалами брокера.",
               "3. Проверить область действия идентификации в обратных звонках и при работе с третьим лицом.",
               "4. Проверить возможность завершения разговора; обычное событие завершения не равно внезапному обрыву.",
               "5. В p4-ru-002 не считать внутреннюю консультацию сотрудников на удержании клиентским диалогом.", "",
               f"Аудио отмечено прослушанным в {audio_count} из {len(annotations)} звонков. Конкретные акустические наблюдения смотрите в аннотациях. Timestamps сохранены как абсолютное время и не трактуются как длительности тишины.", "",
               "Совокупная выгрузка всех 65 диалогов: ai-dev-all-preannotations.json. У каждой аннотации свой checklist_hash; словарь checklists содержит две версии."]
    (exports / "ai-voice-summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"Voice: {len(annotations)} calls / {report['criterion_decisions']} decisions; uncertain={report['uncertain_decisions']}; audio reviewed={audio_count}")
    print(f"Combined: {len(combined)} dialogues / {combined_report['criterion_decisions']} decisions; rubric versions=2")


if __name__ == "__main__":
    main()
