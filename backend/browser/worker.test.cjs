const {test,after} = require('node:test');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const requireFrontend = createRequire(require('node:path').resolve(__dirname,'../../frontend/package.json'));
const {chromium} = requireFrontend('playwright');
const worker = require('./worker.cjs');
let browser;
after(async()=>{if(browser)await browser.close()});
test('signed-in username comes from the sidebar avatar, not a feed profile',async()=>{
  const f=await fixture();
  try{
    await f.page.setContent(`<nav><a href="/tester/"><img alt="tester's profile picture" width="24" height="24"></a><a href="/explore/">Explore</a></nav><main style="margin-left:480px"><a href="/someone/"><img alt="someone's profile picture" width="32" height="32"></a></main>`);
    assert.equal(await worker.username(),'tester');
    await f.page.setContent(`<main style="margin-left:480px"><a href="/someone/"><img alt="someone's profile picture" width="32" height="32"></a></main>`);
    await assert.rejects(worker.username(),e=>e.category==='authentication');
  }finally{await f.context.close()}
});
test('only normalized Instagram permalinks are accepted',()=>{
  assert.equal(worker.normalize('https://instagram.com/reel/Ab_c/?x=1'),'https://www.instagram.com/reel/Ab_c/');
  for(const url of ['http://instagram.com/p/a/','https://instagram.com.evil/p/a/','https://user@instagram.com/p/a/','https://instagram.com/stories/a/'])assert.throws(()=>worker.normalize(url));
});
const escape = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
async function fixture({existing=false,hideAfter=false,author='tester',challenge=false,composer='form'}={}) {
  browser ||= await chromium.launch({headless:true,channel:'chrome'});
  const context=await browser.newContext(); const page=await context.newPage();
  let posts=0, reloads=0;
  const message='A thoughtful note 🌿';
  const row=()=>`<li><a href="/${author}/">${author}</a><span>${message}</span><a href="/p/fixture/c/12345/"><time>now</time></a><button>Reply</button></li>`;
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==='/fixture-submit'){posts++;return route.fulfill({json:{ok:true}})}
    if(url.hostname!=='www.instagram.com')return route.abort();
    reloads++;
    if(hideAfter&&posts)return route.abort();
    const posted = JSON.stringify(row());
    const composerHtml = composer === 'delayed'
      ? `<div id="composer"><form><textarea placeholder="Add a comment…"></textarea></form></div><script>const send=async()=>{await fetch('/fixture-submit',{method:'POST'});document.querySelector('ul').innerHTML=${posted}};document.querySelector('textarea').addEventListener('input',()=>{if(document.getElementById('post'))return;const b=document.createElement('div');b.id='post';b.setAttribute('role','button');b.textContent='Post';document.getElementById('composer').appendChild(b);b.addEventListener('click',send)});</script>`
      : `<form><textarea placeholder="Add a comment…"></textarea><button type="submit">Post</button></form><script>document.querySelector('form').onsubmit=async(e)=>{e.preventDefault();await fetch('/fixture-submit',{method:'POST'});document.querySelector('ul').innerHTML=${posted}}</script>`;
    return route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"></head><body><a href="/tester/" aria-label="Profile">Profile</a><ul>${existing||posts?row():''}</ul>${composerHtml}</body></html>`});
  });
  await page.goto('https://www.instagram.com/'+(challenge?'challenge/':'p/fixture/'));
  worker.setPageForTest(page);worker.setOwnerForTest('tester');
  return {page,context,message,posts:()=>posts,reloads:()=>reloads};
}
test('publish clicks a Post control that appears only after the comment is typed',async()=>{
  const f=await fixture({composer:'delayed'});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('publish clicks once and verifies author/text after a fresh navigation',async()=>{
  const f=await fixture();try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1);assert.ok(f.reloads()>=3)}finally{await f.context.close()}
});
test('existing identical comment is submitted again',async()=>{
  const f=await fixture({existing:true});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('reload failure after submission is unknown and never retried',async()=>{
  const f=await fixture({hideAfter:true});try{await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='unknown');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a security challenge stops before clicking',async()=>{
  const f=await fixture({challenge:true});try{await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='authentication');assert.equal(f.posts(),0)}finally{await f.context.close()}
});
test('matching text from another author or a caption is not confirmation',async()=>{
  const f=await fixture({existing:true,author:'someone_else'});try{
    assert.equal(await worker.matchingComment(f.message,'tester'),null);
    await f.page.setContent(`<article><a href="/tester/">tester</a><span>${f.message}</span><time>now</time></article>`);
    assert.equal(await worker.matchingComment(f.message,'tester'),null);
  }finally{await f.context.close()}
});
