const el = (id) => document.getElementById(id);
const source = el('source');
const fields = el('input-fields');
const format = el('format');
let selected = null;
let poll;
let generation = 0;
let connectionReady = false;
let activeJob = null;
let knowledge = null;
const knowledgeFile = el('knowledge-file-input');
const knowledgeFileName = el('knowledge-file-name');
const example = 'Клиент: Здравствуйте! Подскажите, как связаться с поддержкой?\nОператор: Здравствуйте! Меня зовут Алина. Вы уже в чате поддержки. Чем могу помочь?\nКлиент: Спасибо, пока вопросов нет.\nОператор: Если появятся вопросы, обращайтесь. Хорошего дня!';
function node(tag, text = '', className = '') {
    const n = document.createElement(tag);
    n.textContent = text;
    n.className = className;
    return n;
}
async function api(path, data) {
    const hasKnowledge = Boolean(data && typeof data === 'object' && 'knowledge' in data && data.knowledge);
    const response = await fetch(path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', ...(hasKnowledge ? { 'X-ML2-Knowledge': '1' } : {}) }, body: JSON.stringify(data) });
    const body = await response.json();
    if (!response.ok)
        throw new Error(body.error || 'Не удалось выполнить запрос.');
    return body;
}
function error(message = '') { const n = el('form-error'); n.textContent = message; n.hidden = !message; }
function controls() {
    el('format-help').textContent = format.value === 'text' ? 'Каждую реплику начинайте с «Клиент:», «Оператор:», «Бот:» или «Система:».' : 'Один объект диалога или массив реплик. Язык, канал и ID из JSON сохраняются.';
    el('truncated-label').hidden = el('channel').value !== 'call';
}
function answer(r) {
    if (r.status === 'needs_review')
        return 'Нужна проверка';
    if (r.status === 'not_applicable')
        return 'N/A';
    if (typeof r.value === 'boolean')
        return r.value ? 'Да' : 'Нет';
    return String(r.value);
}
function render(job) {
    selected = job;
    const pending = job.status === 'running';
    fields.disabled = pending;
    el('example').disabled = pending;
    el('submit').disabled = !connectionReady || Boolean(activeJob);
    el('progress').hidden = !pending;
    el('download').hidden = job.status !== 'done';
    const result = el('result');
    result.replaceChildren();
    if (pending) {
        const empty = node('div', '', 'empty');
        empty.append(node('h3', 'Ищем основания для оценки'), node('p', 'Можно обновить страницу — запуск продолжится.'));
        result.append(empty);
        return;
    }
    if (job.status === 'error') {
        const message = job.error_code === 'generation_limit' ? 'Модель исчерпала лимит генерации и не завершила ответ. Входной диалог принят; это ошибка обработки моделью.' :
            job.error_code === 'context_budget_exceeded' ? job.error || 'Запрос не помещается в контекст модели. Диалог сохранён без обрезки.' :
            job.error_code === 'generation_incomplete' || job.error === 'Generation incomplete; no partial success saved' ? 'Модель остановилась до завершения ответа. Входной диалог принят; это ошибка обработки моделью.' : job.error || 'Неизвестная ошибка.';
        const failure = node('div', '', 'failure');
        failure.append(node('h3', 'Оценка не завершена'), node('p', message), node('small', 'Диалог сохранён. Можно повторить запуск; частичная оценка не выдаётся за готовую.'));
        result.append(failure);
        return;
    }
    const evaluation = job.result;
    const summary = evaluation.summary;
    const line = node('div', '', 'scoreline');
    const scoreBox = node('div');
    scoreBox.append(node('div', 'Общая оценка', 'score-label'));
    const score = node('div', summary.final_score === null ? '—' : summary.final_score.toLocaleString('ru-RU'), 'score');
    score.append(node('small', ' / 100'));
    scoreBox.append(score);
    const critical = summary.gross_error_detected;
    line.append(scoreBox, node('span', critical === true ? 'Грубая ошибка' : critical === false ? 'Без грубых ошибок' : 'Флаг требует проверки', `badge ${critical === true ? 'bad' : critical === null ? 'review' : ''}`));
    result.append(line);
    if (summary.unresolved_criteria.length)
        result.append(node('p', 'Есть критерии, для которых недостаточно данных. Они не заменены на N/A.', 'partial-note'));
    const criteria = new Map(job.rubric.criteria.map(c => [c.id, c]));
    for (const criterion of evaluation.results) {
        const config = criteria.get(criterion.criterion_id);
        const max = Math.max(...(config?.scale || []).map(s => s.value));
        const partial = typeof criterion.value === 'number' && criterion.value < max;
        const label = typeof criterion.value === 'number' && Number.isFinite(max) ? `${criterion.value} / ${max}` : answer(criterion);
        const detail = node('details', '', 'criterion');
        const heading = node('summary');
        heading.append(node('span', config?.title || criterion.criterion_id, 'criterion-name'), node('span', label, `badge ${criterion.status === 'fail' ? 'bad' : criterion.status === 'needs_review' || partial ? 'review' : criterion.status === 'not_applicable' ? 'neutral' : ''}`));
        const body = node('div', '', 'criterion-body');
        body.append(node('p', criterion.explanation));
        if (criterion.knowledge_status === 'missing')
            body.append(node('p', 'Не найден официальный источник для проверки существенного факта; оценка отправлена на проверку.', 'partial-note'));
        else if (criterion.knowledge_status === 'conflict')
            body.append(node('p', 'В доступных официальных источниках найдено противоречие; оценка отправлена на проверку.', 'partial-note'));
        else if (criterion.knowledge_status === 'supported' && criterion.knowledge_refs.length)
            body.append(node('p', `Источники знаний: ${criterion.knowledge_refs.join(', ')}`, 'help'));
        for (const evidence of criterion.evidence) {
            const quote = node('blockquote');
            quote.append(node('small', `Реплика ${evidence.message_id}`), document.createTextNode(evidence.quote));
            body.append(quote);
        }
        if (criterion.reviewed_range)
            body.append(node('p', `Просмотрены реплики ${criterion.reviewed_range.start_message_id}–${criterion.reviewed_range.end_message_id}`, 'help'));
        detail.append(heading, body);
        result.append(detail);
    }
}
async function history() {
    const jobs = await api('/api/jobs');
    const box = el('history-list');
    box.replaceChildren();
    activeJob = jobs.find(j => j.status === 'running')?.id || null;
    el('submit').disabled = !connectionReady || Boolean(activeJob);
    if (!jobs.length)
        box.append(node('p', 'Проверок пока нет.', 'help'));
    for (const job of jobs) {
        const row = node('button', '', 'history-row');
        row.type = 'button';
        row.append(node('span', job.conversation_id, 'history-name'), node('time', new Date(job.created_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })), node('span', job.status === 'running' ? 'Идёт оценка' : job.status === 'done' ? 'Готово' : 'Ошибка', `badge ${job.status === 'error' ? 'bad' : job.status === 'running' ? 'review' : ''}`));
        row.addEventListener('click', () => void selectJob(job.id, true));
        box.append(row);
    }
    return jobs;
}
async function selectJob(id, fill = false) {
    const current = ++generation;
    clearTimeout(poll);
    try {
        const job = await api('/api/jobs/' + id);
        if (current !== generation)
            return;
        localStorage.setItem('ml2-job', id);
        if (fill && job.input) {
            format.value = 'json';
            source.value = JSON.stringify(job.input, null, 2);
            controls();
        }
        render(job);
        if (job.status === 'running')
            poll = setTimeout(() => void selectJob(id), 2000);
        else
            await history();
    }
    catch (e) {
        if (current !== generation)
            return;
        error('Связь с локальным сервером потеряна. Обновите страницу после его запуска.');
        poll = setTimeout(() => void selectJob(id), 5000);
    }
}
async function health() {
    const status = await api('/api/status');
    connectionReady = status.ready;
    activeJob = status.active;
    el('model-status').textContent = status.ready ? `${status.model} · на компьютере` : 'Модель недоступна · проверьте Ollama';
    el('model-status').className = `model-status ${status.ready ? 'ready' : ''}`;
    el('submit').disabled = !connectionReady || Boolean(activeJob);
    return status;
}
el('evaluate-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    error();
    fields.disabled = true;
    el('example').disabled = true;
    try {
        const job = await api('/api/jobs', { source: source.value, format: format.value, language: el('language').value, channel: el('channel').value, start_truncated: el('truncated').checked, knowledge: knowledge ?? undefined, knowledge_as_of: el('knowledge-as-of').value || undefined });
        render(job);
        await selectJob(job.id);
        await history();
        if (matchMedia('(max-width:950px)').matches)
            el('result-title').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion:reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    }
    catch (e) {
        error(e.message);
        fields.disabled = false;
        el('example').disabled = false;
    }
});
knowledgeFile.addEventListener('change', async () => {
    const file = knowledgeFile.files?.[0];
    if (!file) {
        knowledge = null;
        knowledgeFileName.textContent = 'База знаний не подключена';
        return;
    }
    try {
        if (file.size > 1024 * 1024)
            throw new Error('Файл базы знаний должен быть не больше 1 МБ.');
        const parsed = JSON.parse(await file.text());
        if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.documents))
            throw new Error('Ожидается JSON базы знаний с полями version и documents.');
        knowledge = parsed;
        knowledgeFileName.textContent = `${file.name} · ${parsed.documents.length} выдержек`;
        error();
    }
    catch (e) {
        knowledge = null;
        knowledgeFileName.textContent = 'База знаний не подключена';
        error(e.message);
    }
    finally {
        knowledgeFile.value = '';
    }
});
el('example').addEventListener('click', () => { source.value = example; format.value = 'text'; el('language').value = 'ru'; el('channel').value = 'chat'; el('truncated').checked = false; controls(); error(); source.focus(); });
format.addEventListener('change', controls);
el('channel').addEventListener('change', controls);
el('file-input').addEventListener('change', async (event) => {
    const input = event.target;
    const file = input.files?.[0];
    if (!file)
        return;
    try {
        if (file.size > 1024 * 1024)
            throw new Error('Выберите файл размером до 1 МБ.');
        source.value = await file.text();
        format.value = file.name.toLowerCase().endsWith('.json') ? 'json' : 'text';
        controls();
        error();
    }
    catch (e) {
        error(e.message);
    }
    finally {
        input.value = '';
    }
});
el('download').addEventListener('click', () => {
    if (!selected?.result)
        return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(selected.result, null, 2)], { type: 'application/json' }));
    const link = node('a');
    link.href = url;
    link.download = `ml2-${selected.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
});
el('refresh').addEventListener('click', () => void Promise.all([health(), history()]).catch(() => error('Локальный сервер недоступен.')));
setInterval(() => { if (selected?.status !== 'running')
    return; const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(selected.created_at)) / 1000)); el('elapsed').textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`; }, 1000);
setInterval(() => { if (activeJob && selected?.id !== activeJob)
    void history().catch(() => { }); }, 5000);
void (async () => {
    try {
        const status = await health();
        const jobs = await history();
        const saved = localStorage.getItem('ml2-job');
        const id = status.active || (jobs.some(j => j.id === saved) ? saved : null);
        if (id)
            await selectJob(id, true);
    }
    catch {
        error('Не удалось подключиться к локальному серверу. Обновите страницу.');
    }
})();
export {};
