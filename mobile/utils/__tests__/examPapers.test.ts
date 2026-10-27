import { paperAssignment, examPapers } from '../examPapers';
import { dailyStudy, addStudyDay, studyId } from '../examStudy';
import { blankData, mondayOf } from '../lifeNavigationModel';
describe('dated two-hour real-paper practice', () => {
 it('provides six sourced papers', () => {
  expect(examPapers.map(p=>p.id)).toEqual(['2024-199','2024-204','2025-199','2025-204','2026-199','2026-204']);
  expect(examPapers.find(p=>p.id==='2026-204')?.source).toContain('第三方');
 });
 it('changes assigned sections by date and labels repeated passes as review', () => {
  expect(paperAssignment('2026-10-27')?.english).not.toBe(paperAssignment('2026-10-28')?.english);
  expect(paperAssignment('2026-10-27')?.year).toBe(2024);
  expect(paperAssignment('2026-11-30')?.year).toBe(2026);
  expect(paperAssignment('2026-11-05')?.review).toBe(true);
  expect(paperAssignment('2026-12-19')).toBeNull();
 });
 it('preserves historical allocation, assigns two hours, and retains ledger data', () => {
  expect(dailyStudy('2026-10-26').reduce((n,t)=>n+t.minutes,0)).toBe(60);
  expect(dailyStudy('2026-10-27').reduce((n,t)=>n+t.minutes,0)).toBe(120);
  expect(studyId('2026-10-24','e01')).toBe('e6ba2027-2026-4102-8400-000000000004');
  const d=blankData();addStudyDay(d,'2026-10-27');const w=d.weeks[mondayOf('2026-10-27')];w.tasks[0].result='保留复盘';
  addStudyDay(d,'2026-10-27');expect(w.tasks).toHaveLength(4);expect(w.tasks[0].result).toBe('保留复盘');
 });
});

it('uses the same paper catalog and date assignments on both clients', () => {
 const fs=require('fs'),path=require('path'),root=path.resolve(__dirname,'../../..');
 expect(fs.readFileSync(path.join(root,'mobile/utils/examPapers.ts'),'utf8')).toBe(fs.readFileSync(path.join(root,'frontend/src/components/life-navigation/examPapers.ts'),'utf8'));
});

it('does not inherit completion from a previously saved same-day warmup plan', () => {
 const d=blankData();addStudyDay(d,'2026-10-26');
 const w=d.weeks[mondayOf('2026-10-27')];
 for(const task of w.tasks){task.date='2026-10-27';task.id=studyId('2026-10-27',task.title.includes('英语')?'english':task.title.includes('错题')?'review':'comprehensive');task.status='done';task.result='旧任务结果';}
 const old=JSON.stringify(w.tasks);addStudyDay(d,'2026-10-27');
 expect(JSON.stringify(w.tasks.slice(0,3))).toBe(old);expect(w.tasks).toHaveLength(7);
 expect(w.tasks.slice(3).every(t=>t.status==='planned'&&t.result==='')).toBe(true);
 expect(w.tasks.slice(3).reduce((n,t)=>n+(t.estimated_minutes??0),0)).toBe(120);
 expect(paperAssignment('2026-10-29')?.writing).toContain('再练与扩写');
});
