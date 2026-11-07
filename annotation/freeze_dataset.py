"""Freeze the current reviewed annotations into an immutable development release.

Inputs for model inference and reference answers are separate files. No model is called.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from server import ROOT, Store, atomic_json, calculate_score, digest, read_json
from import_preannotations import AUTHOR as CHAT_AUTHOR
from import_voice_preannotations import AUTHOR as VOICE_AUTHOR


def collect_reviewed(dataset, annotation_dir, rubric_dir):
    checklists, records, annotations = {}, {}, []
    for filename, channel, author in (("checklist.official.json", "agent chat", CHAT_AUTHOR),
                                      ("checklist.voice.json", "voice call", VOICE_AUTHOR)):
        store = Store(dataset, annotation_dir, Path(rubric_dir) / filename, use_active_checklist=False)
        checklists[store.checklist_hash] = store.checklist
        for cid, record in sorted(store.records.items()):
            if record["channel"] != channel:
                continue
            annotation = store.load(cid, author)
            if not annotation:
                raise ValueError(f"Missing annotation: {cid}")
            if not store.eligibility(annotation) or not all(x.get("human_checked") is True for x in annotation["labels"]):
                raise ValueError(f"Annotation is not fully reviewed: {cid}")
            if annotation["score_summary"] != calculate_score(store.checklist, annotation["labels"]):
                raise ValueError(f"Stored arithmetic does not match the rubric: {cid}")
            turns = {t["turn_id"]: t for t in record["transcript"]}
            if len(annotation["labels"]) != len(store.checklist["criteria"]):
                raise ValueError(f"Incomplete criterion coverage: {cid}")
            for label in annotation["labels"]:
                if label["evidence"] != [turns[tid] for tid in label["evidence_turn_ids"]]:
                    raise ValueError(f"Evidence text differs from source: {cid}")
            records[cid] = record
            annotations.append(annotation)
    if len(annotations) != len(records):
        raise ValueError("Duplicate annotation targets")
    return {"schema_version": 1, "checklists": checklists,
            "records": [records[cid] for cid in sorted(records)],
            "annotations": sorted(annotations, key=lambda a: a["conversation_id"])}


def write_jsonl(path, values):
    path.write_text("".join(json.dumps(x, ensure_ascii=False, allow_nan=False) + "\n" for x in values), encoding="utf-8")


def freeze_release(bundle, releases_dir, version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise ValueError("Use a simple version identifier such as dev-reviewed-v1")
    root = Path(releases_dir).resolve()
    target = (root / version).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Release path must stay inside the release directory")
    fingerprint = digest(bundle)
    manifest_path = target / "manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if manifest["source_fingerprint"] != fingerprint:
            raise ValueError("This release is frozen and the annotations changed. Use a new --version.")
        for filename, expected in manifest["files_sha256"].items():
            path = target / filename
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Frozen release was modified: {filename}")
        return manifest
    if target.exists() and any(target.iterdir()):
        raise ValueError("Target contains an incomplete or unrelated release. Use a new --version.")
    target.mkdir(parents=True, exist_ok=True)
    annotations = bundle["annotations"]
    by_id = {a["conversation_id"]: a for a in annotations}
    # Model-facing inputs deliberately contain neither reference labels nor signed recording URLs.
    inputs = [{"conversation_id": r["conversation_id"], "language": r.get("language"),
               "channel": r["channel"], "content_hash": r["content_hash"],
               "checklist_hash": by_id[r["conversation_id"]]["checklist_hash"],
               "transcript": r["transcript"],
               "assessment_scope": {"basis": "transcript_only", "audio_supplied_to_model": False}}
              for r in bundle["records"]]
    rows = [{"conversation_id": r["conversation_id"], "language": r.get("language"),
             "channel": r["channel"], "scenario_group": None, "split": "development",
             "annotation_revision": by_id[r["conversation_id"]]["revision"],
             "checklist_hash": by_id[r["conversation_id"]]["checklist_hash"]}
            for r in bundle["records"]]
    summary = {"dialogues": len(annotations), "criterion_decisions": sum(len(a["labels"]) for a in annotations),
               "languages": dict(Counter(a["language"] for a in annotations)),
               "channels": dict(Counter(a["channel"] for a in annotations)),
               "reviewed_dialogues": sum(a.get("reviewed") is True for a in annotations),
               "human_confirmed_decisions": sum(x.get("human_checked") is True for a in annotations for x in a["labels"]),
               "uncertain_decisions": sum(x["verdict"] == "uncertain" for a in annotations for x in a["labels"]),
               "audio_reviewed_calls": sum(a.get("assessment_context", {}).get("audio_reviewed") is True for a in annotations),
               "reference_audio_scope": "mixed: inspect each reference annotation; model inputs are transcript_only",
               "independent_test": False, "scenario_groups_assigned": False}
    atomic_json(target / "dataset.json", bundle)
    atomic_json(target / "checklists.json", bundle["checklists"])
    write_jsonl(target / "inputs.jsonl", inputs)
    write_jsonl(target / "references.jsonl", annotations)
    atomic_json(target / "manifest-rows.json", rows)
    atomic_json(target / "summary.json", summary)
    note = """# Проверенная DEV-разметка

Это неизменяемый снимок текущей разметки, а не независимый test и не обученная модель.

- inputs.jsonl — только входы оценщика; эталонных ответов и подписанных аудиоссылок здесь нет.
- references.jsonl — ответы для последующего сравнения; не передавать их модели вместе с inputs.
- checklists.json — две версии критериев по checklist_hash.
- dataset.json — полный локальный снимок, включая исходные ссылки для ручного прослушивания.
- manifest.json — версия, отпечаток источников и контрольные суммы файлов.
- manifest-rows.json — версии аннотаций; все примеры относятся к development, scenario_group ещё не назначен.

Часть эталонных звонков проверялась человеком по аудио. Текстовый baseline не получает звук:
при анализе расхождений учитывать это различие и показывать такие случаи отдельно.
Исключённые внутренние участки и ограничения лежат в assessment_context эталонных аннотаций.

Файлы содержат пользовательские данные и исключены из Git. Передавайте этот пакет команде
отдельно от публичного репозитория. При изменении разметки создайте новую версию снимка.
"""
    (target / "README.md").write_text(note, encoding="utf-8")
    filenames = ["dataset.json", "checklists.json", "inputs.jsonl", "references.jsonl", "manifest-rows.json", "summary.json", "README.md"]
    manifest = {"schema_version": 1, "release_version": version,
                "created_at": datetime.now(timezone.utc).isoformat(), "source_fingerprint": fingerprint,
                "summary": summary,
                "files_sha256": {name: sha256((target / name).read_bytes()).hexdigest() for name in filenames}}
    atomic_json(manifest_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="dev-reviewed-v1")
    args = parser.parse_args()
    bundle = collect_reviewed(ROOT / "data/raw/dev.json", ROOT / "data/annotations", Path(__file__).parent)
    result = freeze_release(bundle, ROOT / "data/releases", args.version)
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(f"Frozen release: data/releases/{args.version}")


if __name__ == "__main__":
    main()
