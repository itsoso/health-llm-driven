import type { LifeData, LifeWeek, LifeReview, LifeFocus, LifeBackup, LifeTask, TrackId } from '@/services/lifeNavigation';
export const tracks: Array<{
    id: TrackId;
    label: string;
}> = [{ id: 'main', label: '主线' }, { id: 'aux1', label: '辅助一' }, { id: 'aux2', label: '辅助二' }, { id: 'important', label: '重要事项' }, { id: 'misc', label: '其他事项' }];
export const slotLabels = { morning: '上午', afternoon: '下午', evening: '晚上', flexible: '灵活' } as const;
export const statusLabels = { planned: '未开始', doing: '进行中', done: '已完成', skipped: '已跳过' } as const;
export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function copy<T>(value: T): T { return JSON.parse(JSON.stringify(value)); }
export function blankData(): LifeData { return { strategy: { vision: '', annual_goal: '', primary_question: '' }, quarters: {}, weeks: {}, opportunities: [], focus: { phase: 'idle', focus_minutes: 25, rest_minutes: 5, rounds: 4, current_round: 1, deadline: null, remaining_seconds: null, paused_phase: null, task_id: null } }; }
export function blankWeek(): LifeWeek { return { tracks: tracks.map(t => ({ id: t.id, title: '', criterion: '', strategy_link: '', next_step: '' })), tasks: [], notes: {}, review: { summary: '', gap: '', learning: '', next_week: '' }, archives: [] }; }
export function ensureWeek(data: LifeData, monday: string): LifeData { const next = copy(data); next.weeks[monday] ??= blankWeek(); return next; }
export function localDate(now = new Date()): string { return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`; }
export function addDays(date: string, amount: number): string { const d = new Date(`${date}T12:00:00`); d.setDate(d.getDate() + amount); return localDate(d); }
export function mondayOf(date: string): string { const day = new Date(`${date}T12:00:00`).getDay(); return addDays(date, -(day === 0 ? 6 : day - 1)); }
export function blankTask(date: string, role: LifeTask['role']): LifeTask { return { id: newId(), date, role, track_id: role === 'main' ? 'main' : role === 'auxiliary' ? 'aux1' : 'misc', slot: 'flexible', title: '', criterion: '', estimated_minutes: null, actual_minutes: null, status: 'planned', result: '', root_cause: '', improvement: '' }; }
export function reviewDraft(week: LifeWeek): LifeReview {
    const tasks = week.tasks.filter(t => t.title.trim());
    const notes = Object.entries(week.notes).filter(([, n]) => Object.values(n).some(v => v.trim()));
    return {
        summary: tasks.length || notes.length ? `已记录 ${tasks.length} 项任务，其中完成 ${tasks.filter(t => t.status === 'done').length} 项；日记录 ${notes.length} 天。\n${tasks.filter(t => t.result.trim()).map(t => `${t.title}：${t.result}`).join('\n')}` : '尚无实际任务或日记录，不能生成执行结论。',
        gap: tasks.filter(t => t.root_cause.trim()).map(t => `${t.title}：${t.root_cause}`).join('\n'),
        learning: notes.filter(([, n]) => n.learning.trim()).map(([date, n]) => `${date}：${n.learning}`).join('\n'),
        next_week: tasks.filter(t => t.improvement.trim()).map(t => `${t.title}：${t.improvement}`).join('\n'),
    };
}
export function applyReviewDraft(manual: LifeReview, generated: LifeReview): LifeReview { return Object.fromEntries(Object.keys(manual).map(key => [key, manual[key as keyof LifeReview].trim() ? manual[key as keyof LifeReview] : generated[key as keyof LifeReview]])) as unknown as LifeReview; }
export function focusStart(focus: LifeFocus, taskId: string | null, now: number): LifeFocus { return { ...focus, phase: 'focus', current_round: 1, deadline: new Date(now + focus.focus_minutes * 60000).toISOString(), remaining_seconds: null, paused_phase: null, task_id: taskId }; }
export function focusPause(focus: LifeFocus, now: number): LifeFocus { if (focus.phase !== 'focus' && focus.phase !== 'rest')
    return focus; return { ...focus, phase: 'paused', paused_phase: focus.phase, remaining_seconds: Math.max(0, Math.ceil((Date.parse(focus.deadline ?? '') - now) / 1000)), deadline: null }; }
export function focusResume(focus: LifeFocus, now: number): LifeFocus { if (focus.phase !== 'paused')
    return focus; return { ...focus, phase: focus.paused_phase ?? 'focus', deadline: new Date(now + (focus.remaining_seconds ?? 0) * 1000).toISOString(), remaining_seconds: null, paused_phase: null }; }
export function focusEnd(focus: LifeFocus): LifeFocus { return { ...focus, phase: 'idle', current_round: 1, deadline: null, remaining_seconds: null, paused_phase: null, task_id: null }; }
export function focusAdvance(focus: LifeFocus, now: number): LifeFocus {
    if (!focus.deadline || (focus.phase !== 'focus' && focus.phase !== 'rest') || Date.parse(focus.deadline) > now)
        return focus;
    // Backgrounding never fabricates multiple rounds of completed work.
    if (focus.phase === 'focus' && focus.current_round >= focus.rounds)
        return focusEnd(focus);
    const phase = focus.phase === 'focus' ? 'rest' : 'focus';
    return { ...focus, phase, current_round: phase === 'focus' ? focus.current_round + 1 : focus.current_round, deadline: new Date(now + (phase === 'focus' ? focus.focus_minutes : focus.rest_minutes) * 60000).toISOString() };
}
function object(value: unknown): Record<string, unknown> { if (!value || typeof value !== 'object' || Array.isArray(value))
    throw Error('格式无效'); return value as Record<string, unknown>; }
function keys(value: unknown, allowed: string[]): Record<string, unknown> { const item = object(value); if (Object.keys(item).some(k => !allowed.includes(k)))
    throw Error('备份含不支持或健康引用字段'); return item; }
function texts(value: unknown, allowed: string[]): void { const item = keys(value, allowed); if (allowed.some(k => typeof item[k] !== 'string' || (item[k] as string).length > 4000))
    throw Error('文本字段无效'); }
export function validateData(value: unknown): void {
    const d = keys(value, ['strategy', 'quarters', 'weeks', 'opportunities', 'focus']);
    if (new TextEncoder().encode(JSON.stringify(d)).length > 256 * 1024)
        throw Error('工作区正文超过 256 KiB');
    if (Object.keys(object(d.quarters)).length > 100 || Object.keys(object(d.weeks)).length > 200)
        throw Error('工作区记录过多');
    texts(d.strategy, ['vision', 'annual_goal', 'primary_question']);
    for (const [quarter, q] of Object.entries(object(d.quarters))) {
        if (!/^\d{4}-Q[1-4]$/.test(quarter))
            throw Error('季度无效');
        texts(q, ['review', 'strategy', 'decomposition', 'plan', 'risk']);
    }
    for (const [date, rawWeek] of Object.entries(object(d.weeks))) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || mondayOf(date) !== date)
            throw Error('周日期无效');
        const w = keys(rawWeek, ['tracks', 'tasks', 'notes', 'review', 'archives']);
        if (!Array.isArray(w.tracks) || !Array.isArray(w.tasks) || !Array.isArray(w.archives) || w.tasks.length > 100 || w.tracks.length > 5 || w.archives.length > 20)
            throw Error('任务字段无效');
        for (const t of w.tracks) {
            const v = keys(t, ['id', 'title', 'criterion', 'strategy_link', 'next_step']);
            if (!tracks.some(t => t.id === v.id))
                throw Error('主线无效');
            for (const k of ['title', 'criterion', 'strategy_link', 'next_step'])
                if (typeof v[k] !== 'string')
                    throw Error('主线文本无效');
        }
        for (const t of w.tasks) {
            const v = keys(t, ['id', 'date', 'role', 'track_id', 'slot', 'title', 'criterion', 'estimated_minutes', 'actual_minutes', 'status', 'result', 'root_cause', 'improvement']);
            if (typeof v.id !== 'string' || typeof v.date !== 'string' || !['main', 'auxiliary', 'other'].includes(String(v.role)) || !tracks.some(t => t.id === v.track_id) || !Object.keys(slotLabels).includes(String(v.slot)) || !Object.keys(statusLabels).includes(String(v.status)))
                throw Error('任务内容无效');
            for (const k of ['title', 'criterion', 'result', 'root_cause', 'improvement'])
                if (typeof v[k] !== 'string')
                    throw Error('任务文本无效');
            for (const k of ['estimated_minutes', 'actual_minutes'])
                if (v[k] !== null && (!Number.isInteger(v[k]) || Number(v[k]) < 0 || Number(v[k]) > 1440))
                    throw Error('分钟值无效');
        }
        texts(w.review, ['summary', 'gap', 'learning', 'next_week']);
        for (const [date, n] of Object.entries(object(w.notes))) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(date))
                throw Error('日记录日期无效');
            texts(n, ['valuable', 'beautiful', 'mistake', 'learning']);
        }
        for (const a of w.archives) {
            const v = keys(a, ['id', 'created_at', 'title', 'body', 'source_revision']);
            if (typeof v.id !== 'string' || typeof v.created_at !== 'string' || typeof v.title !== 'string' || v.title.length > 200 || typeof v.body !== 'string' || v.body.length > 20000 || !Number.isInteger(v.source_revision))
                throw Error('成果无效');
        }
    }
    if (!Array.isArray(d.opportunities) || d.opportunities.length > 100)
        throw Error('机会字段无效');
    for (const o of d.opportunities) {
        const v = keys(o, ['id', 'category', 'insight', 'evidence', 'personal_fit', 'assumption', 'next_step', 'success_criteria', 'risk_limit', 'review_date', 'result', 'evidence_level', 'fit']);
        if (!['macro', 'industry', 'people', 'customer'].includes(String(v.category)) || !['unknown', 'hypothesis', 'signal', 'supported'].includes(String(v.evidence_level)) || !['unknown', 'low', 'medium', 'high'].includes(String(v.fit)))
            throw Error('机会内容无效');
        for (const k of ['id', 'insight', 'evidence', 'personal_fit', 'assumption', 'next_step', 'success_criteria', 'risk_limit', 'result'])
            if (typeof v[k] !== 'string')
                throw Error('机会文本无效');
        if (v.review_date !== null && (typeof v.review_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v.review_date)))
            throw Error('机会日期无效');
    }
    const f = keys(d.focus, ['phase', 'focus_minutes', 'rest_minutes', 'rounds', 'current_round', 'deadline', 'remaining_seconds', 'paused_phase', 'task_id']);
    if (!['idle', 'focus', 'rest', 'paused'].includes(String(f.phase)))
        throw Error('计时状态无效');
    for (const [k, max] of [['focus_minutes', 180], ['rest_minutes', 60], ['rounds', 12], ['current_round', 12]] as const)
        if (!Number.isInteger(f[k]) || Number(f[k]) < 1 || Number(f[k]) > max)
            throw Error('计时参数无效');
    if (Number(f.current_round) > Number(f.rounds))
        throw Error('计时轮数无效');
    if (f.deadline !== null && (typeof f.deadline !== 'string' || !Number.isFinite(Date.parse(f.deadline))))
        throw Error('计时截止时间无效');
    if (f.remaining_seconds !== null && (!Number.isInteger(f.remaining_seconds) || Number(f.remaining_seconds) < 0 || Number(f.remaining_seconds) > 10800))
        throw Error('暂停计时无效');
    if (f.paused_phase !== null && !['focus', 'rest'].includes(String(f.paused_phase)))
        throw Error('暂停阶段无效');
    if (f.task_id !== null && typeof f.task_id !== 'string')
        throw Error('任务引用无效');
    if (['focus', 'rest'].includes(String(f.phase)) && (f.deadline === null || f.remaining_seconds !== null || f.paused_phase !== null))
        throw Error('活动计时状态无效');
    if (f.phase === 'paused' && (f.deadline !== null || f.remaining_seconds === null || f.paused_phase === null))
        throw Error('暂停计时状态无效');
    if (f.phase === 'idle' && (f.deadline !== null || f.remaining_seconds !== null || f.paused_phase !== null))
        throw Error('空闲计时状态无效');
}
export function parseBackup(text: string): LifeBackup {
    if (new TextEncoder().encode(text).length > 6 * 1024 * 1024)
        throw Error('备份过大');
    const b = keys(JSON.parse(text), ['schema_version', 'workspace', 'history']);
    if (b.schema_version !== 'life_navigation.backup.v1' || !Array.isArray(b.history) || b.history.length > 20)
        throw Error('备份版本无效');
    const w = keys(b.workspace, ['schema_version', 'revision', 'data', 'updated_at']);
    if (w.schema_version !== 'life_navigation.v1' || !Number.isInteger(w.revision) || Number(w.revision) < 0 || w.updated_at !== null && typeof w.updated_at !== 'string')
        throw Error('工作区版本无效');
    validateData(w.data);
    for (const raw of b.history) {
        const h = keys(raw, ['revision', 'data', 'updated_at']);
        if (!Number.isInteger(h.revision) || typeof h.updated_at !== 'string')
            throw Error('历史版本无效');
        validateData(h.data);
    }
    return b as unknown as LifeBackup;
}
