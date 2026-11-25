// Optional Node.js checks for generated final HTML and reduced-motion behavior.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const app=fs.readFileSync('public/app.js','utf8');
const cut=(start,end)=>app.slice(app.indexOf(start),app.indexOf(end));
const render=cut('function finalResults(){','function animateResults(){');
const animate=cut('function animateResults(){','function voting(){');
const host={id:'host',name:'Alice',submitted:true},guest={id:'guest',name:'小明 <好友>',submitted:true};
const context={state:{members:[host,guest],count:2,host:'host',me:host,restaurants:[{id:'a',name:'A & B',votes:1,voters:[guest]},{id:'z',name:'Z',votes:1,voters:[host]},{id:'none',name:'No votes',votes:0,voters:[]}]},tr:x=>x,esc:s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),openDetails:new Set(),restaurant:()=>'',roster:()=>'',reducedMotion:()=>true,motion:()=>{throw Error('motion must be skipped')},app:{querySelector:()=>{throw Error('motion must be skipped')}}};
vm.createContext(context);vm.runInContext(render+animate,context);const html=vm.runInContext('finalResults()',context);
assert.equal((html.match(/data-result-id=/g)||[]).length,2);assert(html.indexOf('data-result-id="a"')<html.indexOf('data-result-id="z"'));assert(html.includes('小明 &lt;好友&gt;'));assert(html.includes('A &amp; B'));assert(html.includes('Alice'));assert(!html.includes('No votes'));vm.runInContext('animateResults()',context);console.log('Final summary markup and reduced-motion checks passed.');
