import {afterEach,describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {App} from './main';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
function setup(initialConnected=false,outcome='published'){
 let connected=initialConnected;let activities:any[]=[];
 const fetcher=vi.fn(async(input:string,init?:RequestInit)=>{
  let data:any={};
  if(input.endsWith('/auth/status'))data={mode:'browser',connected,username:connected?'tester':null,csrf_token:'test-csrf',reason:connected?null:'Sign in in the browser.'};
  else if(input.endsWith('/browser/open'))data={connected:false,reason:'Sign in'};
  else if(input.endsWith('/comments/publish')){const body=JSON.parse(init?.body as string);activities=[{id:'attempt',post_url:body.url,message:body.message,status:outcome,comment_id:null,created_at:Date.now()/1000,demo:false,reason:outcome==='published'?'Confirmed on the reloaded page.':'Check Instagram before retrying.'}];data=activities[0]}
  else if(input.endsWith('/acknowledge')){activities[0].status='reviewed';data=activities[0]}
  else if(input.endsWith('/activity'))data=activities;
  return {ok:true,json:async()=>data};
 });
 vi.stubGlobal('fetch',fetcher);
 const client=new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}});
 render(<QueryClientProvider client={client}><App/></QueryClientProvider>);
 return {fetcher,signIn:()=>{connected=true}};
}
describe('local browser interface',()=>{
 it('opens browser and checks connection without OAuth',async()=>{
  const {fetcher,signIn}=setup();
  await screen.findByText('Local browser publishing');
  fireEvent.click(screen.getAllByRole('button',{name:'Open Instagram browser'})[0]);
  await waitFor(()=>expect(fetcher.mock.calls.some(([url])=>url.endsWith('/browser/open'))).toBe(true));
  signIn();fireEvent.click(screen.getByRole('button',{name:'Check connection'}));
  await screen.findByText('@tester');
  expect(screen.queryByRole('link',{name:'Connect Instagram'})).not.toBeInTheDocument();
 });
 it('posts once by default and repeats for the selected count',async()=>{
  const {fetcher}=setup(true);
  await screen.findByText('@tester');
  fireEvent.change(screen.getByLabelText(/Instagram post URL/),{target:{value:'https://instagram.com/p/test/'}});
  fireEvent.change(screen.getByLabelText(/Your comment/),{target:{value:'Hello 🌿'}});
  fireEvent.click(screen.getByRole('button',{name:'Publish Comment'}));
  await screen.findByText('Published successfully');
  expect(screen.getByText('No comment ID exposed by Instagram’s page.')).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(([url])=>url.endsWith('/comments/publish'))).toHaveLength(1);
  fireEvent.change(screen.getByLabelText(/Times to post/),{target:{value:'4'}});
  expect(screen.getByLabelText('Exact post count')).toHaveValue(4);
  fireEvent.click(screen.getByRole('button',{name:'Publish Comment'}));
  await waitFor(()=>expect(fetcher.mock.calls.filter(([url])=>url.endsWith('/comments/publish'))).toHaveLength(5));
 });
 it('stops repeating when a send is not published',async()=>{
  const {fetcher}=setup(true,'unknown');await screen.findByText('@tester');
  fireEvent.change(screen.getByLabelText(/Instagram post URL/),{target:{value:'https://instagram.com/p/test/'}});
  fireEvent.change(screen.getByLabelText(/Your comment/),{target:{value:'Hello'}});
  fireEvent.change(screen.getByLabelText('Exact post count'),{target:{value:'25000'}});
  expect(screen.getByLabelText(/Times to post/)).toHaveValue('10000');
  fireEvent.click(screen.getByRole('button',{name:'Publish Comment'}));
  await screen.findByText('Publishing status unknown');
  expect(fetcher.mock.calls.filter(([url])=>url.endsWith('/comments/publish'))).toHaveLength(1);
 });
 it('lets the user acknowledge an unknown outcome without claiming success',async()=>{
  setup(true,'unknown');await screen.findByText('@tester');
  fireEvent.change(screen.getByLabelText(/Instagram post URL/),{target:{value:'https://instagram.com/p/test/'}});
  fireEvent.change(screen.getByLabelText(/Your comment/),{target:{value:'Hello'}});
  fireEvent.click(screen.getByRole('button',{name:'Publish Comment'}));
  await screen.findByText('Publishing status unknown');
  fireEvent.click(await screen.findByRole('button',{name:'I checked Instagram'}));
  await waitFor(()=>expect(screen.queryByText('Publishing status unknown')).not.toBeInTheDocument());
  expect(screen.queryByText('Published successfully')).not.toBeInTheDocument();
 });
});
