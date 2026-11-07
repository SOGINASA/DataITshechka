"""Record the user's explicit confirmation of existing non-uncertain AI labels.

This imports a confirmation already given in the conversation. It is not automatic
label validation. Never rerun it to approve new edits; existing acknowledgements are skipped.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from server import ROOT, Store


STATEMENT = "я собирался до разметить твою версию так как просмотрели и подтвердили ту разметку которую ты составил"


def main():
    total = checked = pending = 0
    for filename in ("checklist.official.json", "checklist.voice.json"):
        store = Store(ROOT / "data/raw/dev.json", ROOT / "data/annotations", Path(__file__).with_name(filename), use_active_checklist=False)
        for original in store.all_annotations():
            if original.get("origin") != "ai_preannotation":
                continue
            total += len(original["labels"])
            if original.get("human_verification"):
                checked += sum(x.get("human_checked") is True for x in original["labels"])
                pending += sum(x.get("human_checked") is not True for x in original["labels"])
                continue
            annotation = deepcopy(original)
            for label in annotation["labels"]:
                label["human_checked"] = label["verdict"] not in ("", "uncertain")
                if label["human_checked"]:
                    label["review_basis"] = "user_confirmation_in_chat"
            all_checked = all(x["human_checked"] for x in annotation["labels"])
            annotation.update(status="complete" if all_checked else "draft", reviewed=False, reviewer="")
            annotation["human_verification"] = {
                "basis": "user_confirmation_in_chat", "reviewer": "Пользователь",
                "statement": STATEMENT, "recorded_at": datetime.now(timezone.utc).isoformat(),
                "independent_second_review_claimed": False
            }
            saved = store.save(annotation)
            for before, after in zip(original["labels"], saved["labels"]):
                assert all(before.get(k) == after.get(k) for k in ("criterion_id", "verdict", "score", "reason", "confidence", "evidence_turn_ids", "checked_span"))
            checked += sum(x["human_checked"] for x in saved["labels"])
            pending += sum(not x["human_checked"] for x in saved["labels"])
    print(f"Recorded user's confirmation: {checked}/{total} labels; still pending: {pending}")


if __name__ == "__main__":
    main()
