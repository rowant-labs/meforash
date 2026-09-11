const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/beta/consent.js', 'utf8');
function setup(accepted = false, failSave = false) {
  const nodes = new Map(); const calls = [];
  function node(id) {
    if (!nodes.has(id)) nodes.set(id, {checked:false,open:false,textContent:'',handlers:{}, replays:0,
      addEventListener(type, fn) {this.handlers[type]=fn;},
      showModal() {this.open=true;}, close() {this.open=false;}, focus() {},
      requestSubmit() {this.replays++; this.handlers.submit(event());}});
    return nodes.get(id);
  }
  vm.runInNewContext(source, {document:{querySelector:node},WeakSet,Promise,Error,
    fetch: async (path, options) => {calls.push({path,options});return {ok: !(failSave && path === '/api/accept-terms'),json:async()=>({access:{terms_accepted:accepted,terms_version:'2026-09-11'}})};}});
  return {node,calls};
}
function event() {return {preventDefault(){},stopImmediatePropagation(){}};}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  let s=setup(); s.node('#chat-form').handlers.submit(event()); await flush();
  assert.equal(s.node('#consent-dialog').open,true);assert.equal(s.node('#chat-form').replays,0);
  await s.node('#consent-form').handlers.submit(event());assert.equal(s.calls.length,1);
  s.node('#consent-check').checked=true;await s.node('#consent-form').handlers.submit(event());await flush();
  assert.equal(s.node('#chat-form').replays,1);assert.equal(s.calls[1].path,'/api/accept-terms');
  assert.deepEqual(JSON.parse(s.calls[1].options.body),{terms_version:'2026-09-11',adult:true});
  s=setup(true);s.node('#chat-form').handlers.submit(event());await flush();assert.equal(s.node('#chat-form').replays,1);assert.equal(s.node('#consent-dialog').open,false);
  s=setup(false,true);s.node('#chat-form').handlers.submit(event());await flush();s.node('#consent-check').checked=true;await s.node('#consent-form').handlers.submit(event());await flush();assert.equal(s.node('#chat-form').replays,0);assert.match(s.node('#consent-error').textContent,/not been sent/);
  s=setup();s.node('#email-form').handlers.submit(event());await flush();assert.equal(s.calls.length,0);s.node('#consent-cancel').handlers.click();await flush();assert.equal(s.node('#email-form').replays,0);
  s=setup();s.node('#email-form').handlers.submit(event());await flush();s.node('#consent-check').checked=true;await s.node('#consent-form').handlers.submit(event());await flush();assert.equal(s.calls.length,0);assert.equal(s.node('#email-form').replays,1);
  process.stdout.write('5 consent gate scenarios passed\n');
})().catch(e=>{console.error(e);process.exitCode=1;});
