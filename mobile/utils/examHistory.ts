import type { LifeData } from '../services/lifeNavigation';
import { practiceQuestions as scheduledQuestions, questions, questionHistory, type Subject, type PracticeMode as ScheduledMode } from './examStudy';

export type PracticeMode = ScheduledMode | 'history' | 'mistakes';
export const practiceModes: {key: PracticeMode; label: string}[] = [
 {key:'next',label:'按进度练习'}, {key:'wrong',label:'待复练'},
 {key:'history',label:'答题历史'}, {key:'mistakes',label:'错题本'}, {key:'all',label:'全部题库'},
];

export function practiceQuestions(data: LifeData, day: string, subject: Subject, mode: PracticeMode) {
 if(mode!=='history'&&mode!=='mistakes')return scheduledQuestions(data,day,subject,mode);
 return questions.filter(question=>{
  if(question.subject!==subject)return false;
  const records=questionHistory(data,question,day);
  if(mode==='history')return records.length>0;
  return records.some(record=>record.status==='doing'||[record.result,record.improvement].some(result=>{
   const answer=/作答：([A-D])；正确答案：([A-D])/.exec(result);
   return answer!==null&&answer[1]!==answer[2];
  }));
 });
}
