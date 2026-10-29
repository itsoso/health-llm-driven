'use client';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import { getExamPractice, getExamAttempts, submitExamAttempt, type ExamAttempt, type ExamAttemptWrite, type ExamPractice, type ExamQuestion } from '@/services/examPractice';
import css from './server-exam-practice.module.css';

type Mode = 'next'|'wrong'|'history'|'mistakes'|'all';
type Scope = 'drill'|'2024'|'2025'|'2026'|'all';
const modes: {key:Mode;label:string}[] = [{key:'next',label:'按进度练习'},{key:'wrong',label:'待复练'},{key:'history',label:'答题历史'},{key:'mistakes',label:'错题本'},{key:'all',label:'全部题库'}];
const scopes: {key:Scope;label:string}[] = [{key:'drill',label:'原创专项'},{key:'2024',label:'2024 真题'},{key:'2025',label:'2025 真题'},{key:'2026',label:'2026 真题'},{key:'all',label:'全部来源'}];
const sources = {submitted:'逐次记录',legacy_first:'旧记录 · 首次',legacy_latest:'旧记录 · 最近复练'};
const letter = (index:number) => String.fromCharCode(65+index);
function failure(error:unknown,operation:string) {
 const status=(error as {response?:{status?:number}})?.response?.status;
 return status===401||status===403?'登录状态或账号权限已变化，请重新登录。':status===409?'提交冲突，未确认保存。请保留本次答案并重试核对。':`${operation}失败，请检查网络后重试。`;
}
type PendingAttempt = {day:string;question:ExamQuestion;body:ExamAttemptWrite};
function readPending(key:string):PendingAttempt|null {
 const raw=sessionStorage.getItem(key);if(!raw)return null;
 const value:unknown=JSON.parse(raw);
 if(!value||typeof value!=='object')throw Error('Invalid pending attempt');
 const entry=value as PendingAttempt,q=entry.question,b=entry.body;
 if(typeof entry.day!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(entry.day)||!q||!b||typeof q.id!=='string'||typeof q.prompt!=='string'||typeof q.topic!=='string'||typeof q.source!=='string'||typeof q.difficulty!=='string'||!['英语','数学','逻辑'].includes(q.subject)||!Array.isArray(q.options)||q.options.length<2||q.options.some(o=>typeof o!=='string')||!Number.isInteger(q.version)||q.version<1||b.question_id!==q.id||b.question_version!==q.version||typeof b.request_id!=='string'||!b.request_id||!Number.isInteger(b.choice_index)||b.choice_index<0||b.choice_index>=q.options.length||!Number.isInteger(b.elapsed_seconds)||b.elapsed_seconds<0||b.elapsed_seconds>21600)throw Error('Invalid pending attempt');
 return entry;
}
export default function ServerExamPractice(props:{owner:number;day:string;initialSubject?:ExamQuestion['subject'];initialPaperYear?:2024|2025|2026}) {
 return <PracticeSession key={`${props.owner}:${props.day}:${props.initialSubject??'英语'}:${props.initialPaperYear??'drill'}`} {...props}/>;
}
function PracticeSession({owner,day,initialSubject='英语',initialPaperYear}:{owner:number;day:string;initialSubject?:ExamQuestion['subject'];initialPaperYear?:2024|2025|2026}) {
 const pendingKey=`lifenav-exam-pending:${owner}`;
 const [pendingDay,setPendingDay]=useState<string|null>(null),[storageError,setStorageError]=useState('');
 const [data,setData]=useState<ExamPractice|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false);
 const [subject,setSubject]=useState(initialSubject),[mode,setMode]=useState<Mode>('next'),[scope,setScope]=useState<Scope>(initialPaperYear?String(initialPaperYear) as Scope:'drill');
 const [selected,setSelected]=useState(''),[choice,setChoice]=useState<number|null>(null),[feedback,setFeedback]=useState<ExamAttempt|null>(null);
 const [questionSnapshot,setQuestionSnapshot]=useState<ExamQuestion|null>(null);
 const [review,setReview]=useState(false),[trail,setTrail]=useState<string[]>([]);
 const [saving,setSaving]=useState(false),[failed,setFailed]=useState(false),[submitError,setSubmitError]=useState('');
 const [history,setHistory]=useState<ExamAttempt[]>([]),[total,setTotal]=useState(0),[historyError,setHistoryError]=useState(''),[historyLoading,setHistoryLoading]=useState(false);
 const alive=useRef(true),readEpoch=useRef(0),historyEpoch=useRef(0),readAbort=useRef<AbortController|null>(null),historyAbort=useRef<AbortController|null>(null);
 const pending=useRef<ExamAttemptWrite|null>(null),lock=useRef(false),started=useRef(Date.now());
 const idle=useRef(true);idle.current=(choice===null||!!feedback)&&!saving&&!failed;
 const refresh=useCallback(async()=>{
  const epoch=++readEpoch.current;readAbort.current?.abort();const ctrl=new AbortController();readAbort.current=ctrl;
  setLoading(true);
  try {const result=await getExamPractice(owner,day,ctrl.signal);if(alive.current&&epoch===readEpoch.current){setData(result);setError('');}}
  catch(e){if(alive.current&&epoch===readEpoch.current&&!ctrl.signal.aborted)setError(failure(e,'读取练习进度'));}
  finally{if(alive.current&&epoch===readEpoch.current)setLoading(false);}
 },[owner,day]);
 useEffect(()=>{
  alive.current=true;
  try {const saved=readPending(pendingKey);if(saved){pending.current=saved.body;setPendingDay(saved.day);setQuestionSnapshot(saved.question);setSubject(saved.question.subject);if(saved.question.paper_year)setScope(String(saved.question.paper_year) as Scope);setSelected(saved.question.id);setChoice(saved.body.choice_index);setFailed(true);setSubmitError('发现未确认的作答，请重试确认保存状态。');}}
  catch {setStorageError('无法读取本账号未确认的作答，请恢复浏览器会话存储后重试；暂不提交新答案。');}
  void refresh();
  const update=()=>{if(document.visibilityState==='visible'&&idle.current)void refresh();};
  const timer=setInterval(update,30_000);document.addEventListener('visibilitychange',update);
  return ()=>{alive.current=false;readEpoch.current++;historyEpoch.current++;readAbort.current?.abort();historyAbort.current?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',update);};
 },[refresh,pendingKey]);
 const progress=new Map(data?.progress.map(p=>[p.question_id,p]));
 const scopePool=data?.questions.filter(q=>scope==='all'||(scope==='drill'?q.paper_year==null:q.paper_year===Number(scope)))??[];
 const pool=scopePool.filter(q=>q.subject===subject);
 const paperQueue=scope!=='drill'&&scope!=='all'?[...pool].sort((a,b)=>(a.question_number??0)-(b.question_number??0)):null;
 const queue=mode==='next'?(paperQueue??(data?.queue??[]).flatMap(id=>pool.filter(q=>q.id===id))):pool.filter(q=>{
  const p=progress.get(q.id);return mode==='all'||(mode==='history'&&!!p?.attempt_count)||(mode==='mistakes'&&p?.ever_wrong)||(mode==='wrong'&&p?.latest_correct===false);
 });
 const question=questionSnapshot??pool.find(q=>q.id===selected)??queue[0];
 const readonly=review&&!feedback;
 const historical=!!data&&data.day!==data.today;
 const locked=saving||failed||!!storageError;
 const questionId=question?.id;
 useEffect(()=>{started.current=Date.now();},[questionId]);
 const loadHistory=useCallback(async(id:string,offset:number)=>{
  const epoch=++historyEpoch.current;historyAbort.current?.abort();const ctrl=new AbortController();historyAbort.current=ctrl;
  setHistoryLoading(true);setHistoryError('');
  try {const result=await getExamAttempts(owner,id,offset,ctrl.signal);if(alive.current&&epoch===historyEpoch.current){setHistory(h=>offset?[...h,...result.items]:result.items);setTotal(result.total);}}
  catch(e){if(alive.current&&epoch===historyEpoch.current&&!ctrl.signal.aborted)setHistoryError(failure(e,'读取答题历史'));}
  finally{if(alive.current&&epoch===historyEpoch.current)setHistoryLoading(false);}
 },[owner]);
 useEffect(()=>{
  setHistory([]);setTotal(0);historyEpoch.current++;historyAbort.current?.abort();
  if(readonly&&questionId)void loadHistory(questionId,0);
 },[readonly,questionId,loadHistory,data]);
 const navigate=(id:string,asReview=false,remember=true)=>{
  if(lock.current||failed)return;
  if(remember&&questionId&&id!==questionId)setTrail(t=>[...t,questionId]);
  setSelected(id);setQuestionSnapshot(null);setChoice(null);setFeedback(null);setReview(asReview);setSubmitError('');pending.current=null;started.current=Date.now();
 };
 const switchMode=(next:Mode)=>{if(locked)return;setMode(next);setSelected('');setQuestionSnapshot(null);setTrail([]);setChoice(null);setFeedback(null);setReview(next==='history'||next==='mistakes');setSubmitError('');pending.current=null;};
 const switchScope=(next:Scope)=>{if(locked)return;setScope(next);setSelected('');setQuestionSnapshot(null);setTrail([]);setChoice(null);setFeedback(null);setReview(mode==='history'||mode==='mistakes');setSubmitError('');pending.current=null;};
 const switchSubject=(next:ExamQuestion['subject'])=>{if(locked)return;setSubject(next);setSelected('');setQuestionSnapshot(null);setTrail([]);setChoice(null);setFeedback(null);setReview(mode==='history'||mode==='mistakes');setSubmitError('');pending.current=null;};
 const previous=()=>{const id=trail.at(-1);if(!id)return;setTrail(t=>t.slice(0,-1));navigate(id,true,false);};
 const next=()=>{const index=queue.findIndex(q=>q.id===questionId);const target=queue[index+1]??queue[0];if(target&&target.id!==questionId)navigate(target.id,mode==='history'||mode==='mistakes');};
 const submit=async()=>{
  if(!question||choice===null||(historical&&!pendingDay)||lock.current||storageError)return;
  lock.current=true;setSaving(true);setSubmitError('');
  try {
   pending.current??={request_id:crypto.randomUUID(),question_id:question.id,question_version:question.version,choice_index:choice,elapsed_seconds:Math.min(21600,Math.max(0,Math.floor((Date.now()-started.current)/1000)))};
   sessionStorage.setItem(pendingKey,JSON.stringify({day:pendingDay??day,question,body:pending.current}));
   const result=await submitExamAttempt(owner,pending.current);
   // Clear only this request, even if the account switched while awaiting the server.
   const stored=readPending(pendingKey);if(stored?.body.request_id===pending.current.request_id)sessionStorage.removeItem(pendingKey);
   if(!alive.current)return;setFeedback(result);setFailed(false);setPendingDay(null);pending.current=null;void refresh();
  }
  catch(e){if(alive.current){setFailed(true);setPendingDay(d=>d??day);setSubmitError(failure(e,'提交答案'));}}
  finally{lock.current=false;if(alive.current)setSaving(false);}
 };
 const discard=()=>{
  if(lock.current||!window.confirm('只放弃本浏览器的待确认提交，不删除服务器记录。此前请求可能已成功，请刷新答题历史核对。确定放弃本机重试信息？'))return;
  try {sessionStorage.removeItem(pendingKey);}catch {setStorageError('无法清理本机待确认提交，请恢复浏览器会话存储后重试。');return;}
  pending.current=null;setPendingDay(null);setStorageError('');setFailed(false);setSubmitError('');setChoice(null);setFeedback(null);setQuestionSnapshot(null);setSelected('');setMode('history');setReview(true);setTrail([]);void refresh();
 };
 const retry=()=>{setReview(false);setFeedback(null);setChoice(null);pending.current=null;started.current=Date.now();};
 return <section className={css.root} aria-label="服务端练习">
  <header className={css.header}><div><h3>{scope==='drill'?'每日练习':scope==='all'?'全部练习':'历年真题'}</h3><p>{data?`当前范围已练 ${pool.filter(q=>progress.has(q.id)).length} / ${pool.length} 题 · ${data.total_minutes} 分钟计划`:'正在读取服务端题库…'}</p></div><button type="button" onClick={()=>{void refresh();}} disabled={loading||saving}>{loading?'读取中…':'刷新进度'}</button></header>
  {error&&<p role="alert" className={css.error}>{error}</p>}{storageError&&<p role="alert" className={css.error}>{storageError}</p>}
  {(failed||storageError)&&<button type="button" disabled={saving} onClick={discard}>放弃待确认提交</button>}
  {data&&<><details className={css.plan}><summary>当日两小时安排</summary>{data.plan.map((b,i)=><p key={i}>{b.subject} · {b.minutes} 分钟：{b.instruction}</p>)}</details><p className={css.meta}>{data.legacy_notice} · 题库版本 {data.catalog_version}</p></>}
  {pendingDay&&<p role="status">{pendingDay} 的作答尚未确认。{data&&pendingDay!==data.today?'跨日重试：若原请求已保存，返回原记录；若尚未保存，本次确认将记录在服务器今天。':'重试只确认原请求，不创建新的请求编号。'}</p>}
  {historical&&<p role="status">历史日期仅供回看，请切回今天后作答。</p>}
  <nav className={css.filters} aria-label="题库来源">{scopes.map(item=><button key={item.key} type="button" aria-pressed={scope===item.key} disabled={locked} onClick={()=>switchScope(item.key)}>{item.label}</button>)}</nav>
  <nav className={css.filters} aria-label="练习筛选">{modes.map(m=><button key={m.key} type="button" aria-pressed={mode===m.key} disabled={locked} onClick={()=>switchMode(m.key)}>{m.label}</button>)}</nav>
  <nav className={css.filters} aria-label="练习科目">{(['英语','数学','逻辑'] as const).map(s=><button key={s} type="button" aria-pressed={subject===s} disabled={locked} onClick={()=>switchSubject(s)}>{s}</button>)}</nav>
  {data&&<div className={css.layout}><nav className={css.list} aria-label="题目列表">{queue.map((q,i)=><button key={q.id} type="button" disabled={locked} aria-current={q.id===questionId?'true':undefined} onClick={()=>navigate(q.id,mode==='history'||mode==='mistakes')}>{i+1}. {q.topic}<small>{progress.has(q.id)?'复习':'未做'}</small></button>)}</nav>
   {question?<article className={css.card}><p className={css.meta}>{question.paper_year?`${question.paper_year} 年 ${question.paper_subject} 第 ${question.question_number} 题 · `:''}{question.subject} / {question.topic} · {question.difficulty} · {question.source}</p>{!readonly&&question.image_path&&<Image unoptimized width={1400} height={900} className={css.questionImage} src={question.image_path} alt={`${question.paper_year} 年管综第 ${question.question_number} 题原卷裁图`}/>}<h4>{readonly?'已保存答题记录':question.prompt}</h4>
    {!readonly&&<fieldset disabled={locked||!!feedback||historical} className={css.options}><legend>选择答案</legend>{question.options.map((text,index)=><label key={index}><input type="radio" name={`exam-${question.id}`} checked={choice===index} onChange={()=>{setSelected(question.id);setQuestionSnapshot(question);setChoice(index);}}/><span>{letter(index)}. {text}</span></label>)}</fieldset>}
    {submitError&&<p role="alert" className={css.error}>{submitError} 本次答案已保留，重试复用同一请求编号。</p>}
    {readonly?<section aria-label="已保存作答记录"><h5>逐次作答记录</h5>{historyLoading&&<p role="status">正在读取历史…</p>}{historyError&&<p role="alert">{historyError}<button type="button" onClick={()=>{void loadHistory(question.id,0);}}>重试读取历史</button></p>}{!historyLoading&&!history.length&&!historyError&&<p>此题没有已保存的作答记录。</p>}{history.map(a=><div key={a.id} className={css.attempt}><strong>{sources[a.source]}</strong><details open={a.question_version!==question.version}><summary>作答时原题 · v{a.question_version}</summary>{a.question.image_path&&<Image unoptimized width={1400} height={900} className={css.questionImage} src={a.question.image_path} alt={`${a.question.paper_year} 年管综第 ${a.question.question_number} 题原卷裁图`}/>}<p>{a.question.prompt}</p><ol type="A">{a.question.options.map((option,index)=><li key={index}>{option}</li>)}</ol></details><p>{a.study_date} · {a.answered_at?new Date(a.answered_at).toLocaleTimeString('zh-CN',{timeZone:'Asia/Taipei',hour:'2-digit',minute:'2-digit'}):'具体时间未记录'} · {a.correct?'答对':'答错'} · 题目 v{a.question_version}</p><p>我的答案 {letter(a.choice_index)} · 正确答案 {letter(a.correct_index)}</p><p>{a.explanation}</p></div>)}{history.length<total&&<button type="button" disabled={historyLoading} onClick={()=>{void loadHistory(question.id,history.length);}}>加载更多记录</button>}<button type="button" disabled={historical} onClick={retry}>重新作答</button></section>:feedback?<section role="status" className={css.attempt}><strong>作答已保存</strong><p>{feedback.study_date} · {feedback.correct?'本次答对':'本次答错'} · 正确答案 {letter(feedback.correct_index)}</p><p>{feedback.explanation}</p><button type="button" disabled={historical} onClick={retry}>重新作答</button></section>:<button className={css.submit} type="button" disabled={choice===null||saving||(historical&&!pendingDay)||!!storageError} onClick={()=>{void submit();}}>{saving?'提交中…':failed?'重试提交':'提交答案'}</button>}
    <nav className={css.filters} aria-label="题目翻页"><button type="button" disabled={locked||!trail.length} onClick={previous}>上一题</button><button type="button" disabled={locked||!queue.some(q=>q.id!==questionId)} onClick={next}>下一题</button></nav>
   </article>:<p className={css.empty}>{mode==='next'?'本科目当前队列为空；没有可安排的新题或复习题。':mode==='history'?'本科目暂无已保存答题记录。':mode==='mistakes'?'本科目暂无已保存错题。':mode==='wrong'?'本科目暂无待复练题。':'本科目暂无可用题目。'}</p>}
  </div>}
 </section>;
}
