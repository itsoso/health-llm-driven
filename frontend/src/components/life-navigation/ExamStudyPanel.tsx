'use client';
import React, { useState } from 'react';
import type { LifeData, LifeTask } from '@/services/lifeNavigation';
import { localDate } from './model';
import { dailyStudy, daysUntil, examDate, phaseFor, addStudyDay, studyTask, type Subject, comprehensiveSubject } from './examStudy';
import ServerExamPractice from './ServerExamPractice';
import { paperAssignment, examPapers } from './examPapers';
import css from './exam-study.module.css';
import { useNavigationParam } from './useNavigationParam';
const studySections = { plan: 'plan', practice: 'practice', resources: 'resources' } as const;

type Props = { owner: number; data: LifeData; day: string; edit: (change: (draft: LifeData) => void) => void; focus: (task: LifeTask) => void };
export default function ExamStudyPanel({owner,data,day,edit,focus}:Props) {
 const [section,setSection]=useNavigationParam<'plan'|'practice'|'resources'>('study', studySections, 'plan');
 const [subject,setSubject]=useState<Subject>('英语');
 const [error,setError]=useState('');
 const assignment=paperAssignment(day);
 const plan=dailyStudy(day);const days=daysUntil(localDate());
 const completed=plan.filter(t=>studyTask(data,day,t.key)?.status==='done').reduce((n,t)=>n+t.minutes,0);
 const mutate=(fn:(d:LifeData)=>void)=>{try {edit(fn);setError('');}catch(e){setError(e instanceof Error?e.message:'修改未完成，请重试。');}};
 const startPractice=(s:Subject)=>{setSubject(s);setSection('practice');};
 return <section className={css.panel} aria-label="备考学习"><fieldset style={{border:0,margin:0,padding:0,minWidth:0}}>
  <div className={css.hero}><div><span className={css.kicker}>EMBA · 每天两小时</span><h2>浙江大学 EMBA · 两小时备考</h2><p>英语四级基础起步 · 199 管综 + 204 英语（二）</p></div><div className={css.countdown}><strong>{days>0?days:days===0?'今天':'已结束'}</strong><span>{days>0?'天后初试':days===0?'初试日':'进入考后阶段'}</span><small>{examDate} · 以准考证为准</small></div></div>
  <nav className={css.tabs} aria-label="备考栏目">{([{key:'plan',label:'每日计划'},{key:'practice',label:'练习与错题'},{key:'resources',label:'真题与路线'}] as const).map(t=><button type="button" key={t.key} aria-pressed={section===t.key} onClick={()=>setSection(t.key)}>{t.label}</button>)}</nav>
  {error&&<p role="alert" className={css.error}>{error}</p>}
  <p className={css.hint}>练习答案独立保存到当前账号。计划和学习笔记仍需点「保存工作区」。</p>
  {assignment&&section!=='resources'&&<article className={css.card} aria-label="每日真题训练"><h3>{day} · {assignment.year}年真题 · {assignment.review?'复测与补弱':'首轮分段'}</h3><p>英语：{assignment.english} · 管综：{assignment.comprehensive}</p><p>{assignment.writing}</p><div className={css.filters}>{assignment.papers.map(p=><a key={p.id} href={p.url} target="_blank" rel="noopener noreferrer">打开{p.year}年{p.subject==='204'?'英语（二）':'管综'}原卷 ↗</a>)}</div><p className={css.hint}>原卷训练：在纸上作答，在每日计划记录结果；尚不支持真题在线自动判分。{assignment.papers.some(p=>p.containsAnswers)?'文件含参考答案，请先遮住答案作答。':''} {assignment.papers.map(p=>p.source).join(' / ')}。进入第二轮会明确标为复测，不冒充新题。</p></article>}
  {section==='plan'&&<>
   <div className={css.sectionTitle}><div><h3>{day} · {phaseFor(day)}</h3><p>本日已勾选完成 {completed} / {plan.reduce((n,t)=>n+t.minutes,0)} 分钟计划</p></div>{plan.length>0&&<button type="button" className={css.primary} onClick={()=>mutate(d=>addStudyDay(d,day))}>加入当日计划</button>}</div>
   {!plan.length&&<p>初试日及之后不再生成冲刺任务。请核对准考证，考后关注成绩和复试通知。</p>}
   <div className={css.cards}>{plan.map(t=>{const saved=studyTask(data,day,t.key);return <article className={css.card} key={t.key}><div className={css.cardHead}><h3>{t.title}</h3><strong>{t.minutes} 分钟</strong></div><p>{t.detail}</p>{assignment?<button type="button" onClick={()=>setSection('resources')}>查看真题与记录方法</button>:t.key==='english'?<button type="button" onClick={()=>startPractice('英语')}>练习英语</button>:t.key==='review'?<button type="button" onClick={()=>startPractice('英语')}>复练错题</button>:comprehensiveSubject(day)!=='写作'?<button type="button" onClick={()=>startPractice(comprehensiveSubject(day) as Subject)}>练习{comprehensiveSubject(day)}</button>:<button type="button" onClick={()=>setSection('resources')}>选择写作真题</button>}{saved?<>
    <label className={css.check}><input type="checkbox" checked={saved.status==='done'} onChange={e=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.status=e.target.checked?'done':'planned';})}/>我已完成这项训练</label>
    <label className={css.field}>学习结果 · {t.title}<textarea value={saved.result} maxLength={4000} placeholder="记下材料、正确题数、耗时和卡住的地方" onChange={e=>mutate(d=>{const task=studyTask(d,day,t.key);if(task)task.result=e.target.value;})}/></label>
    <button type="button" onClick={()=>focus(saved)}>开始专注并保存</button>
   </>:<p className={css.hint}>加入计划后可以记录完成情况，与今日、周计划共用同一条任务。</p>}</article>;})}</div>
   <div className={css.callout}><strong>先做分段摸底，再决定补哪里</strong><p>按每日计划分段训练，记录正确数与耗时。新真题计划单独保存，不替换既有计划或继承其完成状态。分段结果只作诊断，不折算成整卷成绩。每天只多练一个弱项，不靠补打卡追进度。</p></div>
  </>}
  {section==='practice'&&<ServerExamPractice owner={owner} day={day} initialSubject={subject}/>}
  {section==='resources'&&<>
   <article className={css.card}><h3>2024—2026 年真题库</h3><p>年份按试卷命名。高校转载和第三方整理均不等于考试机构官方答案。做完记录：年份 / 科目 / 题号 / 正确数 / 用时 / 错因；没有核对的不计正确。2026年卷留到11月30日开始，避免提前看答案影响检测。</p>{examPapers.map(p=><p key={p.id}><a href={p.url} target="_blank" rel="noopener noreferrer">{p.year} · {p.subject==='204'?'英语（二）':'管综'} ↗</a> · {p.source}{p.containsAnswers?' · 含参考答案':''}</p>)}</article>
   <div className={css.cards}>
    <article className={css.card}><h3>历年真题</h3><p>2024年卷分段摸底，2025年卷强化，2026年卷留作后期检测。解析可能有争议，作文需另行批改。</p><a href="https://pdc.bit.edu.cn/xs%26xy/bkq/d044e07614714a44a98f6a6d9ebf0ba7.htm" target="_blank" rel="noopener noreferrer">北理工 · 2012—2025年真题与答案 ↗</a><a href="https://mba.upc.edu.cn/_t1664/2024/0723/c19452a258464/page.psp" target="_blank" rel="noopener noreferrer">中国石油大学 · 真题解析 ↗</a></article>
    <article className={css.card}><h3>考试与录取</h3><p>初试计划：12月19日上午管综、下午英语（二），具体考场与时间以准考证为准。初试达线还需复试，不承诺录取。</p><a href="https://www.moe.gov.cn/jyb_xwfb/gzdt_gzdt/s5987/202609/t20260924_1451846.html" target="_blank" rel="noopener noreferrer">教育部 · 2027年研考通知 ↗</a><a href="https://yz.chsi.com.cn/apply/main.do" target="_blank" rel="noopener noreferrer">研招网 · 审核状态与准考证 ↗</a></article>
   </div>
   <article className={css.card}><h3>八周路线</h3><ol><li>10/24—11/8：分段摸底，补词汇、基础数学和逻辑条件。</li><li>11/9—11/29：真题专项限时，交替练管综两类作文。</li><li>11/30—12/13：检验完整试卷的节奏，针对反复错误补弱。</li><li>12/14—12/18：只看高频错题、作文结构和考试安排。</li></ol><div className={css.callout}><strong>完整模考需要单独腾出时间</strong><p>每门正式考试3小时。每天两小时可分段训练，但至少争取两次连续3小时检验耐力与取舍；不能用三天各一小时的分数冒充完整模考。</p></div></article>
  </>}
 </fieldset></section>;
}
