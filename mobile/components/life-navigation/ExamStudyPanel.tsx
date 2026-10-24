import React, { useState } from 'react';
import { Linking, Pressable, ScrollView, Text, View } from 'react-native';
import type { LifeData, LifeTask } from '../../services/lifeNavigation';
import { localDate } from '../../utils/lifeNavigationModel';
import { addStudyDay, dailyStudy, daysUntil, examDate, phaseFor, questions, questionHistory, recordAnswer, studyTask, wrongQuestions } from '../../utils/examStudy';
import { useLifeControls } from './Controls';

type Props = {data:LifeData; day:string; disabled:boolean; edit:(change:(data:LifeData)=>void)=>void; focus:(task:LifeTask)=>void};
export default function ExamStudyPanel({data,day,disabled,edit,focus}:Props) {
 const {c,text,button,field}=useLifeControls(disabled);
 const [section,setSection]=useState('一小时计划'),[subject,setSubject]=useState('英语'),[onlyWrong,setOnlyWrong]=useState(false);
 const [selected,setSelected]=useState(questions[0].id),[choice,setChoice]=useState<number|null>(null);
 const [feedback,setFeedback]=useState<{id:string;correct:boolean}|null>(null),[error,setError]=useState(''),[writingHint,setWritingHint]=useState(false);
 const plan=dailyStudy(day),wrong=wrongQuestions(data),remaining=daysUntil(localDate());
 const available=questions.filter(q=>q.subject===subject&&(!onlyWrong||wrong.some(w=>w.id===q.id)||feedback?.id===q.id));
 const q=available.find(item=>item.id===selected)??available[0];
 const answer=feedback?.id===q?.id?feedback:null;
 const reset=()=>{setChoice(null);setFeedback(null);};
 const mutate=(change:(d:LifeData)=>void)=>{if(disabled)return;try{edit(change);setError('');}catch(e){setError(e instanceof Error?e.message:'修改失败，请重试。');}};
 const open=async(url:string)=>{try{await Linking.openURL(url);}catch{setError('无法打开资料，请检查网络后重试。');}};
 const heading=(title:string)=><Text accessibilityRole="header" style={{fontSize:20,lineHeight:28,fontWeight:'600',color:c.labelPrimary}}>{title}</Text>;
 const card={padding:16,gap:12,backgroundColor:c.bgCard,borderRadius:14,borderWidth:1,borderColor:c.separator} as const;
 return <View style={{gap:16}}>
  <View style={card}>{heading('EMBA · 每天一小时')}{text('英语四级基础起步 · 199 管综 + 204 英语（二）')}{text(remaining>0?`${remaining} 天后初试`:remaining===0?'今天初试':'初试已结束')}{text(`${examDate} · 以准考证为准`)}</View>
  <View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{['一小时计划','练习与错题','真题与路线'].map(s=>button(s,()=>setSection(s),section===s))}</View>
  {text('学习记录与网页版共用，修改后请点顶部「保存」。完成勾选和热身正确率不代表掌握或录取。')}
  {!!error&&<Text accessibilityRole="alert" style={{color:c.labelPrimary}}>{error}</Text>}
  {section==='一小时计划'&&<>
   {heading(phaseFor(day))}{text(`${day} · 已完成 ${plan.filter(t=>studyTask(data,day,t.key)?.status==='done').reduce((n,t)=>n+t.minutes,0)} / ${plan.length?60:0} 分钟计划`)}
   {plan.length?button('加入当日计划',()=>mutate(d=>addStudyDay(d,day))):text('初试日及之后不再生成冲刺计划，请关注准考证、成绩和复试通知。')}
   {plan.map(t=>{const saved=studyTask(data,day,t.key);return <View key={t.key} style={card}>{heading(`${t.title} · ${t.minutes} 分钟`)}{text(t.detail)}{saved?<>
    <Pressable accessibilityRole="checkbox" accessibilityLabel={`完成${t.title}`} accessibilityState={{checked:saved.status==='done',disabled}} disabled={disabled} onPress={()=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.status=task.status==='done'?'planned':'done';})} style={{minHeight:44,justifyContent:'center'}}>{text(`${saved.status==='done'?'☑':'□'} 我已完成这项训练`)}</Pressable>
    {field(`学习结果 · ${t.title}`,saved.result,v=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.result=v;}))}
    {button(`专注${t.title}并保存`,()=>focus(saved))}
   </>:text('加入计划后即可记录学习结果。')}</View>})}
   {text('先用旧年真题分段摸底，记录正确数和耗时；分段结果不折算整卷成绩。')}
  </>}
  {section==='练习与错题'&&<>
   {heading('基础热身与错题复练')}{text(`已练 ${questions.filter(item=>questionHistory(data,item).length).length} / ${questions.length} 题 · 待复练 ${wrong.length} 题`)}
   {text('原创基础题，不是历年真题，也不代表联考难度。首次作答和当日最近一次复练保存在任务记录中。')}
   {button(onlyWrong?'显示全部练习':'只看待复练',()=>{setOnlyWrong(!onlyWrong);reset();})}
   <View style={{flexDirection:'row',gap:8}}>{['英语','数学','逻辑'].map(s=>button(s,()=>{setSubject(s);reset();},subject===s))}</View>
   <ScrollView horizontal showsHorizontalScrollIndicator keyboardShouldPersistTaps="handled"><View style={{flexDirection:'row',gap:8}}>{available.map(item=>button(item.topic,()=>{setSelected(item.id);reset();},q?.id===item.id))}</View></ScrollView>
   {q?<View style={card}>{heading(q.topic)}{text(q.prompt)}{q.options.map((option,i)=><Pressable key={option} accessibilityRole="radio" accessibilityLabel={`${String.fromCharCode(65+i)}. ${option}`} accessibilityState={{checked:choice===i,disabled:disabled||!!answer}} disabled={disabled||!!answer} onPress={()=>setChoice(i)} style={{padding:14,minHeight:48,borderWidth:1,borderRadius:10,borderColor:choice===i?c.brand:c.separator}}>{text(`${String.fromCharCode(65+i)}. ${option}`)}</Pressable>)}
    {answer?<View accessibilityLiveRegion="polite" style={{gap:10}}>{heading(answer.correct?'本次答对':'本次答错，已加入待复练')}{text(`正确答案 ${String.fromCharCode(65+q.answer)}`)}{text(q.explanation)}{button('重新作答',reset)}</View>:button('核对答案并记录',()=>{if(choice===null||disabled)return;try{edit(d=>recordAnswer(d,day,q,choice));setFeedback({id:q.id,correct:choice===q.answer});setError('');}catch(e){setError(e instanceof Error?e.message:'作答记录失败');}},choice===null)}
   </View>:text('本科目暂无待复练题，可以显示全部练习或继续真题训练。')}
   <View style={card}>{heading('写作专项')}{text('企业试行四天工作制后销售额增长，管理者认为应全面推广。用20分钟列出论证漏洞并写一段分析。')}{button(writingHint?'收起分析提示':'展开分析提示',()=>setWritingHint(!writingHint))}{writingHint&&text('检查同期营销、季节性和人员变化；试点是否代表所有部门；销售额是否等于效率或利润。说明每个漏洞怎样削弱结论。此练习不自动评分。')}</View>
  </>}
  {section==='真题与路线'&&<>
   <View style={card}>{heading('历年真题')}{text('2022年卷用于分段摸底，较早年份练专项，保留2023—2025年卷用于模考。作文需另行批改。')}{button('北理工 · 真题与答案',()=>{void open('https://pdc.bit.edu.cn/xs%26xy/bkq/d044e07614714a44a98f6a6d9ebf0ba7.htm');})}{button('中国石油大学 · 真题解析',()=>{void open('https://mba.upc.edu.cn/_t1664/2024/0723/c19452a258464/page.psp');})}</View>
   <View style={card}>{heading('八周路线')}{text('10/24—11/8：摸底，补词汇、数学与逻辑基础。\n11/9—11/29：真题专项限时，交替练两类作文。\n11/30—12/13：检验整卷节奏，补反复错题。\n12/14—12/18：高频错题、作文结构和考试安排。')}{text('初试计划为12月19日上午管综、下午英语（二），以准考证为准。每门3小时，至少争取两次连续3小时模考；三天各一小时不等于完整模考。初试达线还需复试。')}{button('教育部 · 研考通知',()=>{void open('https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202609/t20260924_1451846.html');})}{button('研招网 · 审核与准考证',()=>{void open('https://yz.chsi.com.cn/apply/main.do');})}</View>
  </>}
 </View>;
}
