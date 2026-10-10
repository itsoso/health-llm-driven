import { describe, expect, it } from 'vitest';
import { blankData, ensureWeek, reviewDraft, applyReviewDraft, focusStart, focusPause, focusResume, focusAdvance, parseBackup } from './model';
import { weekNumber, weekDayLabel } from './model';
describe('calendar navigation at year boundaries', () => {
    it('uses ISO week numbers for dates that belong to the adjacent week year', () => {
        expect(weekNumber('2021-01-01')).toBe(53);
        expect(weekNumber('2024-12-30')).toBe(1);
        expect(weekNumber('2026-10-10')).toBe(41);
        expect(weekDayLabel('2026-10-11')).toBe('周日');
        expect(weekDayLabel('2026-10-12')).toBe('周一');
    });
});
describe('Life navigation deterministic semantics', () => {
    it('uses the same task object in day, week and slot views', () => {
        const data = ensureWeek(blankData(), '2026-10-05');
        data.weeks['2026-10-05'].tasks.push({ id: '00000000-0000-4000-8000-000000000001', date: '2026-10-09', role: 'main', track_id: 'main', slot: 'morning', title: 'Test task', criterion: 'Test criterion', estimated_minutes: 20, actual_minutes: null, status: 'planned', result: '', root_cause: '', improvement: '' });
        const task = data.weeks['2026-10-05'].tasks[0];
        task.status = 'done';
        expect(data.weeks['2026-10-05'].tasks.filter(t => t.slot === 'morning')[0].status).toBe('done');
    });
    it('generates only from actual records and preserves manual review fields', () => {
        const week = ensureWeek(blankData(), '2026-10-05').weeks['2026-10-05'];
        week.review.summary = 'My manual summary';
        week.notes['2026-10-09'] = { valuable: 'Observed value', beautiful: '', mistake: '', learning: 'Observed learning' };
        const draft = reviewDraft(week);
        expect(draft.learning).toContain('Observed learning');
        const merged = applyReviewDraft(week.review, draft);
        expect(merged.summary).toBe('My manual summary');
        expect(merged.learning).toContain('Observed learning');
        expect(reviewDraft(ensureWeek(blankData(), '2026-10-05').weeks['2026-10-05']).summary).toContain('尚无');
    });
    it('keeps timer deadlines across reload, pause/resume, and never completes a task', () => {
        const focus = focusStart(blankData().focus, '00000000-0000-4000-8000-000000000001', 1000);
        expect(focus.deadline).toBe(new Date(1501000).toISOString());
        const paused = focusPause(focus, 11000);
        expect(paused.remaining_seconds).toBe(1490);
        expect(focusResume(paused, 21000).deadline).toBe(new Date(1511000).toISOString());
        const ended = focusAdvance(focus, 1501001);
        expect(ended.phase).toBe('rest');
        expect(ended.task_id).toBe(focus.task_id);
        expect(Object.keys(ended)).not.toContain('status');
    });
    it('rejects invalid or health-bearing backups before importing', () => {
        expect(() => parseBackup('{bad')).toThrow();
        const backup = { schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 1, data: blankData(), updated_at: '2026-10-09T00:00:00Z' }, history: [] };
        expect(parseBackup(JSON.stringify(backup)).workspace.revision).toBe(1);
        expect(() => parseBackup(JSON.stringify({ ...backup, workspace: { ...backup.workspace, data: { ...blankData(), health: { action_ref: 'secret' } } } }))).toThrow();
    });
});
describe('Life navigation record boundaries', () => {
    it('limits main and auxiliary task views to the same existing records', () => {
        const data = ensureWeek(blankData(), '2026-10-05');
        const w = data.weeks['2026-10-05'];
        w.review = { summary: 'Authored summary', gap: 'Authored cause', learning: 'Authored lesson', next_week: 'Authored plan' };
        expect(applyReviewDraft(w.review, reviewDraft(w))).toEqual(w.review);
    });
    it('does not advance missed background rounds into fictitious completed work', () => {
        const focus = focusStart(blankData().focus, null, 0);
        const next = focusAdvance(focus, 86400000);
        expect(next.current_round).toBe(1);
        expect(next.phase).toBe('rest');
        expect(Date.parse(next.deadline!)).toBe(86700000);
    });
});
describe('Backup round trip bounds', () => {
    it('accepts a valid exported backup above 256 KiB when each workspace fits the bound', () => {
        const data = ensureWeek(blankData(), '2026-10-05');
        data.weeks['2026-10-05'].archives = Array.from({ length: 10 }, (_, i) => ({ id: `00000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`, created_at: '2026-10-09T00:00:00Z', title: '', body: 'x'.repeat(20000), source_revision: 1 }));
        const backup = { schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 2, data, updated_at: '2026-10-10T00:00:00Z' }, history: [{ revision: 1, data, updated_at: '2026-10-09T00:00:00Z' }] };
        const text = JSON.stringify(backup);
        expect(text.length).toBeGreaterThan(256 * 1024);
        expect(parseBackup(text).history).toHaveLength(1);
    });
    it('rejects backup blobs above 6 MiB and unsupported timer parameters', () => {
        expect(() => parseBackup(' '.repeat(6 * 1024 * 1024 + 1))).toThrow('备份过大');
        const data = blankData();
        data.focus.focus_minutes = 181;
        expect(() => parseBackup(JSON.stringify({ schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 1, data, updated_at: '2026-10-09T00:00:00Z' }, history: [] }))).toThrow('计时参数无效');
    });
});
