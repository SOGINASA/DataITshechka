"""Read-only review queue over the existing AI annotations, across checklist versions."""
import json


def review_sources(store):
    profiles = store.profiles()
    if not any(p["checklist_hash"] == store.checklist_hash for p in profiles):
        profiles.append({"id": "current", "checklist_hash": store.checklist_hash})
    for profile in profiles:
        directory = store.output / profile["checklist_hash"]
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*/*.json")):
            annotation = json.loads(path.read_text(encoding="utf-8-sig"))
            record = store.records.get(annotation.get("conversation_id"))
            if (annotation.get("origin") == "ai_preannotation" and record
                and annotation.get("content_hash") == record["content_hash"]
                and annotation.get("checklist_hash") == profile["checklist_hash"]):
                yield profile, record, annotation


def build_queue(store, phase="uncertain"):
    if phase not in ("uncertain", "remaining", "all"):
        raise ValueError("Неизвестный этап проверки.")
    tasks = []
    counts = {"total": 0, "confirmed": 0, "uncertain_total": 0,
              "uncertain_pending": 0, "other_pending": 0, "dialogues": 0}
    for profile, record, annotation in review_sources(store):
        counts["dialogues"] += 1
        original = {x["criterion_id"]: x for x in annotation.get("review_baseline", {}).get("labels", annotation["labels"])}
        criteria = {c["id"]: (i, c["name"]) for i, c in enumerate(annotation["checklist"]["criteria"])}
        for label in annotation["labels"]:
            baseline = original[label["criterion_id"]]
            was_uncertain = baseline["verdict"] == "uncertain"
            counts["total"] += 1
            counts["uncertain_total"] += int(was_uncertain)
            checked = label.get("human_checked") is True and label["verdict"] not in ("", "uncertain")
            if checked:
                counts["confirmed"] += 1
                continue
            counts["uncertain_pending" if was_uncertain else "other_pending"] += 1
            if (phase == "uncertain" and not was_uncertain) or (phase == "remaining" and was_uncertain):
                continue
            index, name = criteria[label["criterion_id"]]
            priority = 0 if was_uncertain else 1 if label["criterion_id"] == "critical_errors" and label["verdict"] == "pass" else 2 if label["confidence"] != "high" else 3
            tasks.append({"key": f"{profile['checklist_hash']}:{annotation['annotator']}:{record['conversation_id']}:{label['criterion_id']}",
                          "profile": profile["id"], "checklist_hash": profile["checklist_hash"],
                          "conversation_id": record["conversation_id"], "annotator": annotation["annotator"],
                          "criterion_id": label["criterion_id"], "criterion_index": index, "criterion_name": name,
                          "language": record.get("language"), "channel": record["channel"],
                          "priority": priority, "was_uncertain": was_uncertain,
                          "audio_link": f"/audio/{record['conversation_id']}" if record.get("audio_url") else None})
    tasks.sort(key=lambda x: (x["priority"], {"RU": 0, "KZ": 1, "EN": 2}.get(x["language"], 3),
                             x["profile"], x["conversation_id"], x["criterion_index"]))
    return {"phase": phase, "counts": counts, "tasks": tasks}


def open_task(store, request):
    profile = request.get("profile")
    expected_hash = request.get("checklist_hash")
    if profile == "current":
        if expected_hash != store.checklist_hash:
            raise ValueError("Пользовательский чек-лист изменился. Обновите очередь.")
    else:
        candidate = next((p for p in store.profiles() if p["id"] == profile), None)
        if not candidate or candidate["checklist_hash"] != expected_hash:
            raise ValueError("Версия чек-листа изменилась. Обновите очередь.")
        store.select_profile(profile)
    annotation = store.load(request.get("conversation_id", ""), request.get("annotator", ""))
    if not annotation or annotation.get("origin") != "ai_preannotation":
        raise ValueError("Предварительная разметка не найдена.")
    if annotation["content_hash"] != store.record(annotation["conversation_id"])["content_hash"]:
        raise ValueError("Транскрипт изменился. Нужна повторная разметка.")
    return {"annotation": annotation, "bootstrap": store.bootstrap()}
