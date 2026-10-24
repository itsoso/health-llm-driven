import { describe, it, expect } from 'vitest';
import { blankData, mondayOf } from './model';
import { dailyStudy, addStudyDay, recordAnswer, wrongQuestions, studyId, questions, phaseFor } from './examStudy';
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
  while(w.tasks.length<99)w.tasks.push({...w.tasks[0],id:crypto.randomUUID()});
  expect(()=>addStudyDay(d,'2026-10-25')).toThrow('100');expect(w.tasks).toHaveLength(99);
 });
});
