const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('public/index.html','utf8'), app=fs.readFileSync('public/app.js','utf8'),css=fs.readFileSync('public/style.css','utf8');
const early=html.match(/<script>(.*?)<\/script>/s)[1];
const prefsCode=app.slice(app.indexOf('let savedPrefs='),app.indexOf('const en='));
function test(saved, dark){
 let store=saved===null?{}:{'yuefan:prefs':JSON.stringify({theme:saved})};
 const meta={content:''},root={dataset:{}},media={matches:dark,addEventListener(_,f){this.change=f}};
 const context={document:{documentElement:root,querySelector:()=>meta,body:{classList:{toggle(){}}}},localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>store[k]=v},matchMedia:()=>media,window:{matchMedia:()=>media}};
 vm.createContext(context);vm.runInContext(early,context);const theme=saved||'system';assert.equal(root.dataset.theme,theme);assert.equal(meta.content,(theme==='dark'||theme==='system'&&dark)?'#141416':'#f5f5f7');
 vm.runInContext(prefsCode,context);assert.equal(root.dataset.theme,theme);assert.equal(JSON.parse(store['yuefan:prefs']).theme,theme);
 media.matches=!dark;media.change();assert.equal(meta.content,(theme==='dark'||theme==='system'&&!dark)?'#141416':'#f5f5f7');
 vm.runInContext("prefs.theme='light';applyPrefs()",context);assert.equal(root.dataset.theme,'light');assert.equal(meta.content,'#f5f5f7');assert.equal(JSON.parse(store['yuefan:prefs']).theme,'light');
}
for(const theme of [null,'system','light','dark'])for(const dark of [false,true])test(theme,dark);
assert(css.includes(':root:not([data-theme]),:root[data-theme=system]{color-scheme:dark'));assert(css.includes(':root[data-theme=light]{color-scheme:light'));assert(css.includes(':root[data-theme=dark]{color-scheme:dark'));assert(html.includes('/style.css?v=1.0.0')&&html.includes('/app.js?v=1.0.0'));
console.log('8 theme combinations, live system changes, stored preferences and early theme initialization passed.');
