'use client';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';
import type { components } from '@/types/api.generated';
type Summary=components['schemas']['HealthWeekNavigation'];
type Detail=components['schemas']['NavigationActionDetail'];
const status:Record<string,string>={pending:'待记录',completed:'已完成',skipped:'已跳过',deferred:'已延期',withdrawn:'已撤回',unknown:'状态未知'};
const validRef=(ref:string)=>/^[a-zA-Z0-9_-]{8,128}$/.test(ref)||/^[a-f0-9-]{36}\.[a-f0-9]{64}$/.test(ref);
export default function HealthNavigationView(){
 const {user}=useAuth();
 return user?<HealthView key={user.id} owner={user.id}/>:<p>请登录后查看本人健康周导航。</p>;
}
function HealthView({owner}:{owner:number}){
 const [data,setData]=useState<Summary|null>(null),[detail,setDetail]=useState<Detail|null>(null);
 const [message,setMessage]=useState(''),[reload,setReload]=useState(0),[busy,setBusy]=useState(false);
 const [selected,setSelected]=useState<'completed'|'skipped'|'deferred'|null>(null);
 const epoch=useRef(0),lock=useRef(false),attempt=useRef<{event_type:string;expected_revision:string;operation_id:string}|null>(null);
 const headers={'X-Reva-AI-Subject':String(owner)};
 useEffect(()=>{
  const version=++epoch.current;setData(null);setDetail(null);setSelected(null);attempt.current=null;
  api.get<Summary>('/health-navigation/summary',{headers}).then(({data:value})=>{if(version===epoch.current)setData(value)}).catch(()=>{if(version===epoch.current)setMessage('健康导航暂未开放或暂时不可用，请重试。')});
  const timer=setInterval(()=>{
   setData(value=>value&&Date.parse(value.expires_at)<=Date.now()?null:value);
   setDetail(value=>value&&Date.parse(value.expires_at)<=Date.now()?null:value);
  },1000);
  const visibility=()=>{if(document.hidden){epoch.current++;setData(null);setDetail(null);setSelected(null);attempt.current=null;}else setReload(v=>v+1)};
  document.addEventListener('visibilitychange',visibility);
  return ()=>{epoch.current++;clearInterval(timer);document.removeEventListener('visibilitychange',visibility)};
 // owner is fixed by the keyed parent. Private data never enters a query cache.
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[owner,reload]);
 async function open(ref:string){
  if(!validRef(ref))return;
  const version=++epoch.current;setDetail(null);setSelected(null);attempt.current=null;setMessage('');
  try{const {data:value}=await api.get<Detail>('/health-navigation/actions/'+encodeURIComponent(ref),{headers});if(version===epoch.current)setDetail(value)}catch{if(version===epoch.current)setMessage('行动引用已失效或暂不可用。')}
 }
 async function confirm(){
  if(!detail||!selected||!detail.can_confirm||Date.parse(detail.expires_at)<=Date.now()||lock.current)return;
  lock.current=true;setBusy(true);const version=epoch.current;
  const input=attempt.current??{event_type:selected,expected_revision:detail.action_revision,operation_id:crypto.randomUUID()};attempt.current=input;
  try{
   await api.post('/health-navigation/actions/'+encodeURIComponent(detail.action_ref)+'/events',input,{headers});
   if(version!==epoch.current)return;
   attempt.current=null;setSelected(null);setReload(v=>v+1);setMessage('已保存，重新读取权威状态。');
  }catch(error){
   if(version!==epoch.current)return;
   if((error as {response?:{status:number}}).response?.status===409){attempt.current=null;setSelected(null);setDetail(null);setMessage('行动已变化，请重新核对。');setReload(v=>v+1)}
   else setMessage('结果尚未确认，请使用同一操作重试。');
  }finally{lock.current=false;setBusy(false)}
 }
 async function refresh(){if(lock.current)return;lock.current=true;setBusy(true);const version=epoch.current;
  try{await api.post('/health-navigation/refresh',undefined,{headers});if(version===epoch.current)setReload(v=>v+1)}catch{if(version===epoch.current)setMessage('更新失败，未获得新的安全判断。')}finally{lock.current=false;setBusy(false)}
 }
 return <main className="min-h-screen bg-stone-50 px-4 py-8"><div className="mx-auto max-w-5xl space-y-4">
  <h1 className="text-3xl font-bold">健康周导航</h1><p>健康执行由 Health 记录；生活安排独立保存。</p>
  <div className="flex flex-wrap gap-4"><Link href="/agenda?navigation=week">安排我的一周</Link><Link href="/my-progress">长期健康进展</Link><button onClick={()=>setReload(v=>v+1)}>重新读取</button><button disabled={busy} onClick={()=>void refresh()}>更新今日健康行动</button></div>
  {message&&<p role="alert">{message}</p>}
  {!data&&<p>暂无有效摘要，请重新读取。查看摘要不会自动生成计划。</p>}
  {data&&<><p>{String(data.review_window.start_date)} → {String(data.review_window.end_date)} · {data.timezone}</p><p>已记录 {data.review.recorded_days}/{data.review.window_days} 天</p><p>已完成 {data.review.completed_occurrences} · 已跳过 {data.review.skipped_occurrences} · 已延期 {data.review.deferred_occurrences} · 未知 {data.review.unknown_occurrences}</p><p>{data.review.claim_boundary}</p><p>来源截至：{data.source_as_of??'来源时间未知'}</p>{data.availability==='not_generated'&&<p>尚未生成行动；已生成空计划会独立标明。</p>}
   {data.actions.map(a=><article className="rounded-xl border bg-white p-4" key={a.action_ref}><h2>{a.share_title}</h2><p>{a.share_completion_criterion}</p><p>{status[a.execution_status]}</p>{a.requires_health_review&&<p>请核对安全条件</p>}<button onClick={()=>void open(a.action_ref)}>查看并核对行动</button></article>)}</>}
  {detail&&<section className="rounded-xl border bg-white p-5"><h2 className="text-xl font-bold">{detail.title}</h2><p>{detail.completion_criterion}</p><p>{status[detail.execution_status]}</p>
   {detail.can_confirm&&detail.safety_state==='allowed'&&!detail.requires_health_review&&Date.parse(detail.expires_at)>Date.now()&&!selected&&<div className="flex gap-4">{(['completed','skipped','deferred'] as const).map(event=><button key={event} onClick={()=>setSelected(event)}>记录{status[event].replace('已','')}</button>)}</div>}
   {selected&&<><p>核对上方行动与完成标准后确认：{status[selected]}</p><button disabled={busy} onClick={()=>void confirm()}>确认记录</button>{!attempt.current&&<button onClick={()=>setSelected(null)}>取消</button>}</>}
  </section>}
 </div></main>;
}
