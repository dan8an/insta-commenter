const {test} = require('node:test');
const assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const req=createRequire(require('node:path').resolve(__dirname,'../../frontend/package.json'));
const {JSDOM}=req('jsdom');
const worker=require('./worker.cjs');
async function inspect(html,message='Hello 🌿',author='tester'){
 const dom=new JSDOM(html,{url:'https://www.instagram.com/p/example/'});
 dom.window.Element.prototype.getClientRects=function(){return [1]};
 global.document=dom.window.document;
 worker.setPageForTest({evaluate:async(fn,args)=>fn(args)});
 try{return await worker.matchingComment(message,author)}finally{delete global.document;dom.window.close()}
}
const row=(author,text='Hello 🌿',extra='')=>`<li><a href="https://www.instagram.com/${author}/">${author}</a><span>${text}</span><time>now</time><button>Reply</button>${extra}</li>`;
test('requires text and author in the same individual comment row',async()=>{
 assert.equal(await inspect(`<ul>${row('other')}${row('tester','Different words')}</ul>`),null);
});
test('caption is not accepted as a published comment',async()=>{
 assert.equal(await inspect('<article><a href="https://www.instagram.com/tester/">tester</a><span>Hello 🌿</span><time>now</time></article>'),null);
});
test('visible comment without an ID has no fabricated ID',async()=>{
 assert.deepEqual(await inspect(row('tester')),{comment_id:null});
});
test('extracts only a comment ID visible in a permalink',async()=>{
 assert.deepEqual(await inspect(row('tester','Hello 🌿','<a href="https://www.instagram.com/p/example/c/987/">View</a>')),{comment_id:'987'});
});
test('matches line breaks and Unicode rendered with normalized whitespace',async()=>{
 assert.deepEqual(await inspect(row('tester','Hello   🌿'),'Hello\n🌿'),{comment_id:null});
});
