"""Local, dependency-free CQA annotation tool. Run: python annotation/server.py."""
from __future__ import annotations

import argparse
from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from html import escape
import math
from pathlib import Path
import threading
from urllib.parse import parse_qs, quote, unquote, urlsplit
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
PROFILES = {"chat": "checklist.official.json", "voice": "checklist.voice.json",
            "voice_v2": "checklist.voice.v2.json"}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def validate_checklist(value):
    if not isinstance(value, dict):
        raise ValueError("Чек-лист должен быть JSON-объектом.")
    for key in ("name", "version", "source"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError(f"Заполните поле чек-листа: {key}.")
    if value.get("status") not in ("demo", "official"):
        raise ValueError("status чек-листа: demo или official.")
    criteria = value.get("criteria")
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 50:
        raise ValueError("В чек-листе должно быть от 1 до 50 критериев.")
    ids = set()
    for c in criteria:
        if not isinstance(c, dict):
            raise ValueError("Критерий должен быть объектом.")
        for key in ("id", "name", "description", "pass_rule", "fail_rule"):
            if not isinstance(c.get(key), str) or not c[key].strip():
                raise ValueError(f"Заполните поле критерия: {key}.")
        if c["id"] in ids:
            raise ValueError("ID критериев должны быть уникальны.")
        ids.add(c["id"])
        if c.get("type") not in ("binary", "ordinal"):
            raise ValueError("type критерия: binary или ordinal.")
        if type(c.get("na_allowed")) is not bool:
            raise ValueError("na_allowed должен быть true или false.")
        if c["na_allowed"] and not str(c.get("na_rule", "")).strip():
            raise ValueError("Укажите правило применимости N/A.")
        if c["type"] == "ordinal":
            scores = c.get("allowed_scores")
            if (not isinstance(scores, list) or len(scores) < 2
                or any(type(s) not in (int, float) or not math.isfinite(s) for s in scores)
                or len(set(scores)) != len(scores) or scores != sorted(scores)):
                raise ValueError("allowed_scores: возрастающий список уникальных чисел, минимум два.")
        if "weight" in c and (type(c["weight"]) not in (int, float)
                              or not math.isfinite(c["weight"]) or c["weight"] < 0):
            raise ValueError("Вес должен быть конечным неотрицательным числом.")
        if "is_critical" in c and type(c["is_critical"]) is not bool:
            raise ValueError("is_critical должен быть true или false.")
        if c.get("is_critical") and (c["type"] != "binary" or c.get("weight", 0) != 0):
            raise ValueError("Грубая ошибка — отдельный бинарный флаг без веса.")
        if "positive_evidence_roles" in c:
            roles = c["positive_evidence_roles"]
            if not isinstance(roles, list) or not roles or any(r not in ("operator", "system") for r in roles):
                raise ValueError("Для положительного ответа допустимы роли operator и/или system.")
    weighted = [c for c in criteria if not c.get("is_critical")]
    if any("weight" in c for c in weighted):
        if any("weight" not in c for c in weighted):
            raise ValueError("Укажите вес каждого критерия с баллами.")
        if any(c["type"] == "ordinal" and (min(c["allowed_scores"]) < 0 or max(c["allowed_scores"]) <= 0)
               for c in weighted):
            raise ValueError("Взвешенная шкала должна быть неотрицательной с положительным максимумом.")
    if "applicable_channels" in value and (not isinstance(value["applicable_channels"], list)
        or not value["applicable_channels"]
        or any(x not in ("agent chat", "voice call") for x in value["applicable_channels"])):
        raise ValueError("applicable_channels: список agent chat и/или voice call.")
    # JSON round-trip rejects NaN and detaches the caller's mutable objects.
    return json.loads(json.dumps(value, allow_nan=False))


def calculate_score(checklist, labels):
    """Deterministic weighted score. Critical flags never silently zero the total."""
    by_id = {x["criterion_id"]: x for x in labels}
    weighted = [c for c in checklist["criteria"] if not c.get("is_critical")]
    configured = bool(weighted) and all("weight" in c for c in weighted)
    earned, applicable = Decimal(0), Decimal(0)
    pending, critical = [], []
    for c in checklist["criteria"]:
        label = by_id.get(c["id"], {})
        verdict = label.get("verdict", "")
        if c.get("is_critical"):
            critical.append(True if verdict == "pass" else False if verdict == "fail" else None)
            continue
        if not configured or c["weight"] == 0:
            continue
        if verdict in ("", "uncertain"):
            pending.append(c["id"])
            continue
        if verdict == "na":
            continue
        weight = Decimal(str(c["weight"]))
        applicable += weight
        if c["type"] == "binary":
            earned += weight if verdict == "pass" else Decimal(0)
        else:
            earned += weight * Decimal(str(label["score"])) / Decimal(str(max(c["allowed_scores"])))
    total = None
    if configured and not pending and applicable:
        total = float((100 * earned / applicable).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    critical_flag = True if True in critical else None if None in critical or not critical else False
    return {"configured": configured, "total": total,
            "earned_before_na": float(earned), "applicable_weight": float(applicable),
            "pending_criteria": pending, "critical_errors": critical_flag}


class Store:
    def __init__(self, dataset, output, checklist, *, use_active_checklist=True):
        self.output = Path(output)
        self.lock = threading.RLock()
        envelope = read_json(dataset)
        if not isinstance(envelope, dict) or envelope.get("isSuccess") is not True:
            raise ValueError("Нужен успешный полный JSON-ответ API с data.records.")
        records = envelope.get("data", {}).get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("В data.records нет диалогов.")
        self.records = {}
        for raw in records:
            if not isinstance(raw, dict) or not isinstance(raw.get("conversation_id"), str):
                raise ValueError("У диалога отсутствует строковый conversation_id.")
            cid = raw["conversation_id"]
            turns = raw.get("transcript")
            if cid in self.records or not isinstance(turns, list) or not turns:
                raise ValueError("Повтор ID диалога или пустой транскрипт.")
            if any(not isinstance(t, dict) or not isinstance(t.get("text"), str)
                   or t.get("speaker") not in ("client", "operator", "bot", "system")
                   or not isinstance(t.get("timestamp"), str) for t in turns):
                raise ValueError("Некорректная реплика в транскрипте.")
            # Audio URL may expire/change without changing the annotation target.
            fingerprint = digest({k: raw.get(k) for k in
                                  ("conversation_id", "language", "channel", "transcript")})
            self.records[cid] = {**raw, "content_hash": fingerprint,
                                   "transcript": [{**t, "turn_id": f"t{i:04d}"}
                                                  for i, t in enumerate(turns, 1)]}
        active = self.output / "active-checklist.json"
        self.checklist = validate_checklist(read_json(active if use_active_checklist and active.exists() else checklist))

    def profiles(self):
        result = []
        for key, filename in PROFILES.items():
            path = Path(__file__).with_name(filename)
            if path.exists():
                value = validate_checklist(read_json(path))
                result.append({"id": key, "name": value["name"], "checklist_hash": digest(value),
                               "applicable_channels": value.get("applicable_channels", [])})
        return result

    def select_profile(self, key):
        if key not in PROFILES:
            raise ValueError("Неизвестный профиль чек-листа.")
        return self.set_checklist(read_json(Path(__file__).with_name(PROFILES[key])))

    @property
    def checklist_hash(self):
        return digest(self.checklist)

    def set_checklist(self, value):
        candidate = validate_checklist(value)
        with self.lock:
            atomic_json(self.output / "active-checklist.json", candidate)
            self.checklist = candidate
        return {"checklist": candidate, "checklist_hash": digest(candidate)}

    def record(self, cid):
        if cid not in self.records:
            raise ValueError("Неизвестный диалог.")
        return self.records[cid]

    def annotation_path(self, cid, annotator):
        self.record(cid)
        return (self.output / self.checklist_hash / digest(annotator) /
                f"{digest(cid)}.json")

    def load(self, cid, annotator):
        path = self.annotation_path(cid, annotator)
        return read_json(path) if path.exists() else None

    def all_annotations(self):
        directory = self.output / self.checklist_hash
        if not directory.exists():
            return []
        return [read_json(p) for p in sorted(directory.glob("*/*.json"))]

    def eligibility(self, value):
        rec = self.records.get(value.get("conversation_id"))
        return bool(rec and value.get("content_hash") == rec["content_hash"]
                    and value.get("checklist_hash") == self.checklist_hash
                    and self.checklist["status"] == "official"
                    and (value.get("origin", "human") == "human" or
                         (value.get("origin") == "ai_preannotation" and value.get("human_verification")
                          and all(x.get("human_checked") is True for x in value.get("labels", []))))
                    and rec.get("channel") in self.checklist.get("applicable_channels", ["agent chat", "voice call"])
                    and value.get("status") == "complete"
                    and value.get("reviewed") is True
                    and value.get("labels")
                    and all(x.get("verdict") not in ("", "uncertain") for x in value["labels"]))

    def bootstrap(self):
        annotations = self.all_annotations()
        return {"checklist": self.checklist, "checklist_hash": self.checklist_hash,
                "profiles": self.profiles(),
                "records": list(self.records.values()),
                "annotations": [{k: x.get(k) for k in
                                 ("conversation_id", "annotator", "status", "reviewed", "content_hash", "origin", "score_summary")}
                                for x in annotations],
                "counts": dict(Counter(r.get("language") for r in self.records.values()))}

    def save(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Нужен JSON-объект разметки.")
        with self.lock:
            return self._save(payload)

    def _save(self, p):
        cid = p.get("conversation_id")
        if not isinstance(cid, str):
            raise ValueError("Укажите ID диалога.")
        rec = self.record(cid)
        annotator = p.get("annotator")
        if not isinstance(annotator, str) or not 1 <= len(annotator.strip()) <= 100:
            raise ValueError("Укажите имя разметчика, максимум 100 символов.")
        annotator = annotator.strip()
        if p.get("checklist_hash") != self.checklist_hash:
            raise ValueError("Чек-лист изменился. Обновите страницу.")
        if p.get("content_hash") != rec["content_hash"]:
            raise ValueError("Транскрипт изменился. Перечитайте и разметьте текущую версию.")
        status = p.get("status")
        if status not in ("draft", "complete"):
            raise ValueError("Статус: draft или complete.")
        old = self.load(cid, annotator)
        revision = old["revision"] if old else 0
        if type(p.get("revision")) is not int or p["revision"] != revision:
            raise ValueError("Разметка изменена в другой вкладке. Перезагрузите диалог.")
        labels = p.get("labels")
        if not isinstance(labels, list) or any(not isinstance(x, dict) for x in labels):
            raise ValueError("labels должен быть массивом объектов.")
        by_id = {x.get("criterion_id"): x for x in labels if isinstance(x.get("criterion_id"), str)}
        ids = {c["id"] for c in self.checklist["criteria"]}
        if len(by_id) != len(labels) or set(by_id) != ids:
            raise ValueError("Нужна ровно одна запись для каждого критерия текущего чек-листа.")
        turns = {t["turn_id"]: t for t in rec["transcript"]}
        order = {tid: i for i, tid in enumerate(turns)}
        cleaned = []
        for criterion in self.checklist["criteria"]:
            x = by_id[criterion["id"]]
            verdict = x.get("verdict", "")
            allowed = {"", "uncertain", "na"}
            allowed |= {"pass", "fail"} if criterion["type"] == "binary" else {"score"}
            if verdict not in allowed or (verdict == "na" and not criterion["na_allowed"]):
                raise ValueError(f"Недопустимый ответ: {criterion['name']}.")
            score = x.get("score")
            if verdict == "score":
                if type(score) not in (int, float) or score not in criterion["allowed_scores"]:
                    raise ValueError("Баллы должны соответствовать шкале критерия.")
            else:
                score = None
            reason = x.get("reason", "")
            confidence = x.get("confidence", "medium")
            evidence_ids = x.get("evidence_turn_ids", [])
            if not isinstance(reason, str) or confidence not in ("high", "medium", "low"):
                raise ValueError("Проверьте объяснение и уверенность разметчика.")
            if (not isinstance(evidence_ids, list) or any(not isinstance(t, str) or t not in turns for t in evidence_ids)
                or len(evidence_ids) != len(set(evidence_ids))):
                raise ValueError("Доказательство ссылается на несуществующую или повторную реплику.")
            span = x.get("checked_span")
            if span is not None:
                if (not isinstance(span, dict) or not isinstance(span.get("start_turn_id"), str)
                    or not isinstance(span.get("end_turn_id"), str)
                    or span["start_turn_id"] not in turns or span["end_turn_id"] not in turns
                    or order[span["start_turn_id"]] > order[span["end_turn_id"]]):
                    raise ValueError("Некорректные границы проверенного участка.")
                span = {k: span[k] for k in ("start_turn_id", "end_turn_id")}
            if status == "complete" or x.get("human_checked") is True:
                if not verdict or not reason.strip():
                    raise ValueError(f"Заполните ответ и объяснение: {criterion['name']}.")
                if verdict != "uncertain" and not evidence_ids and span is None:
                    raise ValueError(f"Укажите доказательство или проверенный участок: {criterion['name']}.")
                positive = verdict == "pass" or (verdict == "score" and score > min(criterion["allowed_scores"]))
                positive_roles = criterion.get("positive_evidence_roles", ["operator"])
                if positive and not any(turns[tid]["speaker"] in positive_roles for tid in evidence_ids):
                    raise ValueError(f"Для положительной оценки нужна реплика роли {', '.join(positive_roles)}: {criterion['name']}.")
            cleaned.append({"criterion_id": criterion["id"], "verdict": verdict,
                            "score": score, "reason": reason.strip(), "confidence": confidence,
                            "evidence_turn_ids": evidence_ids, "checked_span": span,
                            "evidence": [turns[tid] for tid in evidence_ids]})
        assessment = p.get("assessment_context")
        if assessment is not None:
            if not isinstance(assessment, dict):
                raise ValueError("assessment_context должен быть объектом.")
            basis, audio_reviewed = assessment.get("basis"), assessment.get("audio_reviewed")
            if basis not in ("transcript_only", "transcript_and_audio") or type(audio_reviewed) is not bool:
                raise ValueError("Укажите основание оценки и факт прослушивания аудио.")
            if audio_reviewed != (basis == "transcript_and_audio"):
                raise ValueError("Основание оценки противоречит факту прослушивания.")
            limitations = assessment.get("limitations", [])
            if not isinstance(limitations, list) or any(not isinstance(x, str) for x in limitations):
                raise ValueError("Ограничения оценки должны быть списком строк.")
            acoustics = assessment.get("acoustic_observations", {})
            if not isinstance(acoustics, dict) or any(not isinstance(v, str) for v in acoustics.values()):
                raise ValueError("Акустические наблюдения должны быть текстовыми.")
            if not audio_reviewed and any(v != "not_assessed" for v in acoustics.values()):
                raise ValueError("Нельзя оценивать акустические характеристики без прослушивания аудио.")
            excluded = assessment.get("excluded_turn_spans", [])
            if not isinstance(excluded, list):
                raise ValueError("Исключённые участки должны быть списком.")
            excluded_ids = set()
            for section in excluded:
                if (not isinstance(section, dict) or section.get("start_turn_id") not in order
                    or section.get("end_turn_id") not in order
                    or order[section["start_turn_id"]] > order[section["end_turn_id"]]
                    or not isinstance(section.get("reason"), str) or not section["reason"].strip()):
                    raise ValueError("Некорректный исключённый участок.")
                excluded_ids.update(tid for tid in order if order[section["start_turn_id"]] <= order[tid] <= order[section["end_turn_id"]])
            if any(excluded_ids.intersection(x["evidence_turn_ids"]) for x in cleaned):
                raise ValueError("Внутренний исключённый участок нельзя выдавать за доказательство общения с клиентом.")
            assessment = {"basis": basis, "audio_reviewed": audio_reviewed,
                          "limitations": limitations, "acoustic_observations": acoustics,
                          "excluded_turn_spans": excluded}
        reviewed = p.get("reviewed", False)
        reviewer = p.get("reviewer", "")
        if type(reviewed) is not bool or not isinstance(reviewer, str):
            raise ValueError("Проверьте поля проверки разметки.")
        reviewer = reviewer.strip()
        origin = p.get("origin", "human")
        if origin not in ("human", "ai_example", "ai_preannotation"):
            raise ValueError("origin: human, ai_example или ai_preannotation.")
        verification = p.get("human_verification", old.get("human_verification") if old else None)
        baseline = deepcopy(old.get("review_baseline")) if old else None
        if verification is not None:
            if (not isinstance(verification, dict) or not isinstance(verification.get("reviewer"), str)
                or not verification["reviewer"].strip() or len(verification["reviewer"]) > 100
                or verification["reviewer"].strip().casefold() == annotator.casefold()
                or verification.get("basis") not in ("user_confirmation_in_chat", "manual_ui")):
                raise ValueError("Укажите источник человеческого подтверждения и имя проверяющего.")
            verification = deepcopy(verification)
            verification["reviewer"] = verification["reviewer"].strip()
            if baseline is None and old:
                baseline = {"revision": old["revision"], "labels": deepcopy(old["labels"]),
                            "assessment_context": deepcopy(old.get("assessment_context"))}
            original = {x["criterion_id"]: x for x in (baseline or {}).get("labels", [])}
            previous = {x["criterion_id"]: x for x in old["labels"]} if old else {}
            for label in cleaned:
                supplied = by_id[label["criterion_id"]]
                checked = supplied.get("human_checked", False)
                if type(checked) is not bool:
                    raise ValueError("human_checked должен быть true или false.")
                if checked and label["verdict"] in ("", "uncertain"):
                    raise ValueError("Нельзя подтвердить «не уверен»: выберите окончательный ответ или отложите.")
                initial = original.get(label["criterion_id"], {})
                if checked and initial.get("verdict") == "uncertain" and label["reason"] == initial.get("reason", "").strip():
                    raise ValueError("Обновите объяснение: прежнее обоснование ИИ описывает неопределённость.")
                label["human_checked"] = checked
                if checked:
                    before = previous.get(label["criterion_id"], {})
                    same = all(label.get(k) == before.get(k) for k in ("verdict", "score", "reason", "confidence", "evidence_turn_ids", "checked_span"))
                    label["human_checked_at"] = before.get("human_checked_at") if same and before.get("human_checked_at") else datetime.now(timezone.utc).isoformat()
                    label["human_checked_by"] = verification["reviewer"]
                    label["review_basis"] = supplied.get("review_basis", "manual_ui")
            fully_checked = all(x.get("human_checked") is True for x in cleaned)
            if status == "complete" and not fully_checked:
                raise ValueError("В диалоге ещё есть неподтверждённые оценки. Сохраните черновик или проверьте их.")
            reviewed = fully_checked and status == "complete"
            reviewer = verification["reviewer"] if reviewed else ""
        if reviewed and (status != "complete" or not reviewer or len(reviewer) > 100
                         or reviewer.casefold() == annotator.casefold()
                         or any(x["verdict"] in ("", "uncertain") for x in cleaned)):
            raise ValueError("Проверку отмечает другой человек: все ответы завершены, спорные случаи разрешены.")
        saved = {"schema_version": 1, "conversation_id": cid, "language": rec.get("language"),
                 "channel": rec.get("channel"), "content_hash": rec["content_hash"],
                 "checklist_hash": self.checklist_hash, "checklist": self.checklist,
                 "annotator": annotator, "status": status, "reviewed": reviewed,
                 "origin": origin,
                 "reviewer": reviewer if reviewed else "", "labels": cleaned,
                 "score_summary": calculate_score(self.checklist, cleaned),
                 "revision": revision + 1, "updated_at": datetime.now(timezone.utc).isoformat()}
        if assessment is not None:
            saved["assessment_context"] = assessment
        if verification is not None:
            saved["human_verification"] = verification
        if baseline is not None:
            saved["review_baseline"] = baseline
        if old and old.get('policy_migration'):
            saved['policy_migration'] = deepcopy(old['policy_migration'])
        path = self.annotation_path(cid, annotator)
        if old:
            atomic_json(path.parent / "history" / f"{path.stem}-{revision}.json", old)
        atomic_json(path, saved)
        return saved

    def export(self):
        annotations = self.all_annotations()
        for x in annotations:
            x["eligible_for_reference"] = self.eligibility(x)
        return {"schema_version": 1, "checklist": self.checklist,
                "checklist_hash": self.checklist_hash,
                "warning": "Демо, непроверенные, спорные и устаревшие оценки не являются эталоном. Разделите диалоги до обучения.",
                "records": list(self.records.values()), "annotations": annotations}


def handler_for(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log dialogue content or URL parameters.

        def respond(self, status, content, content_type="application/json; charset=utf-8", download=None):
            body = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def local_request(self):
            port = self.server.server_port
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in hosts and (not origin or origin in {f"http://{h}" for h in hosts})

        def do_GET(self):
            if not self.local_request():
                self.respond(403, {"error": "Разрешён только локальный доступ."})
                return
            url = urlsplit(self.path)
            try:
                with store.lock:
                    if url.path == "/api/bootstrap":
                        self.respond(200, store.bootstrap())
                    elif url.path == "/api/review/queue":
                        from review import build_queue
                        self.respond(200, build_queue(store, parse_qs(url.query).get("phase", ["uncertain"])[0]))
                    elif url.path == "/api/annotation":
                        q = parse_qs(url.query)
                        self.respond(200, store.load(q.get("conversation_id", [""])[0], q.get("annotator", [""])[0]))
                    elif url.path == "/api/export":
                        self.respond(200, store.export(), download="cqa-annotations.json")
                    elif url.path == "/audio":
                        links = [f'<li><a href="/audio/{quote(r["conversation_id"], safe="")}" target="_blank" rel="noopener noreferrer">{escape(r["conversation_id"])}</a> — открыть запись</li>'
                                 for r in store.records.values() if r.get("audio_url")]
                        html = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Записи звонков</title><link rel="stylesheet" href="/style.css"><header><h1>Записи пяти звонков</h1><a href="/?review=1">К разметке</a></header><section class="recordings-list"><p>Ссылки на записи из исходного DEV-набора. После прослушивания вернитесь к разметке и отметьте «Аудио прослушано».</p><ul>' + ''.join(links) + '</ul></section></html>'
                        self.respond(200, html.encode("utf-8"), "text/html; charset=utf-8")
                    elif url.path.startswith("/audio/"):
                        record = store.record(unquote(url.path[len("/audio/"):]))
                        target = record.get("audio_url")
                        if not isinstance(target, str) or urlsplit(target).scheme not in ("http", "https") or any(c in target for c in "\r\n"):
                            raise ValueError("У диалога нет допустимой ссылки на запись.")
                        self.send_response(302)
                        self.send_header("Location", target)
                        self.send_header("Cache-Control", "no-store")
                        self.send_header("Referrer-Policy", "no-referrer")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                    elif url.path in ("/", "/app.js", "/style.css"):
                        name = "index.html" if url.path == "/" else url.path[1:]
                        mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
                        self.respond(200, (STATIC / name).read_bytes(), mime + "; charset=utf-8")
                    else:
                        self.respond(404, {"error": "Не найдено."})
            except (ValueError, KeyError):
                self.respond(400, {"error": "Некорректный запрос."})
            except OSError:
                self.respond(500, {"error": "Ошибка чтения локального файла. Проверьте терминал и доступ к папке."})

        def do_POST(self):
            if not self.local_request():
                self.respond(403, {"error": "Разрешён только локальный доступ."})
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Нужен Content-Type: application/json.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 2_000_000:
                    raise ValueError("Недопустимый размер запроса.")
                data = json.loads(self.rfile.read(length))
                with store.lock:
                    if self.path == "/api/annotation":
                        self.respond(200, store.save(data))
                    elif self.path == "/api/review/open":
                        from review import open_task
                        self.respond(200, open_task(store, data))
                    elif self.path == "/api/checklist":
                        self.respond(200, store.set_checklist(data))
                    elif self.path == "/api/checklist/select":
                        self.respond(200, store.select_profile(data.get("profile")))
                    else:
                        self.respond(404, {"error": "Не найдено."})
            except (ValueError, KeyError, TypeError) as exc:
                self.respond(400, {"error": str(exc) if isinstance(exc, ValueError) else "Некорректная структура JSON."})
            except OSError:
                self.respond(500, {"error": "Не удалось сохранить файл. Проверьте доступ к папке разметки."})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/raw/dev.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/annotations")
    parser.add_argument("--checklist", type=Path, default=Path(__file__).with_name("checklist.official.json"))
    parser.add_argument("--open", action="store_true", help="Open the local tool in a browser")
    args = parser.parse_args()
    try:
        store = Store(args.dataset, args.output, args.checklist)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(store))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Cannot start annotation tool: {exc}\n")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"CQA annotation: {url}\nRecords: {len(store.records)} | checklist: {store.checklist['status']}\nCtrl+C to stop.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
