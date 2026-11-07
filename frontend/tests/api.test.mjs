import test from 'node:test';
import assert from 'node:assert/strict';
import {createApiClient, ApiError} from '../dist/js/api.js';
import {mapChecklist, checklistPayload, mapConversation, mapEvaluation, mapAppeal, conversationPayload} from '../dist/js/api-mapping.js';
import {answerLabel, score, finalValue, isAssessed} from '../dist/js/scoring.js';
import {sectionContributions} from '../dist/js/review.js';
import {parseImport, importExample} from '../dist/js/import.js';

const json = (body, status=200) => new Response(JSON.stringify(body), {status, headers:{'content-type':'application/json'}});
const criterion = (id, weight) => ({id, title:id, description:'Rule', section:id, weight, answer_type:'binary',
  allow_na:true, na_condition:'No relevant action', scale:[], rule:{type:'semantic'}, critical:false, require_evidence:true});
const checklist = {id:'checklist', name:'QA', version:'official-1', description:'Original', created_at:'2026-11-07T00:00:00Z', criteria:[criterion('known',10), criterion('pending',90)]};
const conversation = {id:'conversation', external_id:'external-1', title:'QA', operator_name:'QA', channel:'chat', language:'kk', recording_url:null,
  created_at:'2026-11-07T00:00:00Z', messages:[{id:'msg-b', speaker:'operator', text:'Hello', start_ms:12000}]};
const result = {criterion_id:'known', value:true, status:'pass', explanation:'Confirmed', evidence:[{message_id:'msg-b'}]};
const pending = {criterion_id:'pending', value:null, status:'needs_review', explanation:'Review required', evidence:[]};

test('client preserves API prefix and follows every page', async () => {
  const urls=[];
  const client=createApiClient('https://example.test/fbroker/api/', async (url, init) => {
    urls.push(url); assert.equal(init.credentials,'omit');
    const page=Number(new URL(url).searchParams.get('page'));
    return json({items:[page],pagination:{pages:2}});
  });
  assert.deepEqual(await client.list('/conversations'),[1,2]);
  assert.match(urls[0], /\/fbroker\/api\/conversations\?per_page=100&page=1$/);
});
test('client sends JSON and propagates server errors without retry', async () => {
  let count=0;
  const client=createApiClient('https://example.test/api', async (url, init) => {
    count++; assert.equal(init.method,'POST'); assert.equal(init.headers['Content-Type'],'application/json');
    assert.deepEqual(JSON.parse(init.body), {expected_revision:3});
    return json({error:{code:'revision_conflict',message:'Reload first'}},409);
  });
  await assert.rejects(client.request('appeals/id/decision',{expected_revision:3}), e => e instanceof ApiError && e.status===409 && e.code==='revision_conflict');
  assert.equal(count,1);
  const html=createApiClient('https://example.test/api',async()=>new Response('<html>SPA</html>',{headers:{'content-type':'text/html'}}));
  await assert.rejects(html.request('ready'), e=>e.code==='invalid_response');
});
test('POST timeout reports uncertain outcome and never retries', async () => {
  let count=0;
  const client=createApiClient('https://example.test/api',async (url,init)=>{
    count++; return new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new Error('abort'))));
  });
  await assert.rejects(client.request('evaluations',{},5), /Результат операции неизвестен/);
  assert.equal(count,1);
});
test('checklists preserve arbitrary versions and assessment rules on round trip', () => {
  const mapped=mapChecklist(checklist);
  assert.equal(mapped.version,'official-1');
  assert.deepEqual(checklistPayload(mapped).criteria,checklist.criteria);
});
test('server current/original results, pending scores and evidence IDs stay distinct', () => {
  const mappedConversation=mapConversation(conversation);
  const raw={id:'evaluation', checklist_id:'checklist', conversation_id:'conversation', revision:4,created_at:'2026-11-07T00:00:00Z',
    results:[result,pending],original_results:[{...result,value:false,status:'fail'},pending],final_score:null,score:100,coverage:10,needs_review:true,original_summary:{final_score:null}};
  const e=mapEvaluation(raw,mapChecklist(checklist),mappedConversation);
  assert.equal(mappedConversation.language,'KZ'); assert.equal(mappedConversation.transcript[0].startMs,12000);
  assert.equal(e.results[0].value,1); assert.equal(e.originalResults[0].value,0);
  assert.deepEqual(e.results[0].evidence,[0]); assert.equal(score(e),null); assert.equal(isAssessed(e),false);
  assert.equal(answerLabel(null,e.checklist.criteria[1],e.results[1].status),'Не оценено');
  assert.equal(finalValue(e,'known',[{evaluationId:e.id,criterionId:'known',status:'resolved',decision:'change',value:0}]),1);
  assert.deepEqual(sectionContributions(e,[]),[{name:'known',earned:10,max:10},{name:'pending',earned:0,max:90}]);
});
test('appeal keeps disputed evidence and its own review outcome', () => {
  const a=mapAppeal({id:'appeal',evaluation_id:'e',criterion_id:'known',disputed_result:{...result,value:false,status:'fail'},comment:'Check',
    status:'resolved',created_at:'date',resolved_at:'later',decision:'change',review_id:'review'},'c',
    {id:'review',comment:'Human reason',changes:[{criterion_id:'known',after:result}]});
  assert.equal(a.originalValue,0); assert.equal(a.value,1); assert.equal(a.reason,'Human reason');
  assert.deepEqual(a.originalEvidenceIds,['msg-b']); assert.equal(a.originalExplanation,'Confirmed');
});
test('import maps external IDs/timing and rejects mixed or decreasing clocks', () => {
  const c=parseImport(importExample)[0]; const payload=conversationPayload(c);
  assert.equal(payload.external_id,c.id); assert.equal(payload.messages[1].start_ms,12000);
  c.transcript[0].timestamp='2026-11-07T00:00:00Z';
  assert.throws(()=>conversationPayload(c), /смешивать/);
  c.transcript[0].timestamp='00:20'; assert.throws(()=>conversationPayload(c),/возрастанию/);
});
