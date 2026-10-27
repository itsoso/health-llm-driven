import { blankData, validateData } from '../lifeNavigationModel';
import { questions, practiceQuestions, recordAnswer, studyId, questionHistory } from '../examStudy';

describe('expanded original practice bank', () => {
 it('contains 60 additional distinct questions with one valid keyed answer', () => {
  expect(questions.length).toBeGreaterThanOrEqual(80);
  expect(new Set(questions.map(q=>q.id)).size).toBe(questions.length);
  expect(new Set(questions.map(q=>q.prompt)).size).toBe(questions.length);
  for(const q of questions) {
   expect(q.options.length).toBe(4);
   expect(new Set(q.options).size).toBe(4);
   expect(q.options[q.answer]).toBeTruthy();
   expect(q.explanation.length).toBeGreaterThan(12);
  }
 });
 it('preserves all saved legacy identities and separates new questions', () => {
  const day='2026-10-27';
  expect(studyId(day,'e01')).toBe('e6ba2027-2026-4102-8700-000000000004');
  expect(studyId(day,'paper-review')).toBe('e6ba2027-2026-4102-8700-00000000001c');
  expect(new Set(questions.map(q=>studyId(day,q.id))).size).toBe(questions.length);
 });
 it('offers a deterministic dated batch of new questions that changes the next day', () => {
  const data=blankData();
  const today=practiceQuestions(data,'2026-10-27','英语');
  expect(today).toHaveLength(6);
  expect(today[0].id).toBe('e101');
  expect(practiceQuestions(data,'2026-10-27','英语')).toEqual(today);
  const tomorrow=practiceQuestions(data,'2026-10-28','英语');
  expect(tomorrow.map(q=>q.id)).not.toEqual(today.map(q=>q.id));
  expect(tomorrow.every(q=>!today.includes(q))).toBe(true);
 });
 it('replenishes completed questions without recycling old answers or losing mistakes', () => {
  const data=blankData();const q=practiceQuestions(data,'2026-10-27','英语')[0];
  recordAnswer(data,'2026-10-27',q,(q.answer+1)%4);
  expect(practiceQuestions(data,'2026-10-27','英语')).toHaveLength(6);
  expect(practiceQuestions(data,'2026-10-27','英语')).not.toContain(q);
  expect(practiceQuestions(data,'2026-10-28','英语')).not.toContain(q);
  expect(practiceQuestions(data,'2026-10-28','英语','wrong')).toContain(q);
  expect(questionHistory(data,q)).toHaveLength(1);
  expect(()=>validateData(data)).not.toThrow();
 });
 it('stops at exhaustion instead of inventing fresh questions', () => {
  const data=blankData();const english=questions.filter(q=>q.subject==='英语');
  for(const q of english)recordAnswer(data,'2026-10-27',q,q.answer);
  expect(practiceQuestions(data,'2026-10-28','英语')).toEqual([]);
  expect(practiceQuestions(data,'2026-10-28','英语','all')).toEqual(english);
 });
});


it('checks original mathematics answers against independently calculated results', () => {
 const expected: Record<string,string> = {
  m101:String(80*1.25*0.9-80), m102:`${(100*0.2+100*0.4)/200*100}%`,
  m103:String(240/(120/60+120/40)), m104:String((1-2*(1/12+1/6))/(1/6)),
  m105:String(25+20-40), m106:String(6*5), m107:'3/10', m108:String(1-0.2*0.2),
  m109:'2或3', m110:'−1或5', m111:String(Array.from({length:10},(_,i)=>3+2*i).reduce((a,b)=>a+b,0)),
  m112:String((6*8/2)/((6+8+Math.hypot(6,8))/2)), m113:String((4**2*3)/(2**2*6)),
  m114:'7和4', m115:String((3*2)%5), m116:String(400*5), m117:String(2*Math.sqrt(4)),
  m118:String(Math.round(100*1.1**2)), m119:String(10+Math.ceil(3.2-1)*3),
  m120:'两条件单独均不充分，联合充分',
 };
 for(const [id,value] of Object.entries(expected)) {
  const q=questions.find(q=>q.id===id)!;expect(q.options[q.answer]).toBe(value);
 }
});


it('ships identical expanded content on Web and native', () => {
 const fs=require('fs');const path=require('path');const root=path.resolve(__dirname,'../../..');
 expect(fs.readFileSync(path.join(root,'mobile/utils/examQuestionBank.ts'),'utf8')).toBe(fs.readFileSync(path.join(root,'frontend/src/components/life-navigation/examQuestionBank.ts'),'utf8'));
});
