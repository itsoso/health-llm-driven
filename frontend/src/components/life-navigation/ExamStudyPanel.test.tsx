import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import ExamStudyPanel from './ExamStudyPanel';
import { blankData, copy, validateData } from './model';
import type { LifeData } from '@/services/lifeNavigation';
import { questions, recordAnswer, addStudyDay, studyId } from './examStudy';
afterEach(() => { cleanup(); window.history.replaceState(null, '', '/'); });
function Harness({initial=blankData()}: {initial?:LifeData}){const [data,setData]=useState(initial);return <ExamStudyPanel owner={7} data={data} day="2026-10-24" focus={vi.fn()} edit={fn=>setData(prev=>{const next=copy(prev);fn(next);return next;})}/>;}
describe('exam study user flow',()=>{
 it('creates one shared daily plan and lets the learner explicitly mark work done',()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  fireEvent.click(screen.getAllByRole('checkbox')[0]);expect(screen.getByText('本日已勾选完成 30 / 60 分钟计划')).toBeTruthy();
 });
 it('uses the existing validated backup format without introducing hidden storage',()=>{
  const data:LifeData=blankData();addStudyDay(data,'2026-10-24');recordAnswer(data,'2026-10-24',questions[0],0);
  expect(()=>validateData(data)).not.toThrow();
 });
 it('surfaces capacity failures rather than pretending a plan was added',()=>{
  render(<ExamStudyPanel owner={7} data={blankData()} day="2026-10-24" focus={vi.fn()} edit={()=>{throw Error('每周最多100项任务');}}/>);
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));expect(screen.getByRole('alert')).toHaveTextContent('100');
 });
});

describe('real paper daily plan', () => {
 it('shows dated paper sections and two-hour allocation without replacing warmup history', () => {
  render(<ExamStudyPanel owner={7} data={blankData()} day="2026-10-27" edit={()=>{}} focus={()=>{}}/>);
  expect(screen.getByText('本日已勾选完成 0 / 120 分钟计划')).toBeTruthy();
  expect(screen.getByRole('button',{name:'在线做2024年英语（二）'})).toBeTruthy();
  expect(screen.getAllByRole('link',{name:'打开原卷 ↗'}).some(link=>link.getAttribute('href')?.includes('bbfa3fc'))).toBe(true);
  expect(screen.getByText(/客观题可在线作答、判分/)).toBeTruthy();
 });
 it('offers online entry for all six papers and keeps subjective scoring honest',()=>{
  render(<ExamStudyPanel owner={7} data={blankData()} day="2026-10-27" edit={()=>{}} focus={()=>{}}/>);
  fireEvent.click(screen.getByRole('button',{name:'真题与路线'}));
  expect(screen.getAllByRole('button',{name:/在线做 20(24|25|26) ·/})).toHaveLength(6);
  expect(screen.getByText(/写作和翻译保留原卷与参考材料/)).toBeTruthy();
 });
});

it('does not show saved old-plan results as completion of new real-paper work', () => {
 const data=blankData();addStudyDay(data,'2026-10-26');
 Object.values(data.weeks).flatMap(w=>w.tasks).forEach(t=>{t.date='2026-10-27';t.id=studyId(t.date,t.title.includes('英语')?'english':t.title.includes('错题')?'review':'comprehensive');t.status='done';t.result='旧计划的结果';});
 render(<ExamStudyPanel owner={7} data={data} day="2026-10-27" edit={()=>{}} focus={()=>{}}/>);
 expect(screen.getByText('本日已勾选完成 0 / 120 分钟计划')).toBeTruthy();
 expect(screen.queryByDisplayValue('旧计划的结果')).toBeNull();
});
