// Run the real app entrypoint/event handlers with a minimal DOM adapter.
// This verifies routing/request behavior, not layout or browser rendering.
import test from 'node:test';
import assert from 'node:assert/strict';

test('app navigation keeps bounded requests, global badges and single viewport listeners', async () => {
  const nodes = new Map();
  const listeners = () => ({
    handlers: new Map(),
    addEventListener(name, fn) {
      const handlers = this.handlers.get(name) || [];
      handlers.push(fn); this.handlers.set(name, handlers);
    },
    async dispatch(name, event = {}) {for (const fn of this.handlers.get(name) || []) await fn(event);},
  });
  class Element {
    constructor() {
      Object.assign(this, listeners());
      this.dataset = {}; this.attributes = {}; this.style = {setProperty() {}};
      this.open = false; this.textContent = ''; this.links = [];
      const classes = new Set();
      this.classList = {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
        toggle: (c, enabled) => enabled ? classes.add(c) : classes.delete(c)};
    }
    set id(value) {this._id = value; nodes.set(value, this);}
    get id() {return this._id;}
    set innerHTML(value) {
      this._html = value;
      for (const [, id] of value.matchAll(/\bid="([^"]+)"/g)) {const node = new Element(); node.id = id;}
      this.links = [...value.matchAll(/data-section="([^"]+)"/g)].map(([, section]) => {
        const link = new Element(); link.dataset.section = section;
        if (section === 'appeals') link.badge = new Element();
        return link;
      });
    }
    get innerHTML() {return this._html || '';}
    setAttribute(name, value) {this.attributes[name] = value;}
    removeAttribute(name) {delete this.attributes[name];}
    querySelectorAll(selector) {return selector === '.dock-item' ? this.links : [];}
    querySelector(selector) {return selector === '.dock-badge' ? this.badge : null;}
    closest(selector) {return selector === '[data-action]' && this.dataset.action ? this : null;}
    append() {}
    focus() {document.activeElement = this;}
  }
  class Input extends Element {}
  const app = new Element(); app.id = 'app';
  const modal = new Element(); modal.id = 'modal';
  const document = {...listeners(), body: new Element(), documentElement: new Element(), activeElement: null,
    getElementById: id => nodes.get(id) || null,
    querySelector: selector => selector.startsWith('#') ? nodes.get(selector.slice(1)) || null : null,
    querySelectorAll: () => [], createElement: () => new Element()};
  const window = {...listeners(), innerHeight: 800, visualViewport: {...listeners(), height: 800, offsetTop: 0}, scrollTo() {}};
  const calls = [];
  let offline = false;
  const summary = id => ({id, external_id: null, title: id, operator_name: 'QA', channel: 'chat', language: 'ru',
    created_at: '2026-11-07T00:00:00Z', evaluation_id: null, assessed: false, final_score: null, open_appeals: 0});
  const overview = {total: 65, assessed: 0, attention: 0, average: null, open_appeals: 25,
    recent: [summary('recent')], appeals: [], trend: [], criteria: []};
  const environment = {document, window, Element, HTMLElement: Element, HTMLInputElement: Input, HTMLTextAreaElement: class extends Element {},
    location: {hash: ''}, matchMedia: () => ({matches: false}), requestAnimationFrame: fn => setImmediate(fn),
    fetch: async url => {
      const path = new URL(url).pathname.split('/api/')[1];
      calls.push(path + new URL(url).search);
      if (offline) throw Error('offline');
      let data;
      if (path === 'workspace/overview') data = overview;
      else if (path === 'workspace/conversations') {
        const page = Number(new URL(url).searchParams.get('page'));
        data = {items: [summary(`page-${page}`)], pagination: {page, pages: 4, per_page: 20, total: 65}, open_appeals: 25};
      } else if (path === 'workspace/conversations/recent') {
        data = {conversation: {...summary('recent'), messages: [], recording_url: null},
          evaluations: [], checklists: [], reviews: [], appeals: [], open_appeals: 25};
      } else throw Error(`Unexpected request ${path}`);
      return new Response(JSON.stringify(data), {headers: {'content-type': 'application/json'}});
    }};
  const previous = Object.fromEntries(Object.keys(environment).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  Object.assign(globalThis, environment);
  const settle = async () => {for (let i = 0; i < 12; i++) await new Promise(setImmediate);};
  const navigate = async hash => {location.hash = hash; await window.dispatch('hashchange'); await settle();};
  const click = async (action, page) => {
    const control = new Element(); control.dataset = {action, page};
    await document.dispatch('click', {target: control, preventDefault() {}}); await settle();
  };
  try {
    await import('../dist/js/app.js');
    await settle();
    assert.deepEqual(calls, ['workspace/overview']);
    const dock = nodes.get('mobile-dock');
    const appeals = dock.links.find(link => link.dataset.section === 'appeals');
    assert.equal(appeals.badge.textContent, '25');
    assert.equal(appeals.badge.hidden, false);
    await navigate('#/dialogues');
    assert.equal(calls.length, 2);
    await click('dialogue-page', '2');
    assert.equal(calls.length, 3);
    assert.match(calls[2], /page=2/);
    const search = new Input(); search.id = 'search';
    for (const value of ['q', 'qu', 'query']) {
      search.value = value;
      await document.dispatch('input', {target: search});
    }
    assert.equal(calls.length, 3);
    await new Promise(resolve => setTimeout(resolve, 350));
    await settle();
    assert.equal(calls.length, 4);
    assert.match(calls[3], /search=query/);
    assert.match(calls[3], /page=1/);
    await navigate('#/dialogues/recent');
    assert.equal(calls.length, 5);
    assert.equal(calls[4], 'workspace/conversations/recent');
    await navigate('#/overview');
    assert.equal(calls.length, 6);
    await click('refresh');
    assert.equal(calls.length, 7);
    assert.equal(nodes.get('mobile-dock'), dock);
    assert.equal(window.handlers.get('resize').length, 1);
    assert.equal(window.visualViewport.handlers.get('resize').length, 1);
    assert.equal(document.handlers.get('focusin').length, 1);
    await window.dispatch('resize');
    await window.visualViewport.dispatch('resize');
    await document.dispatch('focusin');
    await settle();
    assert.equal(calls.length, 7);
    offline = true;
    await navigate('#/dialogues');
    assert.match(app.innerHTML, /Не удалось загрузить данные/);
    assert.equal(calls.length, 8);
    offline = false;
    await click('refresh');
    assert.equal(calls.length, 9);
    assert.match(app.innerHTML, /Найдено диалогов/);
    assert.ok(calls.every(path => !path.includes('/export')));
  } finally {
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  }
});
