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
test('the save request carries this comment; a comment query or unrelated mutation does not',()=>{
  const text='goated';
  const body='variables='+encodeURIComponent(JSON.stringify({comment_text:text}));
  const req=(url,headers,data)=>({method:()=>'POST',url:()=>url,headers:()=>headers,postData:()=>data});
  assert.equal(worker.isCommentSubmit(req('https://www.instagram.com/graphql/query',{'x-fb-friendly-name':'PolarisPostCommentInputRevampedMutation'},body),text),true);
  assert.equal(worker.isCommentSubmit(req('https://www.instagram.com/graphql/query',{'x-fb-friendly-name':'PolarisPostCommentsPaginationQuery'},body),text),false);
  assert.equal(worker.isCommentSubmit(req('https://www.instagram.com/graphql/query',{'x-fb-friendly-name':'PolarisCommentSeenMutation'},''),text),false);
});
test('only normalized Instagram permalinks are accepted',()=>{
  assert.equal(worker.normalize('https://instagram.com/reel/Ab_c/?x=1'),'https://www.instagram.com/reel/Ab_c/');
  for(const url of ['http://instagram.com/p/a/','https://instagram.com.evil/p/a/','https://user@instagram.com/p/a/','https://instagram.com/stories/a/'])assert.throws(()=>worker.normalize(url));
});
const escape = text => text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
async function fixture({existing=false,author='tester',challenge=false,composer='form',decline=false,slow=false,drop=false,decoy=false,checkOnly=false}={}) {
  browser ||= await chromium.launch({headless:true,channel:'chrome'});
  const context=await browser.newContext(); const page=await context.newPage();
  let posts=0, reloads=0;
  const message='A thoughtful note 🌿';
  const row=()=>`<li><a href="/${author}/">${author}</a><span>${message}</span><a href="/p/fixture/c/12345/"><time>now</time></a><button>Reply</button></li>`;
  const created = {data:{xig_comment_create:{comment:{pk:'12345',text:message,user:{username:author}}}}};
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==='/graphql/query')return route.fulfill({status:200,contentType:'application/json',body:'{"status":"ok"}'});
    if(url.pathname==='/fixture-submit'){
      if(slow)await new Promise(r=>setTimeout(r,3000));
      if(drop)return route.fulfill({status:400,contentType:'application/json',body:'{"status":"fail"}'});
      posts++;
      return route.fulfill({json:created});
    }
    if(url.hostname!=='www.instagram.com')return route.abort();
    reloads++;
    const posted = JSON.stringify(row());
    const save = `const res=await fetch('/fixture-submit',{method:'POST',headers:{'x-fb-friendly-name':'PolarisPostCommentInputRevampedMutation','content-type':'application/x-www-form-urlencoded'},body:'comment_text='+encodeURIComponent(${JSON.stringify(message)})});if(!res.ok)return;const box=document.querySelector('textarea');if(box)box.value=''`;
    const check = `await fetch('/graphql/query',{method:'POST',headers:{'x-fb-friendly-name':'PolarisCommentOffensiveCheckMutation','content-type':'application/x-www-form-urlencoded'},body:'comment_text='+encodeURIComponent(${JSON.stringify(message)})});const box=document.querySelector('textarea');if(box)box.value=''`;
    const prelude = decoy ? `await fetch('/graphql/query',{method:'POST',headers:{'x-fb-friendly-name':'PolarisCommentOffensiveCheckMutation','content-type':'application/x-www-form-urlencoded'},body:'comment_text='+encodeURIComponent(${JSON.stringify(message)})});await new Promise(r=>setTimeout(r,800));` : '';
    const action = decline ? '' : checkOnly ? check : prelude + save;
    const composerHtml = composer === 'delayed'
      ? `<div id="composer"><form><textarea placeholder="Add a comment…"></textarea></form></div><script>const send=async()=>{${action}};document.querySelector('textarea').addEventListener('input',()=>{if(document.getElementById('post'))return;const b=document.createElement('div');b.id='post';b.setAttribute('role','button');b.textContent='Post';document.getElementById('composer').appendChild(b);b.addEventListener('click',send)});</script>`
      : `<form><textarea placeholder="Add a comment…"></textarea><button type="submit">Post</button></form><script>document.querySelector('form').onsubmit=async(e)=>{e.preventDefault();${action}}</script>`;
    const showComment = existing || (checkOnly && posts === 0) || (posts && /\/c\/\d+/.test(url.pathname));
    return route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><html><head><meta charset="utf-8"></head><body><a href="/tester/" aria-label="Profile">Profile</a><div hidden>confirm it's you</div><ul>${showComment?row():''}</ul>${composerHtml}</body></html>`});
  });
  await page.goto('https://www.instagram.com/'+(challenge?'challenge/':'p/fixture/'));
  worker.setPageForTest(page);worker.setOwnerForTest('tester');
  return {page,context,message,posts:()=>posts,reloads:()=>reloads};
}
test('publish clicks a Post control that appears only after the comment is typed',async()=>{
  const f=await fixture({composer:'delayed'});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('publish clicks once and verifies author/text without leaving the post',async()=>{
  const f=await fixture();try{const loads=f.reloads();const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1);assert.equal(f.reloads(),loads);assert.equal(new URL(f.page.url()).pathname,'/p/fixture/')}finally{await f.context.close()}
});
test('existing identical comment is submitted again',async()=>{
  const f=await fixture({existing:true});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a second comment on the open post does not load the url again',async()=>{
  const f=await fixture();try{
    const first=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});
    const loads=f.reloads();
    const second=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:'A thoughtful note 🌿'});
    assert.equal(first.comment_id,'12345');assert.equal(second.comment_id,'12345');
    assert.equal(f.posts(),2);assert.equal(f.reloads(),loads);assert.equal(new URL(f.page.url()).pathname,'/p/fixture/');
  }finally{await f.context.close()}
});
test('text left in the box means the comment was not posted',async()=>{
  const f=await fixture({decline:true});try{await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='provider'&&/did not send/.test(e.message));assert.equal(f.posts(),0)}finally{await f.context.close()}
});
test('a slow save is not reloaded away before Instagram accepts it',async()=>{
  const f=await fixture({slow:true});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a follow-up publish opens the post before it looks for the profile',async()=>{
  const f=await fixture();try{await f.page.setContent('<main><p>Opened comment</p></main>');const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a created comment is confirmed from the save when the post list hides it',async()=>{
  const f=await fixture();try{
    const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});
    assert.equal(result.comment_id,'12345');
    assert.equal(await worker.matchingComment(f.message,'tester'),null);
    assert.equal(new URL(f.page.url()).pathname,'/p/fixture/');
  }finally{await f.context.close()}
});
test('a comment check that returns first does not cancel the later save',async()=>{
  const f=await fixture({decoy:true});try{const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a comment check with no new comment is not confirmed from the post list',async()=>{
  const f=await fixture({checkOnly:true});try{
    await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='unknown'&&/did not return the new comment/.test(e.message));
    assert.equal(f.posts(),0);
    assert.equal(new URL(f.page.url()).pathname,'/p/fixture/');
  }finally{await f.context.close()}
});
test('a refused save is not described as an unverified post',async()=>{
  const f=await fixture({drop:true});try{await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='provider'&&/refused/.test(e.message));assert.equal(f.posts(),0)}finally{await f.context.close()}
});
test('publish returns to the post when the window has left Instagram',async()=>{
  const f=await fixture();try{await f.page.goto('about:blank');const result=await worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message});assert.equal(result.comment_id,'12345');assert.equal(f.posts(),1)}finally{await f.context.close()}
});
test('a rate limit stops before a comment is typed when the post must be opened',async()=>{
  const f=await fixture();try{
    await f.page.goto('about:blank');
    await f.page.route('**/*',route=>{const url=new URL(route.request().url());if(url.pathname==='/p/fixture/')return route.fulfill({status:429,contentType:'text/html',body:''});return route.fallback()});
    await assert.rejects(worker.publish({url:'https://www.instagram.com/p/fixture/',message:f.message}),e=>e.category==='rate_limit');
    assert.equal(f.posts(),0);
  }finally{await f.context.close()}
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
