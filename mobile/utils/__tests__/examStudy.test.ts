import { blankData, mondayOf } from '../lifeNavigationModel';
import { dailyStudy, addStudyDay, recordAnswer, wrongQuestions, studyId, questions, phaseFor, practiceQuestions } from '../examStudy';
describe('exam preparation on the private LifeNav task ledger', () => {
 it('allocates exactly one hour and never schedules after the exam', () => {
  expect(dailyStudy('2026-10-24').reduce((sum, t) => sum+t.minutes, 0)).toBe(60);
  expect(dailyStudy('2026-12-19')).toEqual([]);
  expect(dailyStudy('2026-12-20')).toEqual([]);
  expect(phaseFor('2026-12-20')).toContain('复试');
 });
 it('adds a day idempotently without replacing authored tasks or results', () => {
  const d = blankData(); addStudyDay(d, '2026-10-24');
  const tasks = d.weeks[mondayOf('2026-10-24')].tasks;
  tasks[0].result = 'My own reflection';
  addStudyDay(d, '2026-10-24');
  expect(tasks).toHaveLength(3); expect(tasks[0].result).toBe('My own reflection');
  expect(tasks.every(t=>t.role==='other')).toBe(true);
 });
 it('retains a wrong first answer and resolves the mistake only on a correct retry', () => {
  const d=blankData(); const q=questions[0]; const incorrect=(q.answer+1)%q.options.length;
  recordAnswer(d,'2026-10-24',q,incorrect);
  expect(wrongQuestions(d).map(q=>q.id)).toContain(q.id);
  recordAnswer(d,'2026-10-25',q,q.answer);
  expect(wrongQuestions(d)).toEqual([]);
  const old=d.weeks[mondayOf('2026-10-24')].tasks.find(t=>t.id===studyId('2026-10-24',q.id));
  expect(old?.status).toBe('doing');
 });
 it('keeps deterministic UUID identities distinct between days and questions', () => {
  expect(studyId('2026-10-24','english')).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/);
  expect(studyId('2026-10-24','english')).not.toBe(studyId('2026-10-25','english'));
 });
 it('rejects full weeks before adding partial plans or attempts', () => {
  const d=blankData();addStudyDay(d,'2026-10-24');const w=d.weeks[mondayOf('2026-10-24')];
  while(w.tasks.length<99)w.tasks.push({...w.tasks[0],id:'test-'+w.tasks.length});
  expect(()=>addStudyDay(d,'2026-10-25')).toThrow('100');expect(w.tasks).toHaveLength(99);
 });
});

describe('practice selection follows dated study history', () => {
 it('prioritizes earlier mistakes and skips correct answers without rewriting history', () => {
  const data=blankData();
  recordAnswer(data,'2026-10-24',questions[0],questions[0].answer);
  recordAnswer(data,'2026-10-24',questions[3],0);
  const before=JSON.stringify(data);
  const queue=practiceQuestions(data,'2026-10-26','英语');
  expect(queue[0].id).toBe('e04');
  expect(queue.map(q=>q.id)).not.toContain('e01');
  expect(queue[1].id).toBe('e02');
  expect(JSON.stringify(data)).toBe(before);
 });
 it('does not repeatedly assign mistakes from the same day but permits explicit review', () => {
  const data=blankData();recordAnswer(data,'2026-10-26',questions[0],0);
  expect(practiceQuestions(data,'2026-10-26','英语').map(q=>q.id)).not.toContain('e01');
  expect(practiceQuestions(data,'2026-10-26','英语','wrong').map(q=>q.id)).toEqual(['e01']);
  expect(practiceQuestions(data,'2026-10-27','英语')[0].id).toBe('e01');
 });
 it('uses only records on or before the selected day, including across weeks', () => {
  const data=blankData();recordAnswer(data,'2026-10-25',questions[0],0);
  recordAnswer(data,'2026-10-27',questions[0],questions[0].answer);
  expect(practiceQuestions(data,'2026-10-26','英语')[0].id).toBe('e01');
  expect(practiceQuestions(data,'2026-10-27','英语').map(q=>q.id)).not.toContain('e01');
 });
 it('does not recycle exhausted questions, while allowing access to the full bank', () => {
  const data=blankData();const english=questions.filter(q=>q.subject==='英语');
  english.forEach(q=>recordAnswer(data,'2026-10-25',q,q.answer));
  expect(practiceQuestions(data,'2026-10-26','英语')).toEqual([]);
  expect(practiceQuestions(data,'2026-10-26','英语','all')).toEqual(english);
 });
});

it('keeps persisted IDs and practice rules identical to the Web source',()=>{ const fs=require('fs'); const path=require('path'); const root=path.resolve(__dirname,'../../..'); const body=(p:string)=>fs.readFileSync(p,'utf8').split('\n').slice(2).join('\n'); expect(body(path.join(root,'mobile/utils/examStudy.ts'))).toBe(body(path.join(root,'frontend/src/components/life-navigation/examStudy.ts'))); });
