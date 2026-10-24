import React, { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import ExamStudyPanel from './ExamStudyPanel';
import { blankData, copy, validateData } from './model';
import type { LifeData } from '@/services/lifeNavigation';
import { questions, recordAnswer, addStudyDay } from './examStudy';
afterEach(cleanup);
function Harness(){const [data,setData]=useState(blankData());return <ExamStudyPanel data={data} day="2026-10-24" focus={vi.fn()} edit={fn=>setData(prev=>{const next=copy(prev);fn(next);return next;})}/>;}
describe('exam study user flow',()=>{
 it('creates one shared daily plan and lets the learner explicitly mark work done',()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));
  expect(screen.getAllByRole('checkbox')).toHaveLength(3);
  fireEvent.click(screen.getAllByRole('checkbox')[0]);expect(screen.getByText('本日已勾选完成 30 / 60 分钟计划')).toBeTruthy();
 });
 it('does not show an answer before submission and records wrong answers for review',()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
  expect(screen.queryByText(questions[0].explanation)).toBeNull();
  expect(screen.getByRole('button',{name:'核对答案并记录'})).toBeDisabled();
  fireEvent.click(screen.getByRole('radio',{name:'A. cancel permanently'}));
  fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
  expect(screen.getByRole('status')).toHaveTextContent('本次答错');
  fireEvent.click(screen.getByRole('checkbox',{name:'只看待复练'}));
  expect(screen.getByText(questions[0].prompt)).toBeTruthy();
 });
 it('keeps correct-answer feedback visible when a wrong question is resolved',()=>{
  render(<Harness/>);fireEvent.click(screen.getByRole('button',{name:'练习与错题'}));
  fireEvent.click(screen.getByRole('radio',{name:'A. cancel permanently'}));
  fireEvent.click(screen.getByRole('button',{name:'核对答案并记录'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'只看待复练'}));
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
  render(<ExamStudyPanel data={blankData()} day="2026-10-24" focus={vi.fn()} edit={()=>{throw Error('每周最多100项任务');}}/>);
  fireEvent.click(screen.getByRole('button',{name:'加入当日计划'}));expect(screen.getByRole('alert')).toHaveTextContent('100');
 });
});
