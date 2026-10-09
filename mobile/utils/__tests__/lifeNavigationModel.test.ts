import { blankData, blankWeek, blankTask, parseBackup, focusStart, focusAdvance, reviewDraft, applyReviewDraft, utf8Size } from '../lifeNavigationModel';
const backup = (): import('../../types/lifeNavigation').LifeBackup => ({ schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 0, data: blankData(), updated_at: null }, history: [] });
it('rejects health references and invalid calendar dates before preview', () => {
    const b = backup();
    b.workspace.data.weeks['2026-10-05'] = blankWeek();
    (b.workspace.data.weeks['2026-10-05'] as any).health_record_id = 9;
    expect(() => parseBackup(JSON.stringify(b))).toThrow();
    delete (b.workspace.data.weeks['2026-10-05'] as any).health_record_id;
    b.workspace.data.weeks['2026-10-05'].tasks.push(blankTask('2026-10-12', 'main'));
    expect(() => parseBackup(JSON.stringify(b))).toThrow();
});
it('bounds multibyte backup input without depending on browser TextEncoder', () => {
    expect(utf8Size('中文😀')).toBe(10);
    expect(() => parseBackup('中'.repeat(2 * 1024 * 1024 + 1))).toThrow('备份过大');
    const b = backup();
    b.workspace.data.strategy.vision = 'x'.repeat(4001);
    expect(() => parseBackup(JSON.stringify(b))).toThrow('文本字段');
});
it('rejects duplicate task IDs, missing focus references and invalid history order', () => {
    const b = backup();
    const week = blankWeek();
    b.workspace.data.weeks['2026-10-05'] = week;
    const task = blankTask('2026-10-05', 'main');
    week.tasks = [task, { ...task }];
    expect(() => parseBackup(JSON.stringify(b))).toThrow();
    week.tasks = [task];
    b.workspace.data.focus.task_id = '11111111-1111-4111-8111-111111111111';
    expect(() => parseBackup(JSON.stringify(b))).toThrow();
    b.workspace.data.focus.task_id = null;
    b.workspace.revision = 2;
    b.workspace.updated_at = '2026-10-10T00:00:00Z';
    (b.history as any) = [{ revision: 2, data: blankData(), updated_at: '2026-10-10T00:00:00Z' }, { revision: 1, data: blankData(), updated_at: '2026-10-10T00:00:00Z' }];
    expect(() => parseBackup(JSON.stringify(b))).toThrow();
});
it('advances a background timer once without claiming task completion', () => {
    const data = blankData(), task = blankTask('2026-10-05', 'main');
    data.focus = focusStart(data.focus, task.id, 0);
    const next = focusAdvance(data.focus, 86400000);
    expect(next.phase).toBe('rest');
    expect(next.current_round).toBe(1);
    expect(task.status).toBe('planned');
});
it('only fills empty review fields from recorded evidence', () => {
    const week = blankWeek();
    const generated = reviewDraft(week);
    expect(generated.summary).toContain('不能生成执行结论');
    expect(applyReviewDraft({ ...week.review, summary: '自己的复盘' }, generated).summary).toBe('自己的复盘');
    expect(parseBackup(JSON.stringify(backup())).workspace.revision).toBe(0);
});
