import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import ExamStudyPanel from '../ExamStudyPanel';
import { blankData } from '../../../utils/lifeNavigationModel';
import { fetchExamPractice } from '../../../services/examPractice';
jest.mock('../../../services/examPractice',()=>({fetchExamPractice:jest.fn(),fetchExamAttempts:jest.fn(),submitExamAttempt:jest.fn()}));
beforeEach(()=>{jest.clearAllMocks();(fetchExamPractice as jest.Mock).mockResolvedValue({catalog_version:'server',day:'2026-10-26',today:'2026-10-26',questions:[{id:'server-l1',version:1,subject:'逻辑',topic:'服务端逻辑',prompt:'服务端新题',options:['甲','乙'],source:'原创',difficulty:'基础'}],progress:[],queue:['server-l1'],plan:[],total_minutes:120,legacy_notice:''});});
it('opens the scheduled subject from the owner server bank without creating study records',async()=>{
 const edit=jest.fn();const view=render(<ExamStudyPanel owner={7} data={blankData()} day="2026-10-26" disabled={false} focus={jest.fn()} edit={edit}/>);
 fireEvent.press(view.getByLabelText('练习逻辑'));await waitFor(()=>view.getByText('服务端新题'));expect(fetchExamPractice).toHaveBeenCalledWith(7,'2026-10-26');expect(edit).not.toHaveBeenCalled();
});
it('keeps manual planning and paper references while practice saves separately',()=>{
 const edit=jest.fn();const view=render(<ExamStudyPanel owner={7} data={blankData()} day="2026-10-28" disabled={false} focus={jest.fn()} edit={edit}/>);
 expect(view.getByText('练习答案独立保存到当前账号。计划和笔记仍需点顶部「保存」。')).toBeTruthy();fireEvent.press(view.getByLabelText('加入当日计划'));expect(edit).toHaveBeenCalledTimes(1);expect(fetchExamPractice).not.toHaveBeenCalled();fireEvent.press(view.getByLabelText('真题与路线'));expect(view.getByText('2024—2026 年真题库')).toBeTruthy();
});
