import { blankData } from '../lifeNavigationModel';
import { questions, recordAnswer } from '../examStudy';
import { practiceQuestions } from '../examHistory';

it('keeps the native and Web history filter implementation identical',()=>{
 const fs=require('fs');const path=require('path');const root=path.resolve(__dirname,'../../..');
 const body=(file:string)=>fs.readFileSync(path.join(root,file),'utf8').split('\n').slice(1).join('\n');
 expect(body('mobile/utils/examHistory.ts')).toBe(body('frontend/src/components/life-navigation/examHistory.ts'));
});
it('distinguishes outstanding mistakes, corrected mistakes and saved correct answers without a write',()=>{
 const data=blankData();const [correct,corrected,pending]=questions;
 recordAnswer(data,'2026-10-26',correct,correct.answer);
 recordAnswer(data,'2026-10-26',corrected,(corrected.answer+1)%4);
 recordAnswer(data,'2026-10-26',corrected,corrected.answer);
 recordAnswer(data,'2026-10-26',pending,(pending.answer+1)%4);
 const before=JSON.stringify(data);
 expect(practiceQuestions(data,'2026-10-27','英语','history').map(q=>q.id)).toEqual([correct.id,corrected.id,pending.id]);
 expect(practiceQuestions(data,'2026-10-27','英语','mistakes').map(q=>q.id)).toEqual([corrected.id,pending.id]);
 expect(practiceQuestions(data,'2026-10-27','英语','wrong').map(q=>q.id)).toEqual([pending.id]);
 expect(practiceQuestions(data,'2026-10-27','数学','history')).toEqual([]);
 expect(JSON.stringify(data)).toBe(before);
});
it('does not show future saved answers when viewing an earlier study date',()=>{
 const data=blankData();recordAnswer(data,'2026-10-28',questions[0],0);
 expect(practiceQuestions(data,'2026-10-27','英语','history')).toEqual([]);
 expect(practiceQuestions(data,'2026-10-27','英语','mistakes')).toEqual([]);
 expect(practiceQuestions(data,'2026-10-28','英语','mistakes')).toEqual([questions[0]]);
});
