export type Connection={mode:'demo'|'browser';connected:boolean;username:string|null;csrf_token:string;reason?:string|null};
export type Activity={id:string;post_url:string;message:string;comment_id:string|null;status:string;reason:string|null;created_at:number;demo:boolean};
let csrf='';
export async function api<T>(path:string,body?:unknown):Promise<T>{
 const response=await fetch('/api'+path,{credentials:'include',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},method:body?'POST':'GET',body:body?JSON.stringify(body):undefined});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please check your inputs and try again.');
 if(data.csrf_token)csrf=data.csrf_token;
 return data;
}
export function validUrl(value:string){try{const u=new URL(value);return u.protocol==='https:'&&['instagram.com','www.instagram.com'].includes(u.hostname)&&!u.username&&!u.password&&!u.port&&/^\/(p|reel)\/[A-Za-z0-9_-]{1,100}\/?$/.test(u.pathname)}catch{return false}}
