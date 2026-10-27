import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ExamStudyPanel from './ExamStudyPanel';
import { blankData, copy, validateData } from './model';
import type { LifeData } from '@/services/lifeNavigation';
import { questions, recordAnswer, addStudyDay, studyId } from './examStudy';
afterEach(() => { cleanup(); window.history.replaceState(null, '', '/'); });
function Harness({initial=blankData()}: {initial?:LifeData}){const [data,setData]=useState(initial);return <ExamStudyPanel data={data} day="2026-10-24" focus={vi.fn()} saveAnswer={async fn=>{setData(prev=>{const next=copy(prev);fn(next);return next;});}} edit={fn=>setData(prev=>{const next=copy(prev);fn(next);return next;})}/>;}
describe('exam study user flow',()=>{
 it('creates one shared daily plan and lets the learner explicitly mark work done',()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  fireEvent.click(screen.getAllByRole('checkbox')[0]);expect(screen.getByText('本日已勾选完成 30 / 60 分钟计划')).toBeTruthy();
 });
 it('does not show an answer before submission and records wrong answers for review',async()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
  expect(screen.queryByText(questions[0].explanation)).toBeNull();
  expect(screen.getByRole('button',{name:'核对答案并记录'})).toBeDisabled();
  fireEvent.click(screen.getByRole('radio',{name:'A. cancel permanently'}));
  fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
  expect(screen.getByRole('status')).toHaveTextContent('本次答错');
  await waitFor(()=>expect(screen.getByText('作答已保存，可刷新或继续下一题')).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'待复练'}));
  expect(screen.getByText(questions[0].prompt)).toBeTruthy();
 });
 it('keeps correct-answer feedback visible when a wrong question is resolved',async()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
  fireEvent.click(screen.getByRole('radio',{name:'A. cancel permanently'}));
  fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
  await waitFor(()=>expect(screen.getByText('作答已保存，可刷新或继续下一题')).toBeTruthy());
  fireEvent.click(screen.getByRole('button',{name:'待复练'}));
  fireEvent.click(screen.getByRole('radio',{name:'B. delay until later'}));
  fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
  expect(screen.getByRole('status')).toHaveTextContent('本次答对');
  expect(screen.getByText(questions[0].explanation)).toBeTruthy();
 });
 it('uses the existing validated backup format without introducing hidden storage',()=>{
  const data:LifeData=blankData();addStudyDay(data,'2026-10-24');recordAnswer(data,'2026-10-24',questions[0],0);
  expect(()=>validateData(data)).not.toThrow();
 });
 it('surfaces capacity failures rather than pretending a plan was added',()=>{
  render(<ExamStudyPanel saveAnswer={async()=>{}} data={blankData()} day="2026-10-24" focus={vi.fn()} edit={()=>{throw Error('每周最多100项任务');}}/>);
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));expect(screen.getByRole('alert')).toHaveTextContent('100');
 });
});

it('opens the next unpracticed question from saved history and preserves feedback until next',async()=>{
 const data=blankData();recordAnswer(data,'2026-10-23',questions[0],questions[0].answer);
 render(<Harness initial={data}/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
 expect(screen.getByText(questions[1].prompt)).toBeTruthy();
 fireEvent.click(screen.getByRole('radio',{name:'C. Less commuting does not guarantee higher productivity.'}));
 fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
 expect(screen.getByRole('status')).toHaveTextContent('本次答对');
 await waitFor(()=>expect(screen.getByRole('button',{name:'下一题'})).not.toBeDisabled());
 fireEvent.click(screen.getByRole('button',{name:'下一题'}));
 expect(screen.getByText(questions[2].prompt)).toBeTruthy();
 expect(screen.getAllByRole('radio').every(r=>!(r as HTMLInputElement).checked)).toBe(true);
});
it('links the scheduled subject to practice without adding or completing tasks',()=>{
 const edit=vi.fn();render(<ExamStudyPanel saveAnswer={async()=>{}} data={blankData()} day="2026-10-26" edit={edit} focus={vi.fn()}/>);
 fireEvent.click(screen.getByRole('button',{name:'练习逻辑'}));
 expect(screen.getByText(questions.find(q=>q.id==='l01')!.prompt)).toBeTruthy();
 expect(edit).not.toHaveBeenCalled();
});
it('shows a truthful exhaustion state and allows deliberate review of answered questions',()=>{
 const data=blankData();questions.filter(q=>q.subject==='英语').forEach(q=>recordAnswer(data,'2026-10-23',q,q.answer));
 render(<Harness initial={data}/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
 expect(screen.getByText(/本科目当前没有未做题/)).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'全部题库'}));
 expect(screen.getByText(questions[0].prompt)).toBeTruthy();
});
it('opens an earlier mistake before the first unseen question',()=>{
 const data=blankData();recordAnswer(data,'2026-10-23',questions[3],0);
 render(<Harness initial={data}/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
 expect(screen.getByText(questions[3].prompt)).toBeTruthy();
});

describe('real paper daily plan', () => {
 it('shows dated paper sections and two-hour allocation without replacing warmup history', () => {
  render(<ExamStudyPanel saveAnswer={async()=>{}} data={blankData()} day="2026-10-27" edit={()=>{}} focus={()=>{}}/>);
  expect(screen.getByText('本日已勾选完成 0 / 120 分钟计划')).toBeTruthy();
  expect(screen.getByRole('link',{name:'打开2024年英语（二）原卷 ↗'}).getAttribute('href')).toContain('bbfa3fc');
  expect(screen.getByText(/尚不支持真题在线自动判分/)).toBeTruthy();
 });
});

it('does not show saved old-plan results as completion of new real-paper work', () => {
 const data=blankData();addStudyDay(data,'2026-10-26');
 Object.values(data.weeks).flatMap(w=>w.tasks).forEach(t=>{t.date='2026-10-27';t.id=studyId(t.date,t.title.includes('英语')?'english':t.title.includes('错题')?'review':'comprehensive');t.status='done';t.result='旧计划的结果';});
 render(<ExamStudyPanel data={data} day="2026-10-27" edit={()=>{}} focus={()=>{}}/>);
 expect(screen.getByText('本日已勾选完成 0 / 120 分钟计划')).toBeTruthy();
 expect(screen.queryByDisplayValue('旧计划的结果')).toBeNull();
});
