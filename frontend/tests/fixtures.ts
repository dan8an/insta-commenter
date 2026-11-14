import {test as base,expect} from '@playwright/test';
export const test=base.extend<{consoleErrors:string[]}>({
 consoleErrors:[async({page},use,testInfo)=>{
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
  await use(errors);
  await testInfo.attach('console-errors',{body:JSON.stringify(errors,null,2),contentType:'application/json'});
  if(!page.isClosed()){
   const screenshot=await page.screenshot({path:testInfo.outputPath('screen.png'),fullPage:true});
   await testInfo.attach('screenshot',{body:screenshot,contentType:'image/png'});
  }
  expect(errors,'Unexpected JavaScript or console errors').toEqual([]);
 },{auto:true}],
});
export {expect};
