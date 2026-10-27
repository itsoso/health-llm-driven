import React, { useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';
import type { LifeData, LifeTask } from '../../services/lifeNavigation';
import { localDate } from '../../utils/lifeNavigationModel';
import { addStudyDay, dailyStudy, daysUntil, examDate, phaseFor, questions, questionHistory, recordAnswer, studyTask, wrongQuestions, practiceQuestions, practiceModes, comprehensiveSubject, type Subject, type PracticeMode } from '../../utils/examStudy';
import { paperAssignment, examPapers } from '../../utils/examPapers';
import { useLifeControls } from './Controls';

type Props = {data:LifeData; day:string; disabled:boolean; edit:(change:(data:LifeData)=>void)=>void; saveAnswer:(change:(data:LifeData)=>void)=>Promise<void>; focus:(task:LifeTask)=>void};
export default function ExamStudyPanel({data,day,disabled,edit,saveAnswer,focus}:Props) {
 const [persistence,setPersistence]=useState<'idle'|'saving'|'saved'|'failed'>('idle');
 const submitting=useRef(false);
 const {c,text,button,field}=useLifeControls(disabled||persistence==='saving');
 const [section,setSection]=useState('每日计划'),[subject,setSubject]=useState<Subject>('英语'),[mode,setMode]=useState<PracticeMode>('next');
 const [selected,setSelected]=useState(''),[choice,setChoice]=useState<number|null>(null);
 const [feedback,setFeedback]=useState<{id:string;correct:boolean}|null>(null),[error,setError]=useState(''),[writingHint,setWritingHint]=useState(false);
 const assignment=paperAssignment(day);
 const plan=dailyStudy(day),wrong=wrongQuestions(data,day),remaining=daysUntil(localDate());
 const available=practiceQuestions(data,day,subject,mode);
 const pinned=feedback?questions.find(item=>item.id===feedback.id&&item.subject===subject):undefined;
 const q=pinned??available.find(item=>item.id===selected)??available[0];
 const answer=feedback?.id===q?.id?feedback:null;
 const reset=()=>{setChoice(null);setFeedback(null);};
 const startPractice=(s:Subject,nextMode:PracticeMode='next')=>{setSubject(s);setMode(nextMode);setSelected('');reset();setSection('练习与错题');};
 const nextQuestion=()=>{const index=available.findIndex(item=>item.id===q?.id);setSelected((available[index+1]??available[0])?.id??'');reset();};
 const mutate=(change:(d:LifeData)=>void)=>{if(disabled)return;try{edit(change);setError('');}catch(e){setError(e instanceof Error?e.message:'修改失败，请重试。');}};
 const open=async(url:string)=>{try{await Linking.openURL(url);}catch{setError('无法打开资料，请检查网络后重试。');}};
 const heading=(title:string)=><Text accessibilityRole="header" style={{fontSize:20,lineHeight:28,fontWeight:'600',color:c.labelPrimary}}>{title}</Text>;
 const card={padding:16,gap:12,backgroundColor:c.bgCard,borderRadius:14,borderWidth:1,borderColor:c.separator} as const;
 const submit=async()=>{
  if(choice===null||!q||disabled||submitting.current)return;
  submitting.current=true;setPersistence('saving');setError('');
  setSelected(q.id);setFeedback({id:q.id,correct:choice===q.answer});
  try {await saveAnswer(d=>recordAnswer(d,day,q,choice));setPersistence('saved');}
  catch(e){setPersistence('failed');setError(e instanceof Error?e.message:'作答尚未保存，请重试');}
  finally{submitting.current=false;}
 };
 return <View style={{gap:16}}>
  <View style={card}>{heading('EMBA · 每天两小时')}{text('英语四级基础起步 · 199 管综 + 204 英语（二）')}{text(remaining>0?`${remaining} 天后初试`:remaining===0?'今天初试':'初试已结束')}{text(`${examDate} · 以准考证为准`)}</View>
  <View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{['每日计划','练习与错题','真题与路线'].map(s=>button(s,()=>setSection(s),section===s))}</View>
  {text('提交答案会保存到当前账号，同时保存其他工作区草稿。计划和笔记仍需点顶部「保存」。')}
  {!!error&&<Text accessibilityRole="alert" style={{color:c.labelPrimary}}>{error}</Text>}
  {assignment&&section!=='真题与路线'&&<View style={card}>{heading(`${day} · ${assignment.year}年真题 · ${assignment.review?'复测与补弱':'首轮分段'}`)}{text(`英语：${assignment.english}；管综：${assignment.comprehensive}`)}{text(assignment.writing)}{assignment.papers.map(p=>button(`打开${p.year}年${p.subject==='204'?'英语（二）':'管综'}原卷`,()=>{void open(p.url);} ))}{text('原卷训练：纸上作答，在每日计划记录题号、正确数、用时与错因；尚无真题在线自动判分。文件可能含参考答案，请先遮住答案。')}{text(assignment.papers.map(p=>p.source).join(' / '))}</View>}
  {section==='每日计划'&&<>
   {heading(phaseFor(day))}{text(`${day} · 已完成 ${plan.filter(t=>studyTask(data,day,t.key)?.status==='done').reduce((n,t)=>n+t.minutes,0)} / ${plan.reduce((n,t)=>n+t.minutes,0)} 分钟计划`)}
   {plan.length?button('加入当日计划',()=>mutate(d=>addStudyDay(d,day))):text('初试日及之后不再生成冲刺计划，请关注准考证、成绩和复试通知。')}
   {plan.map(t=>{const saved=studyTask(data,day,t.key);return <View key={t.key} style={card}>{heading(`${t.title} · ${t.minutes} 分钟`)}{text(t.detail)}{assignment?button('查看真题与记录方法',()=>setSection('真题与路线')):t.key==='english'?button('练习英语',()=>startPractice('英语')):t.key==='review'?button('复练错题',()=>startPractice(wrong[0]?.subject??'英语','wrong')):comprehensiveSubject(day)!=='写作'?button(`练习${comprehensiveSubject(day)}`,()=>startPractice(comprehensiveSubject(day) as Subject)):button('选择写作真题',()=>setSection('真题与路线'))}{saved?<>
    <Pressable accessibilityRole="checkbox" accessibilityLabel={`完成${t.title}`} accessibilityState={{checked:saved.status==='done',disabled}} disabled={disabled} onPress={()=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.status=task.status==='done'?'planned':'done';})} style={{minHeight:44,justifyContent:'center'}}>{text(`${saved.status==='done'?'☑':'□'} 我已完成这项训练`)}</Pressable>
    {field(`学习结果 · ${t.title}`,saved.result,v=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.result=v;}))}
    {button(`专注${t.title}并保存`,()=>focus(saved))}
   </>:text('加入计划后即可记录学习结果。')}</View>})}
   {text('先用旧年真题分段摸底，记录正确数和耗时；分段结果不折算整卷成绩。')}
  </>}
  {section==='练习与错题'&&<>
   {heading('每日专项与错题复练')}{text(`已练 ${questions.filter(item=>questionHistory(data,item,day).length).length} / ${questions.length} 题 · 待复练 ${wrong.length} 题`)}
   {text('原创专项题库，与上方历年真题训练配合使用。首次答案与最近复练分别保留。')}
   <View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{practiceModes.map(m=>button(m.label,()=>startPractice(subject,m.key),mode===m.key))}</View>
   {text(`${day} · ${mode==='all'?'全部题库包含已做旧题；继续新题请切换「按进度练习」。':mode==='wrong'?'这里只显示待复练错题。':'优先未做专项题，每次最多6题，做完继续补入；次日顺序更新，已做记录保留。'}`)}
   <View style={{flexDirection:'row',gap:8}}>{(['英语','数学','逻辑'] as const).map(s=>button(s,()=>startPractice(s,mode),subject===s))}</View>
   <ScrollView horizontal showsHorizontalScrollIndicator keyboardShouldPersistTaps="handled"><View style={{flexDirection:'row',gap:8}}>{available.map(item=>button(item.topic,()=>{setSelected(item.id);reset();},q?.id===item.id))}</View></ScrollView>
   {q?<View style={card}>{heading(q.topic)}{text(q.prompt)}{!answer&&questionHistory(data,q,day).at(-1)&&text(`上次作答：${questionHistory(data,q,day).at(-1)!.date} · ${questionHistory(data,q,day).at(-1)!.status==='done'?'答对':'待复练'}。当前为主动再练。`)}{q.options.map((option,i)=><Pressable key={option} accessibilityRole="radio" accessibilityLabel={`${String.fromCharCode(65+i)}. ${option}`} accessibilityState={{checked:choice===i,disabled:disabled||!!answer}} disabled={disabled||!!answer} onPress={()=>setChoice(i)} style={{padding:14,minHeight:48,borderWidth:1,borderRadius:10,borderColor:choice===i?c.brand:c.separator}}>{text(`${String.fromCharCode(65+i)}. ${option}`)}</Pressable>)}
    {answer?<View accessibilityLiveRegion="polite" style={{gap:10}}>{heading(answer.correct?'本次答对':'本次答错，已加入待复练')}{text(`正确答案 ${String.fromCharCode(65+q.answer)}`)}{text(q.explanation)}{text(persistence==='saving'?'正在保存作答…':persistence==='saved'?'作答已保存，可刷新或继续下一题':'作答尚未保存')}{persistence==='failed'&&button('重试保存作答',()=>{void submit();})}{button('下一题',nextQuestion,persistence!=='saved')}{button('重新作答',()=>{setMode('all');reset();},persistence!=='saved')}</View>:button('核对答案并记录',()=>{void submit();},choice===null)}
   </View>:<View style={{gap:8}}>{text(mode==='next'?'本科目当前没有未做题。题库有限，不把旧题冒充新题；可复练错题或继续真题安排。':'本科目暂无待复练题。')}{button('进入真题训练',()=>setSection('真题与路线'))}</View>}
   <View style={card}>{heading('固定写作示例')}{text('企业试行四天工作制后销售额增长，管理者认为应全面推广。用20分钟列出论证漏洞并写一段分析。')}{button(writingHint?'收起分析提示':'展开分析提示',()=>setWritingHint(!writingHint))}{writingHint&&text('检查同期营销、季节性和人员变化；试点是否代表所有部门；销售额是否等于效率或利润。说明每个漏洞怎样削弱结论。此练习不自动评分。')}</View>
  </>}
  {section==='真题与路线'&&<>
   <View style={card}>{heading('2024—2026 年真题库')}{text('2024年摸底，2025年强化，2026年留作后期检测。高校转载和第三方整理均不等于考试机构官方答案。')}{examPapers.map(p=><View key={p.id}>{button(`${p.year} · ${p.subject==='204'?'英语（二）':'管综'}`,()=>{void open(p.url);})}{text(p.source+(p.containsAnswers?' · 含参考答案':''))}</View>)}</View>
   <View style={card}>{heading('历年真题')}{text('2024年分段摸底，2025年强化，2026年留作后期检测。作文需另行批改。')}{button('北理工 · 真题与答案',()=>{void open('https://pdc.bit.edu.cn/xs%26xy/bkq/d044e07614714a44a98f6a6d9ebf0ba7.htm');})}{button('中国石油大学 · 真题解析',()=>{void open('https://mba.upc.edu.cn/_t1664/2024/0723/c19452a258464/page.psp');})}</View>
   <View style={card}>{heading('八周路线')}{text('10/24—11/8：摸底，补词汇、数学与逻辑基础。\n11/9—11/29：真题专项限时，交替练两类作文。\n11/30—12/13：检验整卷节奏，补反复错题。\n12/14—12/18：高频错题、作文结构和考试安排。')}{text('初试计划为12月19日上午管综、下午英语（二），以准考证为准。每门3小时，至少争取两次连续3小时模考；三天各一小时不等于完整模考。初试达线还需复试。')}{button('教育部 · 研考通知',()=>{void open('https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202609/t20260924_1451846.html');})}{button('研招网 · 审核与准考证',()=>{void open('https://yz.chsi.com.cn/apply/main.do');})}</View>
  </>}
 </View>;
}
