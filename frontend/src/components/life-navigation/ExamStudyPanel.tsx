'use client';
import React, { useState } from 'react';
import type { LifeData, LifeTask } from '@/services/lifeNavigation';
import { localDate } from './model';
import { dailyStudy, daysUntil, examDate, phaseFor, questions, recordAnswer, addStudyDay, studyTask, wrongQuestions, questionHistory, type StudyQuestion } from './examStudy';
import css from './exam-study.module.css';

type Props = { data: LifeData; day: string; edit: (change: (draft: LifeData) => void) => void; focus: (task: LifeTask) => void };
export default function ExamStudyPanel({data,day,edit,focus}:Props) {
 const [section,setSection]=useState<'plan'|'practice'|'resources'>('plan');
 const [subject,setSubject]=useState('英语');const [onlyWrong,setOnlyWrong]=useState(false);
 const [selected,setSelected]=useState(questions[0].id);const [choice,setChoice]=useState<number|null>(null);
 const [feedback,setFeedback]=useState<{id:string;day:string;correct:boolean}|null>(null);const [error,setError]=useState('');
 const plan=dailyStudy(day);const wrong=wrongQuestions(data);const days=daysUntil(localDate());
 const attempts=questions.filter(q=>questionHistory(data,q).length>0).length;
 const completed=plan.filter(t=>studyTask(data,day,t.key)?.status==='done').reduce((n,t)=>n+t.minutes,0);
 const available=questions.filter(q=>q.subject===subject&&(!onlyWrong||wrong.some(w=>w.id===q.id)||(feedback?.id===q.id&&feedback.day===day)));
 const question=available.find(q=>q.id===selected)??available[0];
 const currentFeedback=feedback?.id===question?.id&&feedback.day===day?feedback:null;
 const mutate=(fn:(d:LifeData)=>void)=>{try {edit(fn);setError('');}catch(e){setError(e instanceof Error?e.message:'修改未完成，请重试。');}};
 const pick=(q:StudyQuestion)=>{setSelected(q.id);setChoice(null);setFeedback(null);};
 return <section className={css.panel} aria-label="备考学习">
  <div className={css.hero}><div><span className={css.kicker}>EMBA · 每天一小时</span><h2>把今天的一小时，用在薄弱处</h2><p>英语四级基础起步 · 199 管综 + 204 英语（二）</p></div><div className={css.countdown}><strong>{days>0?days:days===0?'今天':'已结束'}</strong><span>{days>0?'天后初试':days===0?'初试日':'进入考后阶段'}</span><small>{examDate} · 以准考证为准</small></div></div>
  <nav className={css.tabs} aria-label="备考栏目">{([{key:'plan',label:'一小时计划'},{key:'practice',label:'练习与错题'},{key:'resources',label:'真题与路线'}] as const).map(t=><button type="button" key={t.key} aria-pressed={section===t.key} onClick={()=>setSection(t.key)}>{t.label}</button>)}</nav>
  {error&&<p role="alert" className={css.error}>{error}</p>}
  <p className={css.hint}>学习记录随「保存工作区」写入当前账号。勾选完成不代表掌握，练习正确率不代表联考分数。</p>
  {section==='plan'&&<>
   <div className={css.sectionTitle}><div><h3>{day} · {phaseFor(day)}</h3><p>本日已勾选完成 {completed} / {plan.length?60:0} 分钟计划</p></div>{plan.length>0&&<button type="button" className={css.primary} onClick={()=>mutate(d=>addStudyDay(d,day))}>加入当日计划</button>}</div>
   {!plan.length&&<p>初试日及之后不再生成冲刺任务。请核对准考证，考后关注成绩和复试通知。</p>}
   <div className={css.cards}>{plan.map(t=>{const saved=studyTask(data,day,t.key);return <article className={css.card} key={t.key}><div className={css.cardHead}><h3>{t.title}</h3><strong>{t.minutes} 分钟</strong></div><p>{t.detail}</p>{saved?<>
    <label className={css.check}><input type="checkbox" checked={saved.status==='done'} onChange={e=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.status=e.target.checked?'done':'planned';})}/>我已完成这项训练</label>
    <label className={css.field}>学习结果 · {t.title}<textarea value={saved.result} maxLength={4000} placeholder="记下材料、正确题数、耗时和卡住的地方" onChange={e=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.result=e.target.value;})}/></label>
    <button type="button" onClick={()=>focus(saved)}>开始专注并保存</button>
   </>:<p className={css.hint}>加入计划后可以记录完成情况，与今日、周计划共用同一条任务。</p>}</article>;})}</div>
   <div className={css.callout}><strong>先做分段摸底，再决定补哪里</strong><p>第一周把旧年真题拆成30分钟英语和20分钟管综专项，记录正确数与耗时。分段结果只作诊断，不折算成整卷成绩。每天只多练一个弱项，不靠补打卡追进度。</p></div>
  </>}
  {section==='practice'&&<>
   <div className={css.sectionTitle}><div><h3>基础热身与错题回看</h3><p>已练 {attempts} / {questions.length} 题 · 待复练 {wrong.length} 题</p></div><label className={css.check}><input type="checkbox" checked={onlyWrong} onChange={e=>{setOnlyWrong(e.target.checked);setChoice(null);setFeedback(null);}}/>只看待复练</label></div>
   <p className={css.hint}>这些是原创基础热身题，不是历年真题，也不代表联考难度；完成后请转入真题训练。首次作答保留在任务结果，复练记录保留在改进策略中。</p>
   <div className={css.filters}>{['英语','数学','逻辑'].map(s=><button type="button" key={s} aria-pressed={subject===s} onClick={()=>{setSubject(s);setChoice(null);setFeedback(null);}}>{s}</button>)}</div>
   <div className={css.questionLayout}><nav className={css.questionList} aria-label="选择练习题">{available.map((q,i)=><button type="button" key={q.id} aria-pressed={question?.id===q.id} onClick={()=>pick(q)}>{i+1}. {q.topic}{wrong.some(w=>w.id===q.id)?' · 待复练':''}</button>)}</nav>
   {question?<article className={css.card}><span className={css.kicker}>{question.subject} / {question.topic}</span><h3 className={css.prompt}>{question.prompt}</h3><fieldset className={css.answers} disabled={!!currentFeedback}><legend>选择答案</legend>{question.options.map((text,i)=><label key={text}><input type="radio" name={`answer-${question.id}`} checked={choice===i} onChange={()=>setChoice(i)}/><span>{String.fromCharCode(65+i)}. {text}</span></label>)}</fieldset>
    {!currentFeedback?<button type="button" className={css.primary} disabled={choice===null} onClick={()=>{if(choice===null)return;try{edit(d=>recordAnswer(d,day,question,choice));setFeedback({id:question.id,day,correct:choice===question.answer});setError('');}catch(e){setError(e instanceof Error?e.message:'作答记录失败');}}}>核对答案并记录</button>:<div role="status" className={css.callout}><strong>{currentFeedback.correct?'本次答对':'本次答错，已加入待复练'} · 正确答案 {String.fromCharCode(65+question.answer)}</strong><p>{question.explanation}</p><button type="button" onClick={()=>{setChoice(null);setFeedback(null);}}>重新作答</button></div>}
   </article>:<p>这个科目暂无待复练题。可以关闭筛选或去真题入口继续练习。</p>}</div>
   <article className={css.card}><h3>写作专项：先写，后核对</h3><p>一家企业试行四天工作制后销售额增长，管理者认为应在所有部门推广。用20分钟列出论证漏洞，并写一段分析。</p><details><summary>完成后展开分析提示</summary><p>检查同期营销、季节性和人员变化等其他解释；试点样本是否代表所有部门；销售额是否等于效率或利润。指出漏洞后还要说明它为什么削弱结论。此练习没有自动作文评分。</p></details></article>
  </>}
  {section==='resources'&&<>
   <div className={css.cards}>
    <article className={css.card}><h3>历年真题</h3><p>先做2022年卷分段摸底，较早年份练专项，保留2023—2025年完整卷用于模考。解析可能有争议，作文需另行批改。</p><a href="https://pdc.bit.edu.cn/xs%26xy/bkq/d044e07614714a44a98f6a6d9ebf0ba7.htm" target="_blank" rel="noopener noreferrer">北理工 · 2012—2025年真题与答案 ↗</a><a href="https://mba.upc.edu.cn/_t1664/2024/0723/c19452a258464/page.psp" target="_blank" rel="noopener noreferrer">中国石油大学 · 真题解析 ↗</a></article>
    <article className={css.card}><h3>考试与录取</h3><p>初试计划：12月19日上午管综、下午英语（二），具体考场与时间以准考证为准。初试达线还需复试，不承诺录取。</p><a href="https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202609/t20260924_1451846.html" target="_blank" rel="noopener noreferrer">教育部 · 2027年研考通知 ↗</a><a href="https://yz.chsi.com.cn/apply/main.do" target="_blank" rel="noopener noreferrer">研招网 · 审核状态与准考证 ↗</a></article>
   </div>
   <article className={css.card}><h3>八周路线</h3><ol><li>10/24—11/8：分段摸底，补词汇、基础数学和逻辑条件。</li><li>11/9—11/29：真题专项限时，交替练管综两类作文。</li><li>11/30—12/13：检验完整试卷的节奏，针对反复错误补弱。</li><li>12/14—12/18：只看高频错题、作文结构和考试安排。</li></ol><div className={css.callout}><strong>完整模考需要单独腾出时间</strong><p>每门正式考试3小时。每天一小时可分段训练，但至少争取两次连续3小时检验耐力与取舍；不能用三天各一小时的分数冒充完整模考。</p></div></article>
  </>}
 </section>;
}
