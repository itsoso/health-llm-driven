import React, { useState } from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import ExamStudyPanel from '../ExamStudyPanel';
import { blankData, copy } from '../../../utils/lifeNavigationModel';
import { questions, recordAnswer } from '../../../utils/examStudy';
import type { LifeData } from '../../../services/lifeNavigation';

function Harness({initial=blankData()}: {initial?:LifeData}) {
 const [data,setData]=useState(initial);
 const [persisted,setPersisted]=useState(initial);
 return <ExamStudyPanel data={data} persistedData={persisted} day="2026-10-26" disabled={false} focus={jest.fn()} saveAnswer={async fn=>{const next=copy(data);fn(next);setData(next);setPersisted(next);}} edit={fn=>setData(prev=>{const next=copy(prev);fn(next);return next;})}/>;
}
it('resumes progress and retains answer feedback before advancing',async()=>{
 const data=blankData();recordAnswer(data,'2026-10-25',questions[0],questions[0].answer);
 const view=render(<Harness initial={data}/>);
 fireEvent.press(view.getByLabelText('练习与错题'));
 expect(view.getByText(questions[1].prompt)).toBeTruthy();
 fireEvent.press(view.getByLabelText('C. Less commuting does not guarantee higher productivity.'));
 fireEvent.press(view.getByLabelText('核对答案并记录'));
 expect(view.getByText('本次答对')).toBeTruthy();
 expect(view.getByText(questions[1].explanation)).toBeTruthy();
 await waitFor(()=>view.getByText('作答已保存，可刷新或继续下一题'));
 fireEvent.press(view.getByLabelText('下一题'));
 expect(view.getByText(questions[2].prompt)).toBeTruthy();
});
it('opens the scheduled subject without creating study records',()=>{
 const edit=jest.fn();const view=render(<ExamStudyPanel data={blankData()} persistedData={blankData()} day="2026-10-26" disabled={false} focus={jest.fn()} saveAnswer={async()=>{}} edit={edit}/>);
 fireEvent.press(view.getByLabelText('练习逻辑'));
 expect(view.getByText(questions.find(q=>q.id==='l01')!.prompt)).toBeTruthy();
 expect(edit).not.toHaveBeenCalled();
});
it('leaves exhausted practice empty and lets the learner explicitly view the full bank',()=>{
 const data=blankData();questions.filter(q=>q.subject==='英语').forEach(q=>recordAnswer(data,'2026-10-25',q,q.answer));
 const view=render(<Harness initial={data}/>);fireEvent.press(view.getByLabelText('练习与错题'));
 expect(view.getByText(/本科目当前没有未做题/)).toBeTruthy();
 fireEvent.press(view.getByLabelText('全部题库'));
 expect(view.getByText(questions[0].prompt)).toBeTruthy();
});

it('prioritizes a previous mistake when the first question is still unseen',()=>{
 const data=blankData();recordAnswer(data,'2026-10-25',questions[3],0);
 const view=render(<Harness initial={data}/>);fireEvent.press(view.getByLabelText('练习与错题'));
 expect(view.getByText(questions[3].prompt)).toBeTruthy();
});
