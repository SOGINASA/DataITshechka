"""Save two explicitly AI-generated, unreviewed examples under the official chat rubric."""
from pathlib import Path

from server import ROOT, Store, atomic_json, digest, read_json


AUTHOR = "AI-пример (не проверен человеком)"
EXPECTED_HASHES = {
    "p1-ru-001": "5ead9ba9de6be06d483b155b16cb4e0bc0e5676bfae1f4dbde7eaa7c516ab5da",
    "p1-ru-003": "08b025eb92f82ae2d49dd88722c26f78876c3d5176c192402d3b4e33219eedc1",
}


def label(cid, verdict, reason, turns=(), span=None, score=None, confidence="high"):
    return {"criterion_id": cid, "verdict": verdict, "score": score, "reason": reason,
            "confidence": confidence, "evidence_turn_ids": list(turns),
            "checked_span": {"start_turn_id": span[0], "end_turn_id": span[1]} if span else None}


EXAMPLES = {
    "p1-ru-001": [
        label("contact", "pass", "В первом ответе t0010 Алина поздоровалась на русском языке клиента и назвала своё имя. Приветствие бота не учитывалось.", ["t0010"]),
        label("needs", "na", "К моменту подключения оператора уже известны цель (найти название тарифа) и контекст (клиент с ноутбука, не хочет скачивать отчёт). Для инструкции по веб-кабинету уточнений не требовалось.", ["t0001", "t0005"], ("t0001", "t0010")),
        label("identification", "na", "Запрос касается общей навигации: где клиенту самому посмотреть свой тариф. Оператор не раскрывает данные счёта и не выполняет защищённого действия; идентификация не требуется.", ["t0001", "t0010"], ("t0010", "t0012")),
        label("consultation", "score", "Оператор дал конкретный путь в веб-версии и указал место названия тарифа. В t0011 клиент подтвердил, что нашёл его; иных существенных вопросов нет. Это 20 из 20, а не проверка финансовых условий тарифа.", ["t0010", "t0011"], score=20),
        label("empathy", "pass", "Оператор вежлив и отвечает на конкретное неудобство: клиент не хочет скачивать отчёт и работает с ноутбука. Предложена альтернатива через веб-кабинет; разговор завершён доброжелательно.", ["t0005", "t0010", "t0012"], ("t0010", "t0012")),
        label("management", "score", "Короткая инструкция ясна и последовательна, клиент смог ей воспользоваться без переспроса. Во время участия оператора нет явного ожидания, требующего предупреждения. Отдельный трёхминутный порог первой реакции по чек-листу не оценивается.", ["t0010", "t0011", "t0012"], ("t0010", "t0012"), score=10),
        label("closing", "fail", "В t0012 есть вежливое прощание, но нет ни подведения итога оператором, ни предложения дальнейшей помощи. По официальному правилу одного прощания недостаточно. Подтверждение клиента t0011 не заменяет итог со стороны оператора.", ["t0011", "t0012"], ("t0011", "t0012")),
        label("critical_errors", "fail", "В проверенных репликах оператора нет оскорбления, предложения платной услуги в обход компании или раскрытия конфиденциальных данных. Здесь «Нет» означает, что грубая ошибка не выявлена, и не уменьшает балл.", span=("t0010", "t0012")),
    ],
    "p1-ru-003": [
        label("contact", "pass", "В первом ответе t0011 оператор поздоровалась на русском языке клиента и представилась: Лера из поддержки.", ["t0011"]),
        label("needs", "pass", "Из контекста уже известны покупка акций на международном рынке и вопрос о расположении тарифа. Для второго вопроса оператор перед инструкцией уточнила приложение или веб-версию и получила ответ «Через веб». Не требовала повторять уже известный рынок.", ["t0001", "t0005", "t0010", "t0011", "t0012"]),
        label("identification", "na", "Вопросы о комиссии тарифа и навигации являются общими. Оператор не раскрывала сведения конкретного счёта и не выполняла защищённого действия; требование идентификации не возникает.", ["t0001", "t0005", "t0013"], ("t0011", "t0015")),
        label("consultation", "score", "Из двух существенных вопросов закрыт только поиск названия тарифа. Вопрос о комиссии за покупку на международном рынке остался открытым; клиент повторил его в t0014, но оператор снова ответила только про название тарифа. Это ступень 10 из 20, а не 15: пропущена существенная часть запроса.", ["t0001", "t0005", "t0010", "t0013", "t0014", "t0015"], ("t0011", "t0015"), score=10),
        label("empathy", "pass", "Реплики оператора вежливы. Клиент задаёт и повторяет вопросы, но явно не выражает недовольства или отдельного неудобства, требующего специальной реакции. Пропуск комиссии учтён в консультации, а не автоматически продублирован в эмпатии.", ["t0011", "t0013", "t0015"], ("t0011", "t0015"), confidence="medium"),
        label("management", "score", "Уточнение интерфейса и инструкция по поиску тарифа сформулированы ясно и связно. Повтор вопроса о комиссии вызван отсутствием ответа по существу, а не непонятными формулировками. PDF прямо разрешает высокий балл за ведение при частичной консультации. Признаков явного ожидания во время общения с оператором нет.", ["t0011", "t0012", "t0013", "t0014", "t0015"], ("t0011", "t0015"), score=10),
        label("closing", "pass", "Фразу t0015 «Название тарифа смотрите там же» трактую как краткое подведение итога по данной инструкции, а «Хорошего дня!» — как прощание. Это интерпретационный пример: второму разметчику стоит проверить, достаточен ли такой итог по принятой инструкции. Неполнота решения вопроса о комиссии учтена отдельно.", ["t0015"], confidence="medium"),
        label("critical_errors", "fail", "Во всём участке участия оператора не выявлены три основания грубой ошибки: оскорбление, платная услуга в обход компании, раскрытие конфиденциальной информации. Неполный ответ о комиссии сам по себе не входит в этот перечень.", span=("t0011", "t0015")),
    ],
}


def main():
    checklist_path = Path(__file__).with_name("checklist.official.json")
    official = read_json(checklist_path)
    store = Store(ROOT / "data/raw/dev.json", ROOT / "data/annotations", checklist_path)
    if store.checklist_hash != digest(official):
        raise SystemExit("Active checklist differs. Load checklist.official.json before creating examples.")
    for cid, expected in EXPECTED_HASHES.items():
        if store.record(cid)["content_hash"] != expected:
            raise SystemExit(f"Transcript changed for {cid}; re-read it before creating examples.")
    selected = []
    for cid, labels in EXAMPLES.items():
        existing = store.load(cid, AUTHOR)
        if existing:
            print(f"Preserved existing example: {cid}")
            selected.append(existing)
            continue
        rec = store.record(cid)
        saved = store.save({"conversation_id": cid, "content_hash": rec["content_hash"],
                            "checklist_hash": store.checklist_hash, "annotator": AUTHOR,
                            "origin": "ai_example", "revision": 0, "status": "complete",
                            "reviewed": False, "reviewer": "", "labels": labels})
        selected.append(saved)
        print(f"Saved {cid}: {saved['score_summary']['total']:.2f}/100, critical={saved['score_summary']['critical_errors']}")
    for item in selected:
        item["eligible_for_reference"] = store.eligibility(item)
    atomic_json(ROOT / "data/exports/ai-demo-examples.json", {
        "schema_version": 1, "origin": "ai_example", "human_verified": False,
        "warning": "Примеры ИИ по официальному чек-листу, не человеческий эталон. Требуют проверки.",
        "checklist": store.checklist, "checklist_hash": store.checklist_hash,
        "records": [store.record(cid) for cid in EXAMPLES], "annotations": selected})


if __name__ == "__main__":
    main()
