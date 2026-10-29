import React from 'react';
import { Alert, AppState } from 'react-native';
import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import ServerExamPractice from '../ServerExamPractice';
import { fetchExamPractice, fetchExamAttempts, submitExamAttempt, type ExamPractice, type ExamAttempt } from '../../../services/examPractice';
jest.mock('../../../services/examPractice', () => ({ fetchExamPractice: jest.fn(), fetchExamAttempts: jest.fn(), submitExamAttempt: jest.fn() }));
jest.mock('../../../services/examAttemptPending',()=>({readPendingExamAttempt:jest.fn().mockResolvedValue(null),writePendingExamAttempt:jest.fn().mockResolvedValue(undefined),clearPendingExamAttempt:jest.fn().mockResolvedValue(undefined)}));
import {readPendingExamAttempt,writePendingExamAttempt} from '../../../services/examAttemptPending';
jest.mock('expo-modules-core', () => ({ ...jest.requireActual('expo-modules-core'), uuid: { v4: () => '7d3fca50-1968-4c27-804c-ae508d33017d' } }));
const day='2026-10-28';
const initial=():ExamPractice=>({catalog_version:'test',day,today:day,questions:[{id:'e1',version:1,subject:'英语',topic:'第一题',prompt:'A new server question',options:['Alpha','Beta'],source:'原创',difficulty:'基础'},{id:'e2',version:1,subject:'英语',topic:'第二题',prompt:'Another question',options:['One','Two'],source:'原创',difficulty:'基础'}],progress:[],queue:['e1','e2'],plan:[{subject:'英语',minutes:45,instruction:'按队列练习'}],total_minutes:120,legacy_notice:'旧记录只保留可证明的尝试'});
const attempt=(correct=false):ExamAttempt=>({question:initial().questions[0],id:'a1',question_id:'e1',question_version:1,choice_index:correct?1:0,correct_index:1,correct,explanation:'Body evidence',study_date:day,answered_at:`${day}T01:00:00Z`,elapsed_seconds:3,source:'submitted'});
let model:ExamPractice;
let listener:(s:string)=>void;
beforeEach(()=>{jest.clearAllMocks();model=initial();(fetchExamPractice as jest.Mock).mockImplementation(async()=>model);(fetchExamAttempts as jest.Mock).mockResolvedValue({items:[],total:0});jest.spyOn(AppState,'addEventListener').mockImplementation((_event,cb)=>{listener=cb as typeof listener;return{remove:jest.fn()};});});
afterEach(()=>{jest.restoreAllMocks();jest.useRealTimers();});
it('submits to the owner ledger and reads the saved answer on previous and remount',async()=>{
 const saved=attempt();(submitExamAttempt as jest.Mock).mockImplementation(async()=>{model={...model,progress:[{question_id:'e1',attempt_count:1,latest_correct:false,ever_wrong:true,last_date:day,next_review_date:day}],queue:['e2']};(fetchExamAttempts as jest.Mock).mockResolvedValue({items:[saved],total:1});return saved;});
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('A new server question'));
 fireEvent.press(v.getByLabelText('A. Alpha'));fireEvent.press(v.getByLabelText('提交答案'));
 await waitFor(()=>v.getByText('作答已保存'));expect(submitExamAttempt).toHaveBeenCalledWith(7,expect.objectContaining({question_id:'e1',choice_index:0,question_version:1,request_id:expect.any(String)}));
 fireEvent.press(v.getByLabelText('下一题'));expect(v.getByText('Another question')).toBeTruthy();fireEvent.press(v.getByLabelText('上一题'));
 await waitFor(()=>v.getByText('作答 A · 正确答案 B'));expect(v.queryByLabelText('提交答案')).toBeNull();expect(submitExamAttempt).toHaveBeenCalledTimes(1);
 v.unmount();const reopened=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>reopened.getByLabelText('答题历史'));fireEvent.press(reopened.getByLabelText('答题历史'));await waitFor(()=>reopened.getByText('作答 A · 正确答案 B'));
});
it('retries a failed save with the identical id and answer without faking a saved result',async()=>{
 (submitExamAttempt as jest.Mock).mockRejectedValueOnce(Error('network')).mockResolvedValueOnce(attempt());
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('A new server question'));fireEvent.press(v.getByLabelText('A. Alpha'));fireEvent.press(v.getByLabelText('提交答案'));
 await waitFor(()=>v.getByLabelText('重试保存'));expect(v.queryByText('作答已保存')).toBeNull();expect(v.getByLabelText('下一题').props.accessibilityState.disabled).toBe(true);expect(v.getByLabelText('B. Beta').props.accessibilityState.disabled).toBe(true);
 fireEvent.press(v.getByLabelText('重试保存'));await waitFor(()=>v.getByText('作答已保存'));expect((submitExamAttempt as jest.Mock).mock.calls[1]).toEqual((submitExamAttempt as jest.Mock).mock.calls[0]);
});
it('keeps corrected mistakes readable and starts a new attempt only explicitly',async()=>{
 model.progress=[{question_id:'e1',attempt_count:2,latest_correct:true,ever_wrong:true,last_date:day,next_review_date:'2026-10-31'}];(fetchExamAttempts as jest.Mock).mockResolvedValue({items:[{...attempt(true),id:'a2'},attempt()],total:2});
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByLabelText('错题本'));fireEvent.press(v.getByLabelText('错题本'));await waitFor(()=>v.getByText('作答 A · 正确答案 B'));expect(v.getByText('作答 B · 正确答案 B')).toBeTruthy();expect(v.getByLabelText('B. Beta').props.accessibilityState.disabled).toBe(true);expect(submitExamAttempt).not.toHaveBeenCalled();
 fireEvent.press(v.getByLabelText('重新作答'));expect(v.getByLabelText('B. Beta').props.accessibilityState.disabled).toBe(false);
});
it('discards a late prior account response',async()=>{
 let finish!:(x:ExamPractice)=>void;(fetchExamPractice as jest.Mock).mockImplementationOnce(()=>new Promise(r=>finish=r));const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>expect(fetchExamPractice).toHaveBeenCalledWith(7,day));v.rerender(<ServerExamPractice owner={8} day={day}/>);await waitFor(()=>v.getByText('A new server question'));
 await act(async()=>finish({...initial(),questions:[{...initial().questions[0],prompt:'Other account private question'}]}));expect(v.queryByText('Other account private question')).toBeNull();expect(fetchExamPractice).toHaveBeenLastCalledWith(8,day);
});
it('does not poll over a selected answer and hides private content in background',async()=>{
 jest.useFakeTimers();const v=render(<ServerExamPractice owner={7} day={day}/>);await act(async()=>{});fireEvent.press(v.getByLabelText('A. Alpha'));const calls=(fetchExamPractice as jest.Mock).mock.calls.length;
 await act(async()=>{jest.advanceTimersByTime(31000);});expect(fetchExamPractice).toHaveBeenCalledTimes(calls);expect(v.getByLabelText('A. Alpha').props.accessibilityState.checked).toBe(true);
 act(()=>listener('background'));expect(v.queryByText('A new server question')).toBeNull();act(()=>listener('active'));expect(v.getByLabelText('A. Alpha').props.accessibilityState.checked).toBe(true);
});
it('shows service failure without falling back to static questions and prevents backdated submission',async()=>{
 (fetchExamPractice as jest.Mock).mockRejectedValueOnce(Error('offline'));const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('练习暂不可用，请重试读取。'));expect(v.queryByText('A new server question')).toBeNull();v.unmount();
 model={...initial(),day:'2026-10-27'};const old=render(<ServerExamPractice owner={7} day="2026-10-27"/>);await waitFor(()=>old.getByText('历史日期仅供回看，请切回今天作答。'));expect(old.getByLabelText('A. Alpha').props.accessibilityState.disabled).toBe(true);
});

it('restores an unconfirmed request after remount and reuses its original id',async()=>{
 const pending={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};
 (readPendingExamAttempt as jest.Mock).mockResolvedValueOnce(pending);(submitExamAttempt as jest.Mock).mockResolvedValue(attempt());
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByLabelText('重试保存'));expect(v.getByLabelText('A. Alpha').props.accessibilityState.checked).toBe(true);fireEvent.press(v.getByLabelText('重试保存'));await waitFor(()=>v.getByText('作答已保存'));expect(writePendingExamAttempt).toHaveBeenCalledWith(7,pending);expect(submitExamAttempt).toHaveBeenCalledWith(7,pending);
});
it('ignores an in-flight refresh once an answer has been selected',async()=>{
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('A new server question'));
 let finish!:(x:ExamPractice)=>void;(fetchExamPractice as jest.Mock).mockImplementationOnce(()=>new Promise(r=>finish=r));fireEvent.press(v.getByLabelText('同步进度'));fireEvent.press(v.getByLabelText('A. Alpha'));
 await act(async()=>finish({...initial(),queue:['e2']}));expect(v.getByText('A new server question')).toBeTruthy();expect(v.getByLabelText('A. Alpha').props.accessibilityState.checked).toBe(true);
});

it('keeps an old-version pending request intact instead of showing new-version options',async()=>{
 const pending={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};
 (readPendingExamAttempt as jest.Mock).mockResolvedValueOnce(pending);model.questions[0].version=2;(submitExamAttempt as jest.Mock).mockResolvedValue(attempt());
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('题目版本已变化。此前答案与请求标识仍保留，请先重试确认原提交。'));expect(v.queryByLabelText('B. Beta')).toBeNull();fireEvent.press(v.getByLabelText('重试保存'));await waitFor(()=>expect(submitExamAttempt).toHaveBeenCalledWith(7,pending));await waitFor(()=>v.getByText('作答已保存'));expect(v.getByLabelText('A. Alpha')).toBeTruthy();
});

it('requires explicit confirmation to abandon only the local pending request, then reads history',async()=>{
 const pending={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};(readPendingExamAttempt as jest.Mock).mockResolvedValueOnce(pending);
 const alert=jest.spyOn(Alert,'alert');const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByLabelText('放弃本机待确认提交'));fireEvent.press(v.getByLabelText('放弃本机待确认提交'));expect(alert.mock.calls[0][1]).toContain('可能已经保存');expect(submitExamAttempt).not.toHaveBeenCalled();
 await act(async()=>{alert.mock.calls[0][2]![1].onPress!();});await waitFor(()=>v.getByText('已放弃本机待确认请求，服务器记录未删除。请核对答题历史后再作答。'));expect(submitExamAttempt).not.toHaveBeenCalled();expect(v.queryByLabelText('提交答案')).toBeNull();
});

it('keeps receipt recovery available when the server already includes the pending answer',async()=>{
 const pending={request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12};(readPendingExamAttempt as jest.Mock).mockResolvedValueOnce(pending);
 model.progress=[{question_id:'e1',attempt_count:1,latest_correct:false,ever_wrong:true,last_date:day,next_review_date:day}];
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByLabelText('重试保存'));expect(v.queryByLabelText('重新作答')).toBeNull();expect(v.getByLabelText('A. Alpha').props.accessibilityState.disabled).toBe(true);
});

it('shows the historical question snapshot instead of pairing old answers with new options',async()=>{
 model.questions[0]={...model.questions[0],version:2,prompt:'Current revised prompt',options:['New A','New B']};model.progress=[{question_id:'e1',attempt_count:1,latest_correct:false,ever_wrong:true,last_date:day,next_review_date:day}];
 (fetchExamAttempts as jest.Mock).mockResolvedValue({items:[attempt()],total:1});const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('题目版本 1 · 当次原题：A new server question'));expect(v.getByText('Current revised prompt')).toBeTruthy();fireEvent.press(v.getByLabelText('查看当次选项'));expect(v.getByText('A. Alpha')).toBeTruthy();expect(v.getByText('B. Beta')).toBeTruthy();
});
it.each(['2026-10-27','2026-10-29'])('shows the actual receipt study date %s when it differs from the selected date',async studyDate=>{
 if(studyDate<day)(readPendingExamAttempt as jest.Mock).mockResolvedValueOnce({request_id:'7d3fca50-1968-4c27-804c-ae508d33017d',question_id:'e1',question_version:1,choice_index:0,elapsed_seconds:12});
 (submitExamAttempt as jest.Mock).mockResolvedValue({...attempt(),study_date:studyDate});
 const v=render(<ServerExamPractice owner={7} day={day}/>);await waitFor(()=>v.getByText('A new server question'));
 if(studyDate<day)fireEvent.press(v.getByLabelText('重试保存'));
 else{fireEvent.press(v.getByLabelText('A. Alpha'));fireEvent.press(v.getByLabelText('提交答案'));}
 await waitFor(()=>v.getByText(`已记入 ${studyDate}`));expect(v.getByText(`当前查看 ${day}；本次记录以服务器保存日期为准。`)).toBeTruthy();
});
it('waits for pending hydration before foreground refresh can expose questions',async()=>{
 let hydrate!:(value:null)=>void;(readPendingExamAttempt as jest.Mock).mockImplementationOnce(()=>new Promise(resolve=>hydrate=resolve));
 const v=render(<ServerExamPractice owner={7} day={day}/>);
 await act(async()=>{listener('background');listener('active');});
 expect(fetchExamPractice).not.toHaveBeenCalled();expect(v.queryByText('A new server question')).toBeNull();expect(v.queryByLabelText('提交答案')).toBeNull();
 await act(async()=>hydrate(null));await waitFor(()=>v.getByText('A new server question'));expect(fetchExamPractice).toHaveBeenCalledTimes(1);
 fireEvent.press(v.getByLabelText('A. Alpha'));await act(async()=>{listener('background');listener('active');});expect(fetchExamPractice).toHaveBeenCalledTimes(1);expect(v.getByLabelText('A. Alpha').props.accessibilityState.checked).toBe(true);
});
it('shows the sanitized original management-paper crop',async()=>{
 model={...initial(),questions:[{...initial().questions[0],id:'real-2024-199-001',subject:'数学',paper_year:2024,paper_subject:'199',question_number:1,image_path:'/exam-papers/2024/199/q01.webp'}],queue:['real-2024-199-001']};
 const v=render(<ServerExamPractice owner={7} day={day} initialSubject="数学"/>);
 await waitFor(()=>v.getByText('A new server question'));
 const image=v.getByLabelText('2024 年管综第 1 题原卷裁图');
 expect(image.props.source.uri).toBe('https://health.executor.life/exam-papers/2024/199/q01.webp');
});
