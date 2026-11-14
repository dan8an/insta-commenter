// Local browser worker. stdout is reserved for the JSON-line protocol.
const { createRequire } = require('node:module');
const path = require('node:path');
const fs = require('node:fs');
const readline = require('node:readline');
const requireFrontend = createRequire(path.resolve(__dirname, '../../frontend/package.json'));
const { chromium } = requireFrontend('playwright');
const profile = path.resolve(__dirname, '../.local/browser-profile');
let context, page, owner;
class BrowserFailure extends Error {
  constructor(category, message) { super(message); this.category = category; }
}
const fail = (category, message) => { throw new BrowserFailure(category, message); };
const SAVE_QUIET_MS = 1500;
function normText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}
function bodyHasMessage(request, message) {
  const needle = normText(message);
  if (!needle) return false;
  let data = '';
  try { data = request.postData() || ''; } catch { data = ''; }
  let decoded = data;
  try { decoded = decodeURIComponent(data.replace(/\+/g, ' ')); } catch { decoded = data; }
  const unescaped = decoded.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
  return `${data}\n${decoded}\n${unescaped}`.replace(/\s+/g, ' ').includes(needle);
}
function isCommentSubmit(request, message) {
  if (request.method() !== 'POST') return false;
  const url = request.url();
  if (url.includes('/fixture-submit') || /\/comments\/\d+\/add\b/.test(url)) return true;
  const friendly = request.headers()['x-fb-friendly-name'] || '';
  if (/Query/i.test(friendly)) return false;
  // A mutation whose name merely contains "comment" is often a check or a
  // comment-list update. Reloading on that response cancels the later save.
  if (!bodyHasMessage(request, message)) return false;
  if (/instagram\.com/.test(url) && /Mutation/.test(friendly)) return true;
  return /comment_text/i.test(request.postData() || '');
}
function watchCommentSubmit(page, message) {
  const state = {started:false, pending:0, result:null, touchedAt:0};
  const matches = request => isCommentSubmit(request, message);
  const onRequest = request => {
    if (!matches(request)) return;
    state.started = true;
    state.pending += 1;
    state.touchedAt = Date.now();
  };
  const onFailed = request => {
    if (!matches(request)) return;
    state.pending = Math.max(0, state.pending - 1);
    state.touchedAt = Date.now();
  };
  const onResponse = async response => {
    const request = response.request();
    if (!matches(request)) return;
    state.started = true;
    let payload = {};
    try { payload = await response.json(); } catch { payload = {}; }
    state.pending = Math.max(0, state.pending - 1);
    state.result = {status:response.status(), payload};
    state.touchedAt = Date.now();
  };
  page.on('request', onRequest);
  page.on('requestfailed', onFailed);
  page.on('response', onResponse);
  return {state, stop() { page.off('request', onRequest); page.off('requestfailed', onFailed); page.off('response', onResponse); }};
}
function saveSettled(state, now) {
  return state.started && state.pending === 0 && now - state.touchedAt >= SAVE_QUIET_MS;
}
function createdCommentId(payload, message, author) {
  const comment = payload && payload.data && payload.data.xig_comment_create && payload.data.xig_comment_create.comment;
  if (!comment) return null;
  const id = String(comment.pk || comment.id || '');
  const user = comment.user && comment.user.username;
  if (!/^\d{1,64}$/.test(id)) return null;
  if (normText(comment.text) !== normText(message)) return null;
  if (normText(user).toLowerCase() !== normText(author).toLowerCase()) return null;
  return id;
}
function samePost(current, target) {
  try {
    const u = new URL(current);
    if (u.protocol !== 'https:' || !['instagram.com','www.instagram.com'].includes(u.hostname)) return false;
    const path = u.pathname.replace(/\/c\/\d+\/?$/, '/');
    return 'https://www.instagram.com' + path.replace(/\/?$/, '/') === target;
  } catch { return false; }
}
function normalize(value) {
  const u = new URL(value);
  if (u.protocol !== 'https:' || !['instagram.com', 'www.instagram.com'].includes(u.hostname) || u.username || u.password || u.port || !/^\/(p|reel)\/[\w-]{1,100}\/?$/.test(u.pathname)) fail('validation', 'Invalid Instagram post URL.');
  return 'https://www.instagram.com' + u.pathname.replace(/\/?$/, '/');
}
async function launch() {
  if (context && page && !page.isClosed()) return;
  if (context) await context.close().catch(() => {});
  fs.mkdirSync(profile, {recursive:true, mode:0o700}); fs.chmodSync(profile, 0o700);
  try {
    context = await chromium.launchPersistentContext(profile, {
      headless:false, locale:'en-US', viewport:{width:1440,height:1000},
      ...(process.env.BROWSER_CHANNEL === 'chromium' ? {} : {channel:'chrome'}),
    });
    page = context.pages()[0] || await context.newPage();
    page.setDefaultTimeout(10000);
    context.on('close', () => { context = undefined; page = undefined; owner = undefined; });
  } catch { fail('browser_setup', 'Could not open the browser. Install Google Chrome, or run npm run browser:install in frontend and set BROWSER_CHANNEL=chromium. Close any other InstaComment process using this browser profile.'); }
}
async function challenge() {
  if (!page || page.isClosed()) fail('authentication', 'Open the Instagram browser and sign in first.');
  const u = new URL(page.url());
  if (!['instagram.com','www.instagram.com'].includes(u.hostname)) fail('authentication', 'Return to Instagram in the dedicated browser.');
  if (/challenge|checkpoint|two_factor|accounts\/login|accounts\/onetap|consent/.test(u.pathname)) fail('authentication', 'Finish signing in or dismiss the Instagram prompt, then check the connection.');
  if (await page.locator('input[name="password"]:visible').count()) fail('authentication','Sign in directly in the Instagram browser.');
  const prompt = page.getByText(/save your login info|turn on notifications/i).first();
  if (await prompt.isVisible().catch(() => false)) fail('authentication', 'Dismiss the Instagram prompt (Not now is fine), then check the connection again.');
  const restriction = page.getByText(/try again later|we restrict certain activity|automated behavior|confirm it.s you/i);
  for (let i = 0, n = await restriction.count(); i < Math.min(n, 8); i++) {
    if (await restriction.nth(i).isVisible().catch(() => false)) fail('challenge','Instagram requires attention. Resolve the message manually in the browser; no comment was retried.');
  }
}
function useInstagramPage() {
  if (!context) return;
  const open = context.pages().filter(p => !p.isClosed() && /https:\/\/(www\.)?instagram\.com/.test(p.url()));
  if (open.length) page = open[open.length - 1];
}
// The compact sidebar has no "Profile" label. The signed-in account is the nav
// avatar, or a link whose own label ends with Profile. Feed avatars are ignored.
async function username() {
  useInstagramPage();
  await challenge();
  const handle = await page.evaluate(reserved => {
    const visible = el => !!(el.getClientRects().length);
    const handleFrom = href => {
      try {
        const u = new URL(href, location.href);
        if (!['instagram.com','www.instagram.com'].includes(u.hostname)) return null;
        const match = u.pathname.match(/^\/([A-Za-z0-9_.]{1,30})\/?$/);
        if (!match || reserved.includes(match[1].toLowerCase())) return null;
        return match[1];
      } catch { return null; }
    };
    const profileWord = value => /(?:^|\s)profile$/i.test(String(value || '').replace(/\s+/g, ' ').trim());
    const altNames = (name, alt) => new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}['’]s profile picture$`, 'i').test(String(alt || '').trim());
    const candidates = [];
    for (const a of document.querySelectorAll('a[href]')) {
      if (!visible(a)) continue;
      const name = handleFrom(a.getAttribute('href'));
      if (!name) continue;
      const alt = a.querySelector('img')?.getAttribute('alt') || '';
      const labels = [a.getAttribute('aria-label') || '', a.innerText || '', ...[...a.querySelectorAll('[aria-label]')].map(n => n.getAttribute('aria-label') || '')];
      const inNav = !!a.closest('nav, [role="navigation"], header');
      const inSidebar = a.getBoundingClientRect().left < 220;
      const namedByAlt = altNames(name, alt);
      const namedByLabel = labels.some(profileWord);
      let rank = 0;
      if ((inNav || inSidebar) && namedByAlt) rank = 6;
      else if (namedByLabel) rank = 5;
      else if (inNav) rank = 2;
      if (rank) candidates.push({name, rank});
    }
    candidates.sort((a, b) => b.rank - a.rank);
    if (!candidates.length) return null;
    const top = candidates.filter(c => c.rank === candidates[0].rank).map(c => c.name.toLowerCase());
    return new Set(top).size === 1 ? candidates[0].name : null;
  }, ['accounts','explore','direct','reels','stories','p','reel','about','legal','emails','privacy','directory','developer','nametag','ar','tv','locations','lite','settings','challenge','consent','fxcal','qr','ads']);
  if (handle) return handle;
  fail('authentication', 'Could not identify your profile. Dismiss any Instagram prompts, stay on Instagram, then check again.');
}
async function connect() {
  await launch();
  await page.bringToFront();
  await page.goto('https://www.instagram.com/', {waitUntil:'domcontentloaded', timeout:30000});
  return {connected:false, username:null, reason:'Sign in directly in the opened Instagram window, then click Check connection.'};
}
async function status() {
  useInstagramPage();
  if (!page || page.isClosed()) return {connected:false, username:null, reason:'Open the Instagram browser to connect.'};
  try { const name = await username(); owner = name; return {connected:true,username:name,reason:null}; }
  catch (e) { owner = undefined; return {connected:false,username:null,reason:e instanceof BrowserFailure ? e.message : 'Check the Instagram browser and try again.'}; }
}
// Inspect rendered comment rows only. No private endpoints, network interception,
// session-cookie extraction, page internals or generated provider IDs.
async function matchingComment(message, author) {
  return page.evaluate(({message,author}) => {
    const norm = s => s.replace(/\s+/g,' ').trim();
    const visible = el => !!(el.getClientRects().length);
    const elements = [...document.querySelectorAll('span,p')].filter(el => visible(el) && norm(el.textContent || '') === norm(message));
    for (const el of elements) {
      let row = el.parentElement;
      for (let level=0; row && level<12; level++,row=row.parentElement) {
        if (['BODY','MAIN','ARTICLE','UL'].includes(row.tagName)) break;
        const authorLink = [...row.querySelectorAll('a[href]')].find(a => {
          try {return new URL(a.href).pathname.replace(/^\/|\/$/g,'').toLowerCase()===author.toLowerCase() && norm(a.textContent||'').toLowerCase()===author.toLowerCase();} catch {return false;}
        });
        // Reply action distinguishes comment rows from captions; one timestamp
        // prevents a shared container from matching someone else's text.
        const times = row.querySelectorAll('time');
        const reply = [...row.querySelectorAll('button,[role="button"],span')].some(n => norm(n.textContent||'')==='Reply');
        if (!authorLink || times.length!==1 || !reply) continue;
        const permalink = [...row.querySelectorAll('a[href]')].find(a => /\/c\/\d+|[?&]comment_id=\d+/.test(a.href));
        const id = permalink?.href.match(/\/c\/(\d+)|[?&]comment_id=(\d+)/);
        return {comment_id:id ? (id[1]||id[2]) : null};
      }
    }
    return null;
  }, {message,author});
}
async function markPostControl() {
  return page.evaluate(() => {
    document.querySelectorAll('[data-instacomment-post]').forEach(el => el.removeAttribute('data-instacomment-post'));
    const visible = el => !!(el.getClientRects().length);
    const norm = s => String(s || '').replace(/\s+/g, ' ').trim();
    const editors = [...document.querySelectorAll('textarea')].filter(el => visible(el) && /comment/i.test(`${el.getAttribute('placeholder') || ''} ${el.getAttribute('aria-label') || ''}`));
    if (editors.length !== 1) return false;
    const editor = editors[0];
    const isPost = el => {
      if (!visible(el) || el.contains(editor)) return false;
      const named = norm(el.getAttribute('aria-label')) === 'Post' || norm(el.innerText) === 'Post';
      if (!named) return false;
      if (el.matches('button, [role="button"]')) return true;
      const rect = el.getBoundingClientRect();
      return rect.width <= 240 && rect.height <= 80;
    };
    let node = editor.parentElement;
    for (let level = 0; node && node !== document.body && level < 15; level++, node = node.parentElement) {
      const controls = [...node.querySelectorAll('button, [role="button"], div, span')].filter(isPost);
      const buttons = controls.filter(el => el.matches('button, [role="button"]'));
      if (buttons.length > 1) return false;
      const leaves = controls.filter(el => !controls.some(other => other !== el && el.contains(other)));
      const choice = buttons.length === 1 ? buttons[0] : (buttons.length === 0 && leaves.length === 1 ? leaves[0] : null);
      if (choice) { choice.setAttribute('data-instacomment-post', '1'); return true; }
    }
    return false;
  });
}
async function publish({url,message}) {
  useInstagramPage();
  let submitted = false;
  try {
    if (!owner) fail('authentication','Click Check connection before publishing.');
    const author = owner;
    await challenge();
    const target = normalize(url);
    // The previous comment's page has no profile nav, so identify the account after the post opens.
    await page.goto(target, {waitUntil:'domcontentloaded',timeout:30000});
    await challenge();
    if (normalize(page.url()) !== target) fail('unsupported','Instagram did not open the requested post. Open it manually to check access.');
    if (await username() !== author) fail('authentication','Could not confirm the connected account on this post.');
    const editor = page.locator('textarea[placeholder*="comment" i]:visible, textarea[aria-label*="comment" i]:visible');
    await editor.first().waitFor({state:'visible',timeout:12000}).catch(() => fail('unsupported','No comment field is available. Check post access, comments settings, or dismiss dialogs in the browser.'));
    if (await editor.count() !== 1) fail('unsupported','More than one comment field is visible. Open the post manually and try again.');
    await editor.click();
    await editor.fill(message);
    await challenge();
    if (normalize(page.url()) !== target || await username() !== author) fail('authentication','Post or account changed before submission. Nothing was posted.');
    // Instagram renders Post only after the field has text, often outside the form.
    const postButton = page.locator('[data-instacomment-post="1"]');
    let found = false;
    for (let attempt = 0; attempt < 15 && !found; attempt++) {
      found = await markPostControl();
      if (!found) await page.waitForTimeout(200);
    }
    if (!found) fail('unsupported','Instagram’s comment controls were not recognized. Nothing was posted.');
    // The first comment-named response is not the save. Reloading on it aborts the
    // request that actually carries this comment, so the comment never leaves the browser.
    const watch = watchCommentSubmit(page, message);
    submitted = true;
    let entered = false;
    try {
      await postButton.click({timeout:10000}).catch(() => {});
      const waitFrom = Date.now();
      while (Date.now() - waitFrom < 20000) {
        const now = Date.now();
        if (!watch.state.started && !entered && now - waitFrom > 400) {
          entered = true;
          await editor.press('Enter').catch(() => {});
        }
        if (!watch.state.started && now - waitFrom > 2500) break;
        if (saveSettled(watch.state, now)) {
          const refused = watch.state.result && (watch.state.result.status >= 400 || watch.state.result.payload.status === 'fail');
          const remaining = await editor.inputValue().catch(() => '');
          // The composer still holding the text means that response was not the save.
          if (!entered && !refused && normText(remaining) === normText(message)) {
            entered = true;
            watch.state.touchedAt = Date.now();
            await editor.press('Enter').catch(() => {});
            continue;
          }
          break;
        }
        await page.waitForTimeout(100);
      }
    } finally { watch.stop(); }
    if (!watch.state.result) fail('provider', 'Instagram did not send the comment. Nothing was published.');
    if (watch.state.result.status >= 400 || watch.state.result.payload.status === 'fail') fail('provider', 'Instagram refused this comment, so nothing was published.');
    // The post page only renders a subset of comments. A new comment is visible on its own link.
    const createdId = createdCommentId(watch.state.result.payload, message, author);
    try {
      if (createdId) await page.goto(target + 'c/' + createdId + '/', {waitUntil:'domcontentloaded', timeout:30000});
      else await page.reload({waitUntil:'domcontentloaded', timeout:30000});
    }
    catch { fail('unknown','Post was clicked, but the page could not be reloaded to confirm the comment. Check Instagram before trying again.'); }
    for (let i=0;i<8;i++) {
      await challenge();
      if (!samePost(page.url(), target)) break;
      const found = await matchingComment(message,author);
      if (found) return {...found,reason:`Confirmed on the reloaded Instagram page as @${author}. This is browser verification, not an API receipt.`};
      await page.waitForTimeout(1000);
    }
    fail('unknown','Post was clicked, but the comment could not be verified after reloading. Check Instagram before trying again.');
  } catch(e) {
    if (e instanceof BrowserFailure) throw e;
    if (submitted) fail('unknown','Submission may have reached Instagram, but confirmation was unavailable. Inspect the post before trying again. No automatic retry was made.');
    fail('browser','The browser could not prepare the comment. Check its window, connection and login, then try again.');
  }
}
async function dispatch(command) {
  switch(command.action) {
    case 'connect': return connect();
    case 'status': return status();
    case 'publish': return publish(command);
    case 'disconnect':
      if(context) await context.close();
      owner=undefined;
      fs.rmSync(profile,{recursive:true,force:true});
      return {disconnected:true};
    default: fail('validation','Unknown browser command.');
  }
}
async function run() {
  for await (const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})) {
    try {const result=await dispatch(JSON.parse(line)); process.stdout.write(JSON.stringify({ok:true,result})+'\n');}
    catch(e) {process.stdout.write(JSON.stringify({ok:false,category:e.category||'browser',message:e instanceof BrowserFailure ? e.message : 'Browser operation failed. Check the Instagram window.'})+'\n');}
  }
  if(context) await context.close().catch(()=>{});
}
if (require.main===module) run();
module.exports={normalize,matchingComment,username,isCommentSubmit,createdCommentId,setPageForTest:p=>{page=p;},publish,setOwnerForTest:name=>{owner=name;}};
