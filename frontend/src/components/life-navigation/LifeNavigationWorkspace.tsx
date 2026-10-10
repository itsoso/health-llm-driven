'use client';
/* Full-page links intentionally trigger the unsaved-draft beforeunload guard. */
/* eslint-disable @next/next/no-html-link-for-pages */
import React, { useEffect, useRef, useState } from 'react';
import { Compass, Sun, CalendarDays, Timer, BookOpen, Award, Flag, Sprout, Archive, Menu, ChevronLeft, ChevronRight, Undo2, Redo2 } from 'lucide-react';
import { useWorkspaceHistory } from './useWorkspaceHistory';
import { useAuth } from '@/contexts/AuthContext';
import { getLifeWorkspace, saveLifeWorkspace, getLifeHistory, restoreLifeWorkspace, getLifeBackup, importLifeBackup, type LifeData, type LifeWorkspace, type LifeVersion, type LifeBackup, type LifeTask, type LifeOpportunity, type LifeFocus, type LifeReview } from '@/services/lifeNavigation';
import { addDays, mondayOf, localDate, blankWeek, blankTask, copy, tracks, slotLabels, statusLabels, newId, reviewDraft, applyReviewDraft, focusStart, focusPause, focusResume, focusEnd, focusAdvance, parseBackup, weekNumber, weekDayLabel } from './model';
import css from './workspace.module.css';
type Tab = '今日' | '周计划' | '时段导航' | '周复盘' | '成果' | '方向与季度' | '机会' | '备份';
const navGroups = [
    { label: '行动与时间', items: [{ title: '今日', icon: Sun }, { title: '周计划', icon: CalendarDays }, { title: '时段导航', icon: Timer }] },
    { label: '回顾与积累', items: [{ title: '周复盘', icon: BookOpen }, { title: '成果', icon: Award }] },
    { label: '方向与管理', items: [{ title: '方向与季度', icon: Flag }, { title: '机会', icon: Sprout }, { title: '备份', icon: Archive }] },
] as const;
const viewDescriptions: Record<Tab, string> = { 今日: '把重要的事，放在今天。', 周计划: '让方向落在每一周的行动里。', 时段导航: '为行动留出专注的时间。', 周复盘: '从实际行动中，找到下一步。', 成果: '把做过的事，积累成自己的作品。', 方向与季度: '抬头看方向，低头走好这一季。', 机会: '用证据检验想法，再决定投入。', 备份: '保存自己的记录，也保留回来的路。' };
const reviewLabels: Record<keyof LifeReview, string> = { summary: '本周总结', gap: '执行差距与根因', learning: '本周学习', next_week: '下周调整' };
function message(error: unknown): string { const status = (error as {
    response?: {
        status?: number;
    };
})?.response?.status; return status === 422 ? '输入或备份未通过校验，本地草稿已保留。请核对字段与范围。' : status === 409 ? '版本冲突：本地草稿已保留，请核对最新版本后再决定如何处理。' : status === 503 ? '导航工作区暂未开放或暂时不可用，请稍后重试。' : status === 401 || status === 403 ? '当前账号或权限已变化，请重新登录并核对。' : '操作未确认成功，本地草稿保留。请检查网络后重试。'; }
function download(value: LifeBackup, suffix: string): void { const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = `life-navigation-${suffix}-${localDate()}.json`; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
export default function LifeNavigationWorkspace() {
    const { user, isAuthenticated } = useAuth();
    return user && isAuthenticated ? <SessionWorkspace key={user.id} owner={user.id}/> : <div className={css.workspace}>请登录后使用导航工作区。</div>;
}
function SessionWorkspace({ owner }: {
    owner: number;
}) {
    const [workspace, setWorkspace] = useState<LifeWorkspace | null>(null);
    const [draft, setDraft] = useState<LifeData | null>(null);
    const draftHistory = useWorkspaceHistory<LifeData>();
    const clearDraftHistory = draftHistory.clear;
    const [menuOpen, setMenuOpen] = useState(false);
    const [pendingTask, setPendingTask] = useState<string | null>(null);
    const [tab, setTab] = useState<Tab>('今日');
    const [day, setDay] = useState(localDate());
    const monday = mondayOf(day);
    const quarter = `${day.slice(0, 4)}-Q${Math.ceil(Number(day.slice(5, 7)) / 3)}`;
    const [dirty, setDirty] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [history, setHistory] = useState<LifeVersion[]>([]);
    const [preview, setPreview] = useState<LifeBackup | null>(null);
    const [now, setNow] = useState(Date.now());
    const [generated, setGenerated] = useState<LifeReview | null>(null);
    const alive = useRef(true);
    const requestEpoch = useRef(0);
    const writeLock = useRef(false);
    useEffect(() => { alive.current = true; const ctrl = new AbortController(); const epoch = ++requestEpoch.current; getLifeWorkspace(owner, ctrl.signal).then(w => { if (alive.current && epoch === requestEpoch.current) {
        setWorkspace(w);
        setDraft(copy(w.data));
        clearDraftHistory();
    } }).catch(e => { if (alive.current && epoch === requestEpoch.current && !ctrl.signal.aborted)
        setError(message(e)); }); return () => { alive.current = false; requestEpoch.current++; ctrl.abort(); }; }, [owner, clearDraftHistory]);
    useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
    useEffect(() => { if (!dirty)
        return; const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; }; window.addEventListener('beforeunload', handler); return () => window.removeEventListener('beforeunload', handler); }, [dirty]);
    const edit = (fn: (value: LifeData) => void) => { if (!draft || writeLock.current)
        return; const next = copy(draft); fn(next); if (JSON.stringify(next) === JSON.stringify(draft)) return; draftHistory.capture(draft); setDraft(next); setDirty(true); setNotice(''); };
    const moveHistory = (direction: 'undo' | 'redo') => {
        if (!draft || !workspace || busy || writeLock.current) return;
        const next = draftHistory[direction](draft);
        if (!next) return;
        setDraft(next); setDirty(JSON.stringify(next) !== JSON.stringify(workspace.data)); setNotice(''); setGenerated(null); setPreview(null);
    };
    const selectDay = (date: string) => { setDay(date); setGenerated(null); };
    const locateTask = (task: LifeTask) => { selectDay(task.date); setTab('今日'); setPendingTask(task.id); };
    useEffect(() => {
        if (!pendingTask || tab !== '今日') return;
        const target = document.getElementById(`life-task-${pendingTask}`);
        if (target) { target.scrollIntoView?.({ behavior: 'smooth', block: 'center' }); target.focus({ preventScroll: true }); setPendingTask(null); }
    }, [pendingTask, tab, day]);
    const editWeek = (fn: (value: LifeData['weeks'][string]) => void) => edit(d => { d.weeks[monday] ??= blankWeek(); fn(d.weeks[monday]); });
    const write = async (operation: () => Promise<LifeWorkspace>) => { if (writeLock.current)
        return; writeLock.current = true; setBusy(true); setError(''); const epoch = ++requestEpoch.current; try {
        const w = await operation();
        if (alive.current && epoch === requestEpoch.current) {
            setWorkspace(w);
            setDraft(copy(w.data));
            clearDraftHistory();
            setDirty(false);
            setNotice('已保存');
            setHistory([]);
            setGenerated(null);
            setPreview(null);
        }
    }
    catch (e) {
        if (alive.current && epoch === requestEpoch.current)
            setError(message(e));
    }
    finally {
        writeLock.current = false;
        if (alive.current && epoch === requestEpoch.current)
            setBusy(false);
    } };
    const save = (next = draft) => { if (workspace && next)
        void write(() => saveLifeWorkspace(owner, workspace.revision, next)); };
    const focusSave = (focus: LifeFocus) => { if (!draft)
        return; const next = copy(draft); next.focus = focus; draftHistory.capture(draft); setDraft(next); setDirty(true); save(next); };
    const reload = () => { if (dirty && !window.confirm('重新读取会丢弃本地未保存更改。建议先导出本地草稿，确定继续？'))
        return; const epoch = ++requestEpoch.current; setBusy(true); getLifeWorkspace(owner).then(w => { if (alive.current && epoch === requestEpoch.current) {
        setWorkspace(w);
        setDraft(copy(w.data));
        clearDraftHistory();
        setDirty(false);
        setError('');
        setNotice('已重新读取');
        setHistory([]);
        setGenerated(null); setPreview(null); setPendingTask(null);
    } }).catch(e => { if (alive.current && epoch === requestEpoch.current)
        setError(message(e)); }).finally(() => { if (alive.current && epoch === requestEpoch.current)
        setBusy(false); }); };
    const loadHistory = async () => { const epoch = requestEpoch.current; try {
        const h = await getLifeHistory(owner);
        if (alive.current && epoch === requestEpoch.current)
            setHistory(h.slice(-20).reverse());
    }
    catch (e) {
        if (alive.current && epoch === requestEpoch.current)
            setError(message(e));
    } };
    const field = (label: string, value: string, onChange: (v: string) => void, multiline = true) => <label key={label} className={css.field}>{label}{multiline ? <textarea className={`${css.input} ${css.textarea}`} value={value} maxLength={4000} onChange={e => onChange(e.target.value)}/> : <input className={css.input} value={value} maxLength={4000} onChange={e => onChange(e.target.value)}/>}</label>;
    const button = (label: string, onClick: () => void, primary = false) => <button type="button" className={`${css.button} ${primary ? css.primary : ''}`} onClick={onClick} disabled={busy}>{label}</button>;
    if (!draft || !workspace)
        return <div className={css.workspace}><h1>人生与时间导航</h1>{error ? <div role="alert" className={css.alert}>{error}</div> : <p>正在读取你的工作区…</p>}{error ? button('重新读取', reload) : null}</div>;
    const week = draft.weeks[monday] ?? blankWeek();
    const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
    const todayTasks = week.tasks.filter(t => t.date === day);
    const updateTask = (id: string, patch: Partial<LifeTask>) => editWeek(w => { const task = w.tasks.find(t => t.id === id); if (task)
        Object.assign(task, patch); });
    const addTask = (role: LifeTask['role']) => { if (role === 'main' && todayTasks.some(t => t.role === 'main'))
        return; if (role === 'auxiliary' && todayTasks.filter(t => t.role === 'auxiliary').length >= 2)
        return; editWeek(w => { if(w.tasks.length >= 100) { setError('每周任务最多 100 项，请先整理现有任务。'); return; } const task = blankTask(day,role); if(role==='auxiliary' && todayTasks.filter(t=>t.role==='auxiliary').length===1) task.track_id='aux2'; w.tasks.push(task); }); };
    const taskCard = (task: LifeTask) => <section id={`life-task-${task.id}`} tabIndex={-1} className={`${css.card} ${task.role === 'main' ? css.mainTask : ''}`} key={task.id}>
  <div className={css.row}><span className={css.status}>{task.role === 'main' ? '主任务' : task.role === 'auxiliary' ? '辅助任务' : '可选事项'}</span><span className={css.muted}>{task.date}</span>{button('删除此任务', () => { if (window.confirm('删除当前任务？保存前可通过重新读取恢复。'))
        edit(d => { d.weeks[monday].tasks = d.weeks[monday].tasks.filter(t => t.id !== task.id); if (d.focus.task_id === task.id)
            d.focus = focusEnd(d.focus); }); })}</div>
  {field('任务标题', task.title, v => updateTask(task.id, { title: v }), false)}
  <div className={css.grid}>
   {field('完成标准', task.criterion, v => updateTask(task.id, { criterion: v }))}
   <label className={css.field}>所属主线<select className={css.input} value={task.track_id} onChange={e => updateTask(task.id, { track_id: e.target.value as LifeTask['track_id'] })}>{tracks.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</select></label>
   <label className={css.field}>计划时段<select className={css.input} value={task.slot} onChange={e => updateTask(task.id, { slot: e.target.value as LifeTask['slot'] })}>{Object.entries(slotLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
   <label className={css.field}>执行状态<select className={css.input} value={task.status} onChange={e => updateTask(task.id, { status: e.target.value as LifeTask['status'] })}>{Object.entries(statusLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
   {(['estimated_minutes', 'actual_minutes'] as const).map(key => <label key={key} className={css.field}>{key === 'estimated_minutes' ? '预计分钟' : '实际分钟'}<input className={css.input} type="number" min={0} max={1440} value={task[key] ?? ''} onChange={e => { const v = e.target.value === '' ? null : Number(e.target.value); if (v === null || (Number.isInteger(v) && v >= 0 && v <= 1440))
        updateTask(task.id, { [key]: v }); }}/></label>)}
  </div>
  <details><summary className={css.link}>执行结果、根因与改进</summary><div className={css.grid}>{field('执行结果', task.result, v => updateTask(task.id, { result: v }))}{field('根因', task.root_cause, v => updateTask(task.id, { root_cause: v }))}{field('改进策略', task.improvement, v => updateTask(task.id, { improvement: v }))}</div></details>
 </section>;
    const addSlotTask = (date: string, slot: LifeTask['slot']) => {
        if (busy || writeLock.current) return;
        if (week.tasks.length >= 100) { setError('每周任务最多 100 项，请先整理现有任务。'); return; }
        const task = { ...blankTask(date, 'other'), slot };
        editWeek(w => { w.tasks.push(task); });
        locateTask(task);
    };
    const weekTable = () => <div className={css.tableWrap} tabIndex={0} role="region" aria-label="七天日程表，可横向滚动"><table className={css.table}><caption className={css.muted}>{monday} → {addDays(monday, 6)} · 周一至周日，与 Health 滚动 7 天分开</caption><thead><tr><th>日期</th>{Object.entries(slotLabels).map(([id, label]) => <th key={id}>{label}</th>)}</tr></thead><tbody>{days.map(date => <tr key={date}><th>{date.slice(5)}<small className={css.tableDay}>{weekDayLabel(date)}</small></th>{(Object.keys(slotLabels) as LifeTask['slot'][]).map(slot => <td key={slot}>{week.tasks.filter(t => t.date === date && t.slot === slot).map(t => <button type="button" className={css.taskLink} key={t.id} onClick={() => locateTask(t)}>{t.title || '未填写标题'} · {statusLabels[t.status]}</button>)}<button type="button" className={css.addSlot} aria-label={`${date} ${slotLabels[slot]}添加事项`} onClick={() => addSlotTask(date, slot)}>＋ 添加事项</button></td>)}</tr>)}</tbody></table></div>;
    const f = draft.focus;
    const seconds = f.phase === 'paused' ? f.remaining_seconds ?? 0 : f.deadline ? Math.max(0, Math.ceil((Date.parse(f.deadline) - now) / 1000)) : f.focus_minutes * 60;
    const opportunityPatch = (id: string, patch: Partial<LifeOpportunity>) => edit(d => { const o = d.opportunities.find(o => o.id === id); if (o)
        Object.assign(o, patch); });
    const mainTask = todayTasks.find(t => t.role === 'main');
    const completedCount = todayTasks.filter(t => t.status === 'done').length;
    return <main className={css.workspace}>
  <aside className={css.sidebar}>
    <div className={css.brandRow}><a className={css.brand} href="/" aria-label="Reva 首页"><span className={css.brandMark}><Compass size={23} aria-hidden="true"/></span><span>Reva<span className={css.brandSub}>人生与时间导航</span></span></a><button type="button" className={css.menuButton} aria-label={menuOpen ? '收起导航' : '展开导航'} aria-expanded={menuOpen} aria-controls="life-navigation-menu" onClick={() => setMenuOpen(v => !v)}><Menu size={20} aria-hidden="true"/></button></div>
    <nav id="life-navigation-menu" className={`${css.tabs} ${menuOpen ? css.menuOpen : ''}`} aria-label="人生导航视图">{navGroups.map(group => <div className={css.navGroup} key={group.label}><p className={css.navLabel}>{group.label}</p>{group.items.map(({ title, icon: Icon }) => <button type="button" className={`${css.tab} ${tab === title ? css.active : ''}`} aria-pressed={tab === title} key={title} onClick={() => { setTab(title); setMenuOpen(false); if (title === '备份') void loadHistory(); }}><Icon size={17} aria-hidden="true"/><span>{title}</span></button>)}</div>)}<a className={css.healthLink} href="/my-progress?navigation=week">查看 Health 健康周导航 <span aria-hidden="true">↗</span></a></nav>
    <p className={css.sidebarNote}>方向 · 行动 · 时间 · 复盘<br/>让每一天，都朝向自己。</p>
  </aside>
  <div className={css.content}>
  <header className={css.header}>
    <div><span className={css.eyebrow}>LIFE NAVIGATION</span><h1>{tab === '今日' ? '今日导航' : tab === '机会' ? '机会探索' : `${tab}工作区`}</h1></div>
    <div className={css.saveActions}><span role="status" className={`${css.saveStatus} ${dirty ? css.unsaved : ''}`}>{busy ? '正在处理…' : dirty ? '有未保存更改' : notice || `已读取版本 ${workspace.revision}`}</span><div className={css.row}><div className={css.historyActions}><button type="button" className={css.iconButton} aria-label="撤销" title="撤销更改" disabled={busy || !draftHistory.canUndo} onClick={() => moveHistory('undo')}><Undo2 size={17} aria-hidden="true"/></button><button type="button" className={css.iconButton} aria-label="重做" title="重做更改" disabled={busy || !draftHistory.canRedo} onClick={() => moveHistory('redo')}><Redo2 size={17} aria-hidden="true"/></button></div>{button('重新读取', reload)}{button('保存工作区', () => save(), true)}</div></div>
  </header>
  <div className={css.body}>
  {error ? <div role="alert" className={css.alert}>{error}{error.includes('版本冲突') ? <div>{button('导出本地草稿', () => download({ schema_version: 'life_navigation.backup.v1', workspace: { ...workspace, data: draft }, history: [] }, 'draft'))}</div> : null}</div> : null}
  <div className={css.pageIntro}><p>{viewDescriptions[tab]}</p><span className={css.muted}>健康事实仍在 Health 记录一次。</span></div>
  <section className={css.datePanel} aria-label="日期导航">
    <div className={css.weekHeader}><div><span className={css.eyebrow}>第 {weekNumber(day)} 周</span><h2>{monday.slice(0, 4)} 年 {Number(monday.slice(5, 7))} 月 <span>{monday.slice(5)} — {addDays(monday, 6).slice(5)}</span></h2></div><div className={css.row}><button type="button" className={css.iconButton} aria-label="上一周" onClick={() => selectDay(addDays(day, -7))}><ChevronLeft size={18} aria-hidden="true"/></button><button type="button" className={css.button} onClick={() => selectDay(localDate())}>回到今天</button><button type="button" className={css.iconButton} aria-label="下一周" onClick={() => selectDay(addDays(day, 7))}><ChevronRight size={18} aria-hidden="true"/></button><label className={css.datePicker}>查看日期<input className={css.input} type="date" value={day} onChange={e => { if (e.target.value) selectDay(e.target.value); }}/></label></div></div>
    <div className={css.dayStrip}>{days.map(date => <button type="button" className={`${css.dayButton} ${day === date ? css.selectedDay : ''}`} aria-label={`${date} ${weekDayLabel(date)}`} aria-pressed={day === date} key={date} onClick={() => selectDay(date)}><span>{weekDayLabel(date)}</span><strong>{Number(date.slice(8))}</strong><span className={css.dayDot} aria-label={date === localDate() ? '今天' : undefined}>{date === localDate() ? '今天' : week.tasks.some(t => t.date === date) ? '·' : ' '}</span></button>)}</div>
  </section>
  <fieldset className={css.fieldset} disabled={busy}>
  {tab === '今日' ? <>
    <nav className={css.quickLinks} aria-label="今日快捷导航"><a href="#life-today-tasks">今日任务</a><a href="#life-today-schedule">时间安排</a><a href="#life-today-notes">日记录</a></nav>
    <section className={css.focusCard}><div className={css.focusCopy}><span className={css.focusEyebrow}>TODAY’S FOCUS · 今日重点</span><h2>{mainTask?.title || '今天，最重要的一件事是什么？'}</h2><p>{mainTask?.criterion || '先确定一件值得完成的事，再为它留出时间。'}</p>{mainTask ? <button type="button" className={css.focusButton} onClick={() => locateTask(mainTask)}>查看主任务 <span aria-hidden="true">↗</span></button> : <span className={css.focusHint}>从下方添加你的主任务</span>}</div><div className={css.completion}><strong>{completedCount}<span> / {todayTasks.length}</span></strong><span>已完成 {completedCount} / {todayTasks.length} 项</span><div className={css.progressTrack}><div style={{ width: `${todayTasks.length ? completedCount / todayTasks.length * 100 : 0}%` }}/></div></div></section>
    <section id="life-today-tasks" className={css.taskSection}><div className={css.sectionHeading}><div><span className={css.eyebrow}>01 · DAILY TASKS</span><h2>今天的 1 主 2 辅</h2><p className={css.muted}>先主后辅，给重要的事留出位置。</p></div><div className={css.row}>{!todayTasks.some(t => t.role === 'main') ? button('添加主任务', () => addTask('main'), true) : null}{todayTasks.filter(t => t.role === 'auxiliary').length < 2 ? button('添加辅助任务', () => addTask('auxiliary')) : null}{button('添加可选事项', () => addTask('other'))}</div></div>{todayTasks.length ? [...todayTasks].sort((a, b) => ['main', 'auxiliary', 'other'].indexOf(a.role) - ['main', 'auxiliary', 'other'].indexOf(b.role)).map(taskCard) : <div className={css.emptyState}><Sun size={26} aria-hidden="true"/><h3>为这一天，定下一个重点</h3><p>添加 1 项主任务，最多 2 项辅助任务。其他事项按需记录。</p></div>}</section>
    <section id="life-today-schedule" className={css.scheduleSection} aria-label="今日时间安排"><div className={css.sectionHeading}><div><span className={css.eyebrow}>02 · TIME BLOCKS</span><h2>今日时间安排</h2><p className={css.muted}>按任务的计划时段整理，点击任务可直接编辑。</p></div></div><div className={css.slotGrid}>{Object.entries(slotLabels).map(([slot, label], index) => <section key={slot} className={css.slotCard}><span className={css.slotIndex}>0{index + 1}</span><h3>{label}</h3>{todayTasks.some(t => t.slot === slot) ? todayTasks.filter(t => t.slot === slot).map(task => <button type="button" className={css.slotTask} key={task.id} aria-label={`编辑任务：${task.title || '未填写标题'}`} onClick={() => locateTask(task)}><span>{task.title || '未填写标题'}</span><small>{statusLabels[task.status]}{task.estimated_minutes !== null ? ` · ${task.estimated_minutes} 分钟` : ''}</small></button>) : <p className={css.slotEmpty}>尚未安排任务</p>}</section>)}</div></section>
    <section id="life-today-notes" className={css.card}><span className={css.eyebrow}>03 · DAILY NOTES</span><h2>今日记录</h2><p className={css.muted}>留下值得记住的事，给下一次行动一些启发。</p><div className={css.grid}>{(['valuable', 'beautiful', 'mistake', 'learning'] as const).map((key, i) => field(['有价值的事', '美好的事', '错误与差距', '学到的事'][i], week.notes[day]?.[key] ?? '', v => editWeek(w => { w.notes[day] ??= { valuable: '', beautiful: '', mistake: '', learning: '' }; w.notes[day][key] = v; })))}</div></section>
  </> : null}
  {tab === '周计划' ? <><section className={css.card}><h2>本周五条主线</h2><div className={css.stack}>{tracks.map(meta => { const track = week.tracks.find(t => t.id === meta.id) ?? { id: meta.id, title: '', criterion: '', strategy_link: '', next_step: '' }; const patch = (key: keyof typeof track, value: string) => editWeek(w => { let t = w.tracks.find(t => t.id === meta.id); if (!t) {
        t = { ...track };
        w.tracks.push(t);
    } Object.assign(t, { [key]: value }); }); return <section key={meta.id}><h3>{meta.label}</h3><div className={css.grid}>{field(`${meta.label}目标`, track.title, v => patch('title', v))}{field(`${meta.label}完成标准`, track.criterion, v => patch('criterion', v))}{field(`${meta.label}战略关联`, track.strategy_link, v => patch('strategy_link', v))}{field(`${meta.label}下一步`, track.next_step, v => patch('next_step', v))}</div></section>; })}</div></section><section className={css.card}><h2>七天日程</h2>{weekTable()}</section></> : null}
  {tab === '时段导航' ? <><section className={css.card}><h2>专注与休息</h2><p className={css.muted}>截止时间随工作区保存，可跨刷新恢复。计时结束不会改变任务执行状态。计时按钮会保存当前工作区更改。</p><div className={css.clock}>{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</div><p>第 {f.current_round}/{f.rounds} 轮 · {f.phase === 'idle' ? '未开始' : f.phase === 'paused' ? '已暂停' : f.phase === 'focus' ? '专注' : '休息'}</p><div className={css.grid}>{(['focus_minutes', 'rest_minutes', 'rounds'] as const).map((key, i) => <label className={css.field} key={key}>{['专注分钟', '休息分钟', '轮数'][i]}<input className={css.input} type="number" min={1} max={key === 'focus_minutes' ? 180 : key === 'rest_minutes' ? 60 : 12} disabled={f.phase !== 'idle'} value={f[key]} onChange={e => { const v = Number(e.target.value); const max = key === 'focus_minutes' ? 180 : key === 'rest_minutes' ? 60 : 12; if (Number.isInteger(v) && v >= 1 && v <= max)
        edit(d => { d.focus[key] = v; }); }}/></label>)}<label className={css.field}>关联任务<select className={css.input} disabled={f.phase !== 'idle'} value={f.task_id ?? ''} onChange={e => edit(d => { d.focus.task_id = e.target.value || null; })}><option value="">不关联任务</option>{todayTasks.map(t => <option key={t.id} value={t.id}>{t.title || '未填写标题'}</option>)}</select></label></div><div className={css.row}>{f.phase === 'idle' ? button('开始并保存', () => focusSave(focusStart(f, f.task_id, Date.now())), true) : f.phase === 'paused' ? button('继续并保存', () => focusSave(focusResume(f, Date.now())), true) : seconds === 0 ? button('进入下一阶段并保存', () => focusSave(focusAdvance(f, Date.now())), true) : button('暂停并保存', () => focusSave(focusPause(f, Date.now())))}{f.phase !== 'idle' ? button('结束计时并保存', () => focusSave(focusEnd(f))) : null}</div></section><section className={css.card}>{weekTable()}</section></> : null}
  {tab === '周复盘' ? <section className={css.card}><h2>本周复盘</h2><p className={css.muted}>仅汇总当前周实际任务和日记录；不会判断健康效果，也不会覆盖已填写内容。</p>{button('生成待核对草稿', () => setGenerated(reviewDraft(week)))}{generated ? <div className={css.alert}><p>草稿仅供核对，未写入工作区。</p><pre className={css.archive}>{Object.entries(generated).map(([k, v]) => `${reviewLabels[k as keyof LifeReview]}：${v || '暂无记录'}`).join('\n\n')}</pre>{button('仅填入空白字段', () => { editWeek(w => { w.review = applyReviewDraft(w.review, generated); }); setGenerated(null); })}</div> : null}<div className={css.grid}>{Object.entries(reviewLabels).map(([k, label]) => field(label, week.review[k as keyof LifeReview], v => editWeek(w => { w.review[k as keyof LifeReview] = v; })))}</div>{button('定稿并归档', () => { if (!Object.values(week.review).some(v => v.trim())) {
        setError('请先填写或核对本周复盘。');
        return;
    } if (!window.confirm('将当前复盘定稿为成果并保存工作区？'))
        return; const next = copy(draft); next.weeks[monday] ??= blankWeek(); const body = Object.entries(reviewLabels).map(([k, label]) => `${label}\n${week.review[k as keyof LifeReview]}`).join('\n\n'); next.weeks[monday].archives.push({ id: newId(), created_at: new Date().toISOString(), title: `${monday} 本周复盘`, body, source_revision: workspace.revision }); if (next.weeks[monday].archives.length > 20) {
        setError('本周成果最多保存 20 条，请先整理。');
        return;
    } draftHistory.capture(draft); setDraft(next); setDirty(true); save(next); }, true)}</section> : null}
  {tab === '成果' ? <section className={css.card}><h2>本周成果</h2><p className={css.muted}>可编辑成果正文；保存生成工作区版本，旧版在“备份”中恢复。</p>{week.archives.length ? week.archives.map(a => <div className={css.card} key={a.id}><p className={css.muted}>{a.created_at} · 来源版本 {a.source_revision}</p>{field('成果标题', a.title, v => editWeek(w => { const item = w.archives.find(x => x.id === a.id); if (item)
        item.title = v.slice(0, 200); }), false)}<label className={css.field}>成果正文<textarea className={`${css.input} ${css.textarea}`} rows={10} maxLength={20000} value={a.body} onChange={e => editWeek(w => { const item = w.archives.find(x => x.id === a.id); if (item)
        item.body = e.target.value; })}/></label></div>) : <p className={css.muted}>尚未归档成果。</p>}</section> : null}
  {tab === '方向与季度' ? <><section className={css.card}><h2>方向</h2><div className={css.grid}>{(['vision', 'annual_goal', 'primary_question'] as const).map((key, i) => field(['愿景', '年度目标', '当前头号问题'][i], draft.strategy[key], v => edit(d => { d.strategy[key] = v; })))}</div></section><section className={css.card}><h2>{quarter} 季度回顾</h2><p className={css.muted}>由你判断与确认，不自动生成战略结论。</p><div className={css.grid}>{(['review', 'strategy', 'decomposition', 'plan', 'risk'] as const).map((key, i) => field(['季度复盘', '战略更新', '分解更新', '计划更新', '风险管理'][i], draft.quarters[quarter]?.[key] ?? '', v => edit(d => { d.quarters[quarter] ??= { review: '', strategy: '', decomposition: '', plan: '', risk: '' }; d.quarters[quarter][key] = v; })))}</div></section></> : null}
  {tab === '机会' ? <><section className={css.card}><h2>机会验证</h2><p className={css.muted}>记录证据、假设、最小验证和投入边界。证据等级与适配由你选择，无自动评分或预测。</p>{button('添加验证卡', () => edit(d => d.opportunities.push({ id: newId(), category: 'macro', insight: '', evidence: '', personal_fit: '', assumption: '', next_step: '', success_criteria: '', risk_limit: '', review_date: null, result: '', evidence_level: 'unknown', fit: 'unknown' })))}</section>{draft.opportunities.map(o => <section className={css.card} key={o.id}><div className={css.grid}><label className={css.field}>领域<select className={css.input} value={o.category} onChange={e => opportunityPatch(o.id, { category: e.target.value as LifeOpportunity['category'] })}>{[['macro', '宏观'], ['industry', '行业'], ['people', '人才'], ['customer', '客户']].map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>{(['insight', 'evidence', 'personal_fit', 'assumption', 'next_step', 'success_criteria', 'risk_limit', 'result'] as const).map((key, i) => field(['观察', '来源与证据', '个人适配', '关键假设', '最小验证步骤', '成功或停止标准', '投入与风险上限', '实际结果'][i], o[key], v => opportunityPatch(o.id, { [key]: v })))}<label className={css.field}>复查日期<input className={css.input} type="date" value={o.review_date ?? ''} onChange={e => opportunityPatch(o.id, { review_date: e.target.value || null })}/></label><label className={css.field}>证据等级<select className={css.input} value={o.evidence_level} onChange={e => opportunityPatch(o.id, { evidence_level: e.target.value as LifeOpportunity['evidence_level'] })}>{[['unknown', '未知'], ['hypothesis', '假设'], ['signal', '信号'], ['supported', '有证据支持']].map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label><label className={css.field}>适配程度<select className={css.input} value={o.fit} onChange={e => opportunityPatch(o.id, { fit: e.target.value as LifeOpportunity['fit'] })}>{[['unknown', '未知'], ['low', '低'], ['medium', '中'], ['high', '高']].map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label></div>{button('删除验证卡', () => { if (window.confirm('删除这张验证卡？保存前可通过重新读取恢复。'))
        edit(d => { d.opportunities = d.opportunities.filter(x => x.id !== o.id); }); })}</section>)}</> : null}
  {tab === '备份' ? <><section className={css.card}><h2>工作区备份</h2><p className={css.muted}>备份仅含本人生活导航内容，不包含 Health 数据、健康引用或凭据。导入会替换当前工作区，先预览再明确确认；冲突时保留当前草稿。</p><div className={css.row}>{button('导出已保存备份', () => { const epoch = requestEpoch.current; getLifeBackup(owner).then(b => { if (alive.current && epoch === requestEpoch.current)
        download(b, 'saved'); }).catch(e => { if (alive.current && epoch === requestEpoch.current)
        setError(message(e)); }); })}{button('导出本地草稿', () => download({ schema_version: 'life_navigation.backup.v1', workspace: { ...workspace, data: draft }, history: [] }, 'draft'))}<label className={css.field}>选择备份预览<input type="file" accept="application/json,.json" onChange={async (e) => { const file = e.target.files?.[0]; if (!file)
        return; const epoch = requestEpoch.current; try {
        if (file.size > 6 * 1024 * 1024)
            throw Error('备份超过 6 MiB');
        const b = parseBackup(await file.text());
        if (alive.current && epoch === requestEpoch.current) {
            setPreview(b);
            setError('');
        }
    }
    catch (error) {
        if (alive.current && epoch === requestEpoch.current) {
            setPreview(null);
            setError(error instanceof Error ? error.message : '备份格式无效');
        }
    } e.target.value = ''; }}/></label></div>{preview ? <div className={css.alert}><h3>导入预览</h3><p>来源版本 {preview.workspace.revision} · {Object.keys(preview.workspace.data.weeks).length} 周 · {Object.values(preview.workspace.data.weeks).reduce((n, w) => n + w.tasks.length, 0)} 项任务 · {preview.history.length} 个历史版本</p>{button('确认替换并导入', () => { if (window.confirm('将备份内容替换当前工作区。未保存更改将丢失；操作生成新版本。确定导入？'))
        void write(() => importLifeBackup(owner, workspace.revision, preview)); }, true)}{button('取消预览', () => setPreview(null))}</div> : null}</section><section className={css.card}><h2>最近 20 个工作区版本</h2>{button('刷新版本列表', () => void loadHistory())}{history.map(v => <div className={css.row} key={v.revision}><p>版本 {v.revision} · {v.updated_at}</p>{button(`恢复版本 ${v.revision}`, () => { if (window.confirm(`恢复版本 ${v.revision} 会替换当前工作区及未保存更改，并保留新的版本记录。确定？`))
        void write(() => restoreLifeWorkspace(owner, v.revision, workspace.revision)); })}</div>)}</section></> : null}
  </fieldset>
  <footer className={css.footer}>人生与时间导航 · 记录属于你的方向与行动</footer>
  </div>
  </div>
 </main>;
}
