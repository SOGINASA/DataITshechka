// Exercise review transitions with a small DOM adapter and mocked HTTP responses.
// This tests client logic; it does not claim a visual browser inspection.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const directory = path.join(__dirname, '..', 'static');
const html = fs.readFileSync(path.join(directory, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(directory, 'app.js'), 'utf8');
const clone = x => JSON.parse(JSON.stringify(x));

async function setup() {
  const nodes = new Map();
  const created = [];
  class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; this.checked = false; this.disabled = false; this.hidden = false; this.classList = { toggle() {} }; created.push(this); }
    set id(value) { this._id = value; nodes.set(value, this); }
    get id() { return this._id; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(key, value) { this[key] = value; }
    removeAttribute(key) { delete this[key]; }
    addEventListener(key, fn) { (this.listeners[key] ||= []).push(fn); }
    querySelectorAll() { return created; }
    async trigger(key) { for (const fn of this.listeners[key] || []) await fn({ target: this, preventDefault() {} }); }
    remove() {}
    click() { return this.trigger('click'); }
  }
  for (const match of html.matchAll(/id="([^"]+)"/g)) { const node = new Element(); node.id = match[1]; }
  nodes.get('review-phase').value = 'uncertain';
  const criteria = ['opening', 'closing'].map(id => ({ id, name: id, type: 'binary', weight: 10, description: 'rule', pass_rule: 'yes', fail_rule: 'no', na_allowed: false }));
  const record = { conversation_id: 'call-one', language: 'RU', channel: 'voice call', content_hash: 'content', audio_url: 'https://example.invalid/recording', transcript: [
    { turn_id: 't0001', timestamp: '00:01', speaker: 'operator', text: 'Здравствуйте, я оператор.' },
    { turn_id: 't0002', timestamp: '00:02', speaker: 'client', text: 'Спасибо.' }
  ] };
  const labels = criteria.map((c, i) => ({ criterion_id: c.id, verdict: i ? 'uncertain' : 'pass', score: null, reason: i ? 'Неясно без аудио.' : 'Представился.', confidence: i ? 'low' : 'high', evidence_turn_ids: ['t0001'], checked_span: { start_turn_id: 't0001', end_turn_id: 't0002' }, human_checked: !i }));
  let annotation = { conversation_id: record.conversation_id, content_hash: 'content', checklist_hash: 'voice-hash', annotator: 'AI original', origin: 'ai_preannotation', labels, review_baseline: { labels: clone(labels) }, human_verification: { reviewer: 'Пользователь', basis: 'user_confirmation_in_chat' }, assessment_context: { basis: 'transcript_only', audio_reviewed: false, acoustic_observations: { diction: 'not_assessed' }, limitations: [], excluded_turn_spans: [] }, revision: 2, status: 'draft', reviewed: false, reviewer: '', score_summary: { configured: true, total: null, critical_errors: false } };
  const task = { key: 'one-closing', conversation_id: record.conversation_id, profile: 'voice', checklist_hash: 'voice-hash', annotator: annotation.annotator, criterion_id: 'closing', criterion_index: 1, criterion_name: 'closing', channel: 'voice call' };
  const bootstrap = () => ({ checklist: { name: 'voice', version: '1', status: 'official', criteria, applicable_channels: ['voice call'] }, checklist_hash: 'voice-hash', profiles: [{ id: 'voice', name: 'voice', checklist_hash: 'voice-hash' }], records: [record], annotations: [clone(annotation)] });
  const queue = phase => ({ counts: { total: 2, confirmed: annotation.labels.filter(x => x.human_checked).length, uncertain_pending: annotation.labels[1].human_checked ? 0 : 1, other_pending: 0 }, tasks: !annotation.labels[1].human_checked && phase !== 'remaining' ? [task] : [] });
  const calls = [];
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    let data;
    if (url === '/api/bootstrap') data = bootstrap();
    else if (url.startsWith('/api/review/queue')) data = queue(new URL(url, 'http://local').searchParams.get('phase'));
    else if (url === '/api/review/open') data = { annotation: clone(annotation), bootstrap: bootstrap() };
    else if (url.startsWith('/api/annotation?')) data = null;
    else if (url === '/api/annotation') {
      const value = JSON.parse(options.body);
      if (value.labels[1].human_checked && value.labels[1].reason === 'Неясно без аудио.') return { ok: false, json: async () => ({ error: 'Обновите объяснение' }) };
      annotation = { ...value, revision: annotation.revision + 1 };
      data = clone(annotation);
    } else throw new Error('Unexpected request: ' + url);
    return { ok: true, json: async () => clone(data) };
  };
  const document = { getElementById: id => nodes.get(id), createElement: tag => new Element(tag), createDocumentFragment: () => new Element('fragment'), createTextNode: text => ({ textContent: text }), querySelectorAll: () => created, body: new Element('body') };
  const context = vm.createContext({ document, fetch, URL, URLSearchParams, Blob, setTimeout, localStorage: { getItem() { return ''; }, setItem() {} }, window: { location: { search: '?review=1' }, confirm() { return true; }, addEventListener() {} } });
  vm.runInContext(script, context);
  for (let i = 0; i < 25 && !vm.runInContext('state.review.task', context); i++) await new Promise(setImmediate);
  assert.equal(vm.runInContext('state.review.task.criterion_id', context), 'closing');
  return { nodes, calls, context, annotation: () => annotation };
}

test('deep link opens only uncertain criterion in the original author namespace', async () => {
  const page = await setup();
  assert.equal(page.nodes.get('annotator').value, 'AI original');
  assert.equal(page.nodes.get('verdict').value, 'uncertain');
  assert.match(page.nodes.get('review-progress').textContent, /1\/2/);
  assert.equal(page.nodes.get('audio').href, '/audio/call-one');
  assert.equal(page.nodes.get('audio-reviewed').checked, false);
  assert.equal(page.calls.filter(x => x.url === '/api/annotation').length, 0);
});

test('confirm saves the changed criterion and keeps the original author', async () => {
  const page = await setup();
  page.nodes.get('verdict').value = 'pass'; await page.nodes.get('verdict').trigger('change');
  page.nodes.get('reason').value = 'По записи есть итог и прощание.'; await page.nodes.get('reason').trigger('input');
  await page.nodes.get('confirm-next').trigger('click');
  assert.equal(page.annotation().annotator, 'AI original');
  assert.equal(page.annotation().labels[1].human_checked, true);
  assert.equal(page.annotation().labels[0].human_checked, true);
  assert.equal(page.annotation().status, 'complete');
  assert.match(page.nodes.get('review-progress').textContent, /2\/2/);
});

test('postpone does not confirm a label and restarting returns it', async () => {
  const page = await setup();
  await page.nodes.get('review-skip').trigger('click');
  assert.equal(page.annotation().labels[1].human_checked, false);
  assert.equal(page.calls.filter(x => x.url === '/api/annotation').length, 0);
  await page.nodes.get('review-start').trigger('click');
  assert.equal(vm.runInContext('state.review.task.criterion_id', page.context), 'closing');
});

test('failed confirmation keeps the task pending and preserves the edit', async () => {
  const page = await setup();
  page.nodes.get('verdict').value = 'pass'; await page.nodes.get('verdict').trigger('change');
  await page.nodes.get('confirm-next').trigger('click');
  assert.equal(page.annotation().labels[1].human_checked, false);
  assert.equal(vm.runInContext('labelForCurrent().verdict', page.context), 'pass');
  assert.match(page.nodes.get('notice').textContent, /Обновите объяснение/);
});

test('audio is marked only explicitly and unchecking clears acoustic notes', async () => {
  const page = await setup();
  page.nodes.get('audio-reviewed').checked = true; await page.nodes.get('audio-reviewed').trigger('change');
  page.nodes.get('audio-notes').value = 'По аудио реплика различима.'; await page.nodes.get('audio-notes').trigger('input');
  assert.equal(vm.runInContext('state.annotation.assessment_context.basis', page.context), 'transcript_and_audio');
  page.nodes.get('audio-reviewed').checked = false; await page.nodes.get('audio-reviewed').trigger('change');
  assert.equal(page.nodes.get('audio-notes').value, '');
  assert.equal(vm.runInContext('state.annotation.assessment_context.acoustic_observations.notes', page.context), 'not_assessed');
});
