import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiClient} from '../dist/js/api.js';
import {loadWorkspace, getState, cancelWorkspaceLoad} from '../dist/js/state.js';

const json = body => new Response(JSON.stringify(body), {headers: {'content-type': 'application/json'}});
const overview = total => ({total, assessed: 0, attention: 0, average: null, open_appeals: 0,
  recent: [], appeals: [], trend: [], criteria: []});

test('simultaneous GETs share one request; failures and completed reads are not cached', async () => {
  let finish, count = 0;
  const client = createApiClient('https://example.test', () => {
    count++;
    return new Promise(resolve => {finish = resolve;});
  });
  const first = client.request('overview');
  const second = client.request('overview');
  assert.equal(count, 1);
  finish(json({total: 65}));
  assert.deepEqual(await Promise.all([first, second]), [{total: 65}, {total: 65}]);
  const third = client.request('overview');
  assert.equal(count, 2);
  finish(json({total: 66}));
  assert.deepEqual(await third, {total: 66});
  let failures = 0;
  const failing = createApiClient('https://example.test', async () => {failures++; throw Error('offline');});
  await assert.rejects(failing.request('overview'));
  await assert.rejects(failing.request('overview'));
  assert.equal(failures, 2);
});

test('late screen responses cannot overwrite the current route or filter', async () => {
  const original = globalThis.fetch;
  let finishOld;
  globalThis.fetch = url => {
    if (url.includes('workspace/overview')) return new Promise(resolve => {finishOld = resolve;});
    return Promise.resolve(json({items: [], pagination: {page: 3, per_page: 20, total: 42, pages: 3}, open_appeals: 2}));
  };
  try {
    const old = loadWorkspace();
    assert.equal(await loadWorkspace('dialogues', '', {page: 3}), true);
    finishOld(json(overview(999)));
    assert.equal(await old, false);
    assert.equal(getState().pagination.total, 42);
    assert.equal(getState().openAppeals, 2);
    assert.notEqual(getState().overview?.total, 999);
    const cancelled = loadWorkspace();
    cancelWorkspaceLoad();
    finishOld(json(overview(888)));
    assert.equal(await cancelled, false);
    assert.notEqual(getState().overview?.total, 888);
  } finally {globalThis.fetch = original;}
});

test('refresh after a write does not reuse a read that started before the write', async () => {
  const finishes = [];
  const client = createApiClient('https://example.test', (url, init) => {
    if (init.method === 'POST') return Promise.resolve(json({saved: true}));
    return new Promise(resolve => finishes.push(resolve));
  });
  const oldRead = client.request('overview');
  await client.request('import', {items: []});
  const newRead = client.request('overview');
  assert.equal(finishes.length, 2);
  finishes[0](json({total: 1}));
  await oldRead;
  const duplicate = client.request('overview');
  assert.equal(finishes.length, 2);
  finishes[1](json({total: 2}));
  assert.deepEqual(await Promise.all([newRead, duplicate]), [{total: 2}, {total: 2}]);
});

test('a failed screen load preserves the previous complete data and allows retry', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => json(overview(65));
    await loadWorkspace();
    globalThis.fetch = async () => {throw Error('offline');};
    await assert.rejects(loadWorkspace());
    assert.equal(getState().overview.total, 65);
    globalThis.fetch = async () => json(overview(66));
    await loadWorkspace();
    assert.equal(getState().overview.total, 66);
  } finally {globalThis.fetch = original;}
});
