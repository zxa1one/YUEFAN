const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('public/app.js','utf8'),cut=(a,b)=>app.slice(app.indexOf(a),app.indexOf(b));
(async()=>{
const h={id:'h',name:'Host',located:true},g={id:'g',name:'Guest',located:false,locationStatus:'pending'};
const state={me:h,host:'h',count:2,members:[h,g],stage:'lobby'};
let calls=[],resolveGPS;
const ctx={state,tr:x=>x,esc:String,budgetSummary:()=>'',roster:()=>'',rid:'test',location:{origin:'https://test.invalid'},locating:false,locationError:'',autoLocationAttempted:false,render:()=>{},notify:()=>{},refresh:async()=>{},getGPS:()=>{calls.push('gps');return new Promise(r=>resolveGPS=r)},api:async(a,b)=>{calls.push([a,b]);return {ok:true}}};vm.createContext(ctx);
vm.runInContext(cut('function locationPanel(){','async function copyLink()')+cut('async function locateGuest(){','function travel('),ctx);
assert.match(vm.runInContext('lobby()',ctx),/id="start-voting"[^>]*disabled/);
g.located=true;assert.doesNotMatch(vm.runInContext('lobby()',ctx),/id="start-voting"[^>]*disabled/);g.located=false;state.me=g;
let pending=vm.runInContext('locateGuest()',ctx);assert.equal(calls[0],'gps');assert.equal(calls[1][1].status,'locating');assert.match(vm.runInContext('lobby()',ctx),/id="retry-loc"[^>]*disabled/);resolveGPS([114.3,35.7]);await pending;assert.equal(calls[2][0],'location');assert.equal(ctx.locating,false);
ctx.getGPS=()=>Promise.reject(Object.assign(Error('denied'),{locationCode:1}));await vm.runInContext('locateGuest()',ctx);assert.equal(calls.at(-1)[1].status,'denied');assert.match(vm.runInContext('lobby()',ctx),/denied/);assert.doesNotMatch(vm.runInContext('lobby()',ctx),/id="retry-loc"[^>]*disabled/);
// Verify the room refresh invokes the auto-location path once and retains manual retry.
assert.match(app,/!s\.me\.located&&s\.stage!==\x27done\x27&&!autoLocationAttempted\)\{autoLocationAttempted=true;void locateGuest\(\)/);console.log('Location gate, async GPS, denial and retry UI checks passed.');
})().catch(e=>{console.error(e);process.exit(1)});
