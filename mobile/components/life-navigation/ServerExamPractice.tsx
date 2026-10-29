import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AppState, Image, Pressable, ScrollView, Text, View } from 'react-native';
import { uuid } from 'expo-modules-core';
import { fetchExamPractice, fetchExamAttempts, submitExamAttempt, type ExamPractice, type ExamQuestion, type ExamAttempt, type ExamAttemptWrite, type ExamAttempts, type ExamSubject } from '../../services/examPractice';
import { useLifeControls } from './Controls';
import { readPendingExamAttempt, writePendingExamAttempt, clearPendingExamAttempt } from '../../services/examAttemptPending';
import { BASE_URL } from '../../services/api';

type Mode='next'|'wrong'|'history'|'mistakes'|'all';
const modes:{key:Mode;label:string}[]=[{key:'next',label:'今日练习'},{key:'wrong',label:'待复练'},{key:'history',label:'答题历史'},{key:'mistakes',label:'错题本'},{key:'all',label:'全部题库'}];
type Props={owner:number;day:string;disabled?:boolean;initialSubject?:ExamSubject;initialMode?:Mode};
export default function ServerExamPractice(props:Props){return <Practice key={`${props.owner}:${props.day}`} {...props}/>;}
function Practice({owner,day,disabled=false,initialSubject='英语',initialMode='next'}:Props){
 const [data,setData]=useState<ExamPractice|null>(null),[error,setError]=useState(''),[visible,setVisible]=useState(true),[loading,setLoading]=useState(false),[notice,setNotice]=useState('');
 const [subject,setSubject]=useState<ExamSubject>(initialSubject),[mode,setMode]=useState<Mode>(initialMode),[selected,setSelected]=useState(''),[trail,setTrail]=useState<string[]>([]);
 const [choice,setChoice]=useState<number|null>(null),[retryId,setRetryId]=useState(''),[result,setResult]=useState<ExamAttempt|null>(null),[phase,setPhase]=useState<'idle'|'saving'|'failed'>('idle');
 const [showPlan,setShowPlan]=useState(false);
 const [expandedAttempts,setExpandedAttempts]=useState<string[]>([]);
 const [history,setHistory]=useState<ExamAttempts|null>(null),[historyError,setHistoryError]=useState(''),[historyLoading,setHistoryLoading]=useState(false);
 const ready=useRef(false),alive=useRef(true),foreground=useRef(true),readEpoch=useRef(0),historyEpoch=useRef(0),locked=useRef(false),pending=useRef<ExamAttemptWrite|null>(null),choiceRef=useRef<number|null>(null),started=useRef(Date.now());
 const {c,text,button}=useLifeControls(disabled||phase==='saving');
 const load=useCallback(async(allowDraft=false)=>{
  const epoch=++readEpoch.current;setLoading(true);
  try{const next=await fetchExamPractice(owner,day);if(alive.current&&foreground.current&&epoch===readEpoch.current&&(allowDraft||choiceRef.current===null)){setData(next);const pendingQuestion=next.questions.find(item=>item.id===pending.current?.question_id);if(pendingQuestion)setSubject(pendingQuestion.subject);if(!pending.current)setError('');}}
  catch{if(alive.current&&foreground.current&&epoch===readEpoch.current)setError('练习暂不可用，请重试读取。');}
  finally{if(alive.current&&epoch===readEpoch.current)setLoading(false);}
 },[owner,day]);
 const initialize=useCallback(async()=>{
  setLoading(true);
  try{
   const stored=await readPendingExamAttempt(owner);
   if(!alive.current)return;
   if(stored){pending.current=stored;setSelected(stored.question_id);setChoice(stored.choice_index);choiceRef.current=stored.choice_index;setPhase('failed');setError('有一条尚未确认的作答，请重试保存；不会重复记入。');}
   ready.current=true;await load(true);
  }catch{if(alive.current){ready.current=false;setLoading(false);setError('无法读取待确认作答，请重试读取。');}}
 },[owner,load]);
 useEffect(()=>{
  alive.current=true;void initialize();
  const timer=setInterval(()=>{if(ready.current&&foreground.current&&!locked.current&&!pending.current&&choiceRef.current===null)void load();},30000);
  const app=AppState.addEventListener('change',state=>{const active=state==='active';foreground.current=active;setVisible(active);if(!active){++readEpoch.current;++historyEpoch.current;setLoading(false);setHistoryLoading(false);}else if(ready.current&&!locked.current&&!pending.current&&choiceRef.current===null)void load();});
  return()=>{alive.current=false;++readEpoch.current;++historyEpoch.current;clearInterval(timer);app.remove();};
 },[initialize,load]);
 const progress=new Map(data?.progress.map(p=>[p.question_id,p]));
 const pool=(data?.questions??[]).filter(q=>q.subject===subject);
 const available=mode==='next'?(data?.queue??[]).flatMap(id=>pool.find(q=>q.id===id)??[]):pool.filter(q=>mode==='all'||(mode==='wrong'?!progress.get(q.id)?.latest_correct&&progress.has(q.id):mode==='history'?progress.has(q.id):progress.get(q.id)?.ever_wrong));
 const q=result?.question??(pending.current?data?.questions.find(item=>item.id===pending.current?.question_id):data?.questions.find(item=>item.id===selected&&item.subject===subject)??available[0]);
 const pendingVersionChanged=!!pending.current&&q?.version!==pending.current.question_version;
 const record=q?progress.get(q.id):undefined;
 const readOnly=!!record&&!pending.current&&retryId!==q?.id&&!result;
 const historical=!!data&&data.day!==data.today;
 const navigationBlocked=disabled||phase==='saving'||phase==='failed';
 const previousId=trail.at(-1)??pool.filter(item=>item.id!==q?.id&&progress.has(item.id)).at(-1)?.id;
 const nextIndex=available.findIndex(item=>item.id===q?.id);
 const next=available[nextIndex+1]??available[0];
 const questionImage=q?.image_path?new URL(q.image_path,BASE_URL).toString():null;
 const loadHistory=useCallback(async(id:string,offset=0)=>{
  const epoch=++historyEpoch.current;setHistoryLoading(true);setHistoryError('');
  try{const h=await fetchExamAttempts(owner,id,offset);if(alive.current&&foreground.current&&epoch===historyEpoch.current)setHistory(old=>offset&&old?{items:[...old.items,...h.items],total:h.total}:h);}
  catch{if(alive.current&&foreground.current&&epoch===historyEpoch.current)setHistoryError('答题历史暂不可用，请重试。');}
  finally{if(alive.current&&epoch===historyEpoch.current)setHistoryLoading(false);}
 },[owner]);
 useEffect(()=>{setExpandedAttempts([]);setHistory(null);setHistoryError('');++historyEpoch.current;if(q&&readOnly&&visible)void loadHistory(q.id);return()=>{++historyEpoch.current;};},[q?.id,record?.attempt_count,readOnly,visible,loadHistory]);
 const reset=()=>{setChoice(null);choiceRef.current=null;setRetryId('');setResult(null);setPhase('idle');pending.current=null;setError('');started.current=Date.now();};
 const pick=(item:ExamQuestion)=>{if(navigationBlocked)return;if(q&&q.id!==item.id)setTrail(t=>[...t,q.id]);setSelected(item.id);reset();};
 const switchView=(s:ExamSubject,m:Mode)=>{if(navigationBlocked)return;setSubject(s);setMode(m);setSelected('');setTrail([]);reset();};
 const submit=async()=>{
  if((!q&&!pending.current)||choice===null||historical||disabled||locked.current)return;
  locked.current=true;setSelected(pending.current?.question_id??q!.id);setPhase('saving');setError('');
  try{
   pending.current??={request_id:uuid.v4(),question_id:q!.id,question_version:q!.version,choice_index:choice,elapsed_seconds:Math.min(21600,Math.max(0,Math.floor((Date.now()-started.current)/1000)))};
   await writePendingExamAttempt(owner,pending.current);
   const saved=await submitExamAttempt(owner,pending.current);
   await clearPendingExamAttempt(owner,pending.current.request_id);
   if(!alive.current)return;
   pending.current=null;choiceRef.current=null;setResult(saved);setPhase('idle');
   await load(true);
  }catch{if(alive.current){setPhase('failed');setError('作答尚未确认保存。请重试同一答案，系统会防止重复记录。');}}
  finally{locked.current=false;}
 };
 const discard=()=>{
  const request=pending.current;if(!request||locked.current)return;
  Alert.alert('放弃本机待确认提交？','此前请求可能已经保存到服务器。此操作只清除本机待确认请求，不删除服务器作答；随后请核对答题历史。默认可继续使用原标识重试保存。',[
   {text:'继续重试',style:'cancel'},
   {text:'放弃并核对历史',style:'destructive',onPress:()=>{void (async()=>{
    if(!alive.current||pending.current?.request_id!==request.request_id)return;
    locked.current=true;setPhase('saving');
    try{await clearPendingExamAttempt(owner,request.request_id);if(!alive.current)return;reset();setMode('history');setSelected('');setTrail([]);setNotice('已放弃本机待确认请求，服务器记录未删除。请核对答题历史后再作答。');await load(true);}
    catch{if(alive.current){setPhase('failed');setError('无法清除本机待确认请求，原请求仍保留。');}}
    finally{locked.current=false;}
   })();}},
  ]);
 };
 const card={padding:12,gap:10,borderWidth:1,borderColor:c.separator,borderRadius:12,backgroundColor:c.bgCard} as const;
 const heading=(value:string)=><Text accessibilityRole="header" style={{fontSize:16,lineHeight:23,fontWeight:'600',color:c.labelPrimary}}>{value}</Text>;
 if(!visible)return <Text>返回前台后继续练习。</Text>;
 if(!data)return <View style={{gap:8}}>{text(loading?'正在读取服务端题库…':error||'练习暂不可用，请重试读取。')}{button('重新读取练习',()=>{void initialize();},loading)}</View>;
 return <View style={{gap:12}}>
  {heading('每日专项与错题回看')}{text(`已练 ${data.progress.length} / ${data.questions.length} 题 · 待复练 ${data.progress.filter(p=>!p.latest_correct).length} 题`)}
  {text('题库由服务器更新；提交后保存到当前账号。仅回看不会改写作答。')}
  <View style={{flexDirection:'row',flexWrap:'wrap',gap:6}}>{modes.map(m=>button(m.label,()=>switchView(subject,m.key),navigationBlocked||mode===m.key))}{button(loading?'正在同步…':'同步进度',()=>{void load();if(q&&readOnly)void loadHistory(q.id);},loading||navigationBlocked||choice!==null&&!result)}</View>
  {text(`${data.total_minutes} 分钟 · ${data.plan.map(p=>`${p.subject}${p.minutes}分钟`).join(' · ')}`)}
  {button(showPlan?'收起两小时安排':'查看两小时安排',()=>setShowPlan(!showPlan))}{showPlan&&<View style={card}>{data.plan.map((block,index)=><View key={index} style={{gap:4}}>{heading(`${block.subject} · ${block.minutes} 分钟`)}{text(block.instruction)}</View>)}</View>}
  {!!notice&&text(notice)}
  {!!error&&<Text accessibilityRole="alert" style={{color:c.labelPrimary}}>{error}</Text>}
  {historical&&text('历史日期仅供回看，请切回今天作答。')}
  <View style={{flexDirection:'row',gap:8}}>{(['英语','数学','逻辑'] as const).map(s=>button(s,()=>switchView(s,mode),navigationBlocked||subject===s))}</View>
  <ScrollView horizontal keyboardShouldPersistTaps="handled"><View style={{flexDirection:'row',gap:6}}>{available.map(item=><View key={item.id}>{button(`${item.topic} · ${progress.has(item.id)?'复习':'新题'}`,()=>pick(item),navigationBlocked||q?.id===item.id)}</View>)}</View></ScrollView>
  {pendingVersionChanged?<View style={card}>{text('题目版本已变化。此前答案与请求标识仍保留，请先重试确认原提交。')}{text(`原题 ${pending.current?.question_id} · 版本 ${pending.current?.question_version} · 作答 ${String.fromCharCode(65+(pending.current?.choice_index??0))}`)}{button('重试保存',()=>{void submit();},historical)}</View>:q?<View style={card}>
   {heading(q.topic)}{text(`${q.paper_year?`${q.paper_year} 年 ${q.paper_subject} 第 ${q.question_number} 题 · `:''}${q.subject} · ${q.source} · ${q.difficulty}`)}{questionImage&&<Image source={{uri:questionImage}} accessibilityLabel={`${q.paper_year} 年管综第 ${q.question_number} 题原卷裁图`} resizeMode="contain" style={{width:'100%',height:280,backgroundColor:'#fff',borderRadius:8}}/>}{text(q.prompt)}
   {q.options.map((option,i)=><Pressable key={`${q.id}:${i}`} accessibilityRole="radio" accessibilityLabel={`${String.fromCharCode(65+i)}. ${option}`} accessibilityState={{checked:choice===i,disabled:disabled||historical||readOnly||!!result||phase!=='idle'}} disabled={disabled||historical||readOnly||!!result||phase!=='idle'} onPress={()=>{setSelected(q.id);setChoice(i);choiceRef.current=i;}} style={{minHeight:44,padding:12,borderWidth:1,borderColor:choice===i?c.brand:c.separator,borderRadius:8}}>{text(`${String.fromCharCode(65+i)}. ${option}`)}</Pressable>)}
   {result?<View style={{gap:8}} accessibilityLiveRegion="polite">{heading(result.correct?'本次答对':'本次答错')}{text('作答已保存')}{text(`已记入 ${result.study_date}`)}{result.study_date!==day&&text(`当前查看 ${day}；本次记录以服务器保存日期为准。`)}{text(`正确答案 ${String.fromCharCode(65+result.correct_index)}`)}{text(result.explanation)}{button('重新作答',()=>{reset();setRetryId(q.id);},historical)}</View>:readOnly?<View style={{gap:8}}>
    {heading(record?.latest_correct?'最近一次答对':'待复练')}{text(`已保存 ${record?.attempt_count} 次记录`)}
    {historyLoading&&text('正在读取答题历史…')}{!!historyError&&<>{text(historyError)}{button('重试读取历史',()=>{void loadHistory(q.id);},historyLoading)}</>}
    {history?.items.map(a=><View key={a.id} style={{gap:4}}>{text(`${a.study_date} · ${a.source==='submitted'?'在线作答':a.source==='legacy_first'?'旧版首次记录':'旧版最近复练'}`)}{text(`题目版本 ${a.question_version} · 当次原题：${a.question.prompt}`)}{text(`作答 ${String.fromCharCode(65+a.choice_index)} · 正确答案 ${String.fromCharCode(65+a.correct_index)}`)}{button(expandedAttempts.includes(a.id)?'收起当次选项':'查看当次选项',()=>setExpandedAttempts(ids=>ids.includes(a.id)?ids.filter(id=>id!==a.id):[...ids,a.id]))}{expandedAttempts.includes(a.id)&&a.question.options.map((option,index)=><View key={index}>{text(`${String.fromCharCode(65+index)}. ${option}`)}</View>)}{text(a.explanation)}</View>)}
    {history&&history.items.length<history.total&&button('加载更多历史',()=>{void loadHistory(q.id,history.items.length);},historyLoading)}
    {button('重新作答',()=>{reset();setRetryId(q.id);},historical)}
   </View>:button(phase==='saving'?'正在保存…':phase==='failed'?'重试保存':'提交答案',()=>{void submit();},historical||choice===null)}
   <View style={{flexDirection:'row',gap:8}}>{button('上一题',()=>{if(previousId){setTrail(t=>t.slice(0,-1));setSelected(previousId);reset();}},navigationBlocked||!previousId)}{button('下一题',()=>{if(next)pick(next);},navigationBlocked||!next||next.id===q.id)}</View>
  </View>:text(mode==='next'?'本科目今日没有待做题；可查看错题本、全部题库或继续真题训练。题库有限，不把旧题冒充新题。':mode==='history'?'本科目暂无已保存答题记录。':mode==='mistakes'?'本科目暂无已保存错题。':mode==='wrong'?'本科目暂无待复练题。':'本科目暂无题目。')}
  {phase==='failed'&&pending.current&&button('放弃本机待确认提交',discard)}
  {!!data.legacy_notice&&text(data.legacy_notice)}
 </View>;
}
