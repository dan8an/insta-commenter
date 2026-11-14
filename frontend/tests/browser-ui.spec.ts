import {test,expect} from './fixtures';

test('desktop browser connection, publishing and dark appearance',async({page})=>{
 let connected=false;let opened=0;let writes=0;let activity:any[]=[];
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  let data:any={};
  if(path.endsWith('/auth/status')) data={mode:'browser',connected,username:connected?'local.tester':null,csrf_token:'test',reason:connected?null:'Finish signing in, then check connection.'};
  else if(path.endsWith('/browser/open')){opened++;connected=true;data={connected:false,username:null}}
  else if(path.endsWith('/comments/publish')){
   writes++;const body=route.request().postDataJSON();
   activity=[{id:'test-attempt',post_url:body.url,message:body.message,status:'published',comment_id:null,created_at:Date.now()/1000,demo:false,reason:'Confirmed on the reloaded Instagram page as @local.tester.'}];data=activity[0];
  }else if(path.endsWith('/activity')) data=activity;
  await route.fulfill({json:data});
 });
 await page.setViewportSize({width:1440,height:1000});
 await page.goto('/');
 await expect(page.getByText('Local browser publishing')).toBeVisible();
 await page.getByRole('button',{name:'Open Instagram browser'}).first().click();
 await expect(page.getByRole('status')).toHaveText('Ready as @local.tester');
 expect(opened).toBe(1);
 await page.getByLabel('Instagram post URL').fill('https://www.instagram.com/p/example/');
 await page.getByLabel('Your comment').fill('A thoughtful comment 🌿\nSecond line.');
 await page.getByLabel('Times to post').fill('3');
 await expect(page.getByLabel('Exact post count')).toHaveValue('3');
 await page.getByRole('button',{name:'Publish Comment',exact:true}).click();
 await expect(page.getByText('Published successfully',{exact:true})).toBeVisible();
 await expect(page.getByText('No comment ID exposed by Instagram’s page.')).toBeVisible();
 expect(writes).toBe(3);
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('button',{name:'Use dark appearance'}).click();
 await page.getByRole('button',{name:'Close settings'}).click();
 await expect(page.locator('html')).toHaveClass('dark');
});

test('mobile unknown outcome requires review and never shows success',async({page})=>{
 let activity:any[]=[];
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname;
  let data:any={};
  if(path.endsWith('/auth/status'))data={mode:'browser',connected:true,username:'local.tester',csrf_token:'test'};
  else if(path.endsWith('/comments/publish')){
   const body=route.request().postDataJSON();activity=[{id:'uncertain',post_url:body.url,message:body.message,status:'unknown',comment_id:null,created_at:Date.now()/1000,demo:false,reason:'Check Instagram before trying again.'}];data=activity[0];
  }else if(path.endsWith('/acknowledge')){activity[0].status='reviewed';data=activity[0]}
  else if(path.endsWith('/activity'))data=activity;
  await route.fulfill({json:data});
 });
 await page.setViewportSize({width:390,height:844});await page.goto('/');
 await expect(page.getByRole('status')).toHaveText('Ready as @local.tester');
 await page.getByLabel('Instagram post URL').fill('https://www.instagram.com/reel/example/');
 await page.getByLabel('Your comment').fill('Hello 🌿');
 await page.getByRole('button',{name:'Publish Comment',exact:true}).click();
 await expect(page.getByText('Publishing status unknown',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'I checked Instagram'}).click();
 await expect(page.getByText('reviewed',{exact:true})).toBeVisible();
 await expect(page.getByText('Published successfully',{exact:true})).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
