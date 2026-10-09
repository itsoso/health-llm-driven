'use client';
import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { getLifeWorkspace, saveLifeWorkspace, getLifeHistory, restoreLifeWorkspace, getLifeBackup, importLifeBackup, type LifeData, type LifeWorkspace, type LifeVersion, type LifeBackup, type LifeTask, type LifeOpportunity, type LifeFocus, type LifeReview } from '@/services/lifeNavigation';
import { addDays, mondayOf, localDate, blankWeek, blankTask, copy, tracks, slotLabels, statusLabels, newId, reviewDraft, applyReviewDraft, focusStart, focusPause, focusResume, focusEnd, focusAdvance, parseBackup } from './model';
import css from './workspace.module.css';
const tabs = ['今日', '周计划', '时段导航', '周复盘', '成果', '方向与季度', '机会', '备份'] as const;
type Tab = typeof tabs[number];
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
    } }).catch(e => { if (alive.current && epoch === requestEpoch.current && !ctrl.signal.aborted)
        setError(message(e)); }); return () => { alive.current = false; requestEpoch.current++; ctrl.abort(); }; }, [owner]);
    useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
    useEffect(() => { if (!dirty)
        return; const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ''; }; window.addEventListener('beforeunload', handler); return () => window.removeEventListener('beforeunload', handler); }, [dirty]);
    const edit = (fn: (value: LifeData) => void) => { if (!draft || writeLock.current)
        return; const next = copy(draft); fn(next); setDraft(next); setDirty(true); setNotice(''); };
    const editWeek = (fn: (value: LifeData['weeks'][string]) => void) => edit(d => { d.weeks[monday] ??= blankWeek(); fn(d.weeks[monday]); });
    const write = async (operation: () => Promise<LifeWorkspace>) => { if (writeLock.current)
        return; writeLock.current = true; setBusy(true); setError(''); const epoch = ++requestEpoch.current; try {
        const w = await operation();
        if (alive.current && epoch === requestEpoch.current) {
            setWorkspace(w);
            setDraft(copy(w.data));
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
        return; const next = copy(draft); next.focus = focus; setDraft(next); setDirty(true); save(next); };
    const reload = () => { if (dirty && !window.confirm('重新读取会丢弃本地未保存更改。建议先导出本地草稿，确定继续？'))
        return; const epoch = ++requestEpoch.current; setBusy(true); getLifeWorkspace(owner).then(w => { if (alive.current && epoch === requestEpoch.current) {
        setWorkspace(w);
        setDraft(copy(w.data));
        setDirty(false);
        setError('');
        setNotice('已重新读取');
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
    const taskCard = (task: LifeTask) => <section className={css.card} key={task.id}>
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
    const weekTable = () => <div className={css.tableWrap}><table className={css.table}><caption className={css.muted}>{monday} → {addDays(monday, 6)} · 周一至周日，与 Health 滚动 7 天分开</caption><thead><tr><th>日期</th>{Object.entries(slotLabels).map(([id, label]) => <th key={id}>{label}</th>)}</tr></thead><tbody>{days.map(date => <tr key={date}><th>{date.slice(5)}</th>{Object.keys(slotLabels).map(slot => <td key={slot}>{week.tasks.filter(t => t.date === date && t.slot === slot).map(t => <button className={css.taskLink} key={t.id} onClick={() => { setDay(date); setTab('今日'); }}>{t.title || '未填写标题'} · {statusLabels[t.status]}</button>)}</td>)}</tr>)}</tbody></table></div>;
    const f = draft.focus;
    const seconds = f.phase === 'paused' ? f.remaining_seconds ?? 0 : f.deadline ? Math.max(0, Math.ceil((Date.parse(f.deadline) - now) / 1000)) : f.focus_minutes * 60;
    const opportunityPatch = (id: string, patch: Partial<LifeOpportunity>) => edit(d => { const o = d.opportunities.find(o => o.id === id); if (o)
        Object.assign(o, patch); });
    return <main className={css.workspace}>
  <div className={css.header}><div><h1>人生与时间导航</h1><p className={css.muted}>方向、行动、时间与复盘。健康事实仍在 Health 记录一次。</p></div><div className={css.row}><span className={css.status}>{dirty ? '有未保存更改' : notice || `已读取版本 ${workspace.revision}`}</span>{button('保存工作区', () => save(), true)}{button('重新读取', reload)}</div></div>
  {error ? <div role="alert" className={css.alert}>{error}{error.includes('版本冲突') ? <div>{button('导出本地草稿', () => download({ schema_version: 'life_navigation.backup.v1', workspace: { ...workspace, data: draft }, history: [] }, 'draft'))}</div> : null}</div> : null}
  <nav className={css.tabs} aria-label="人生导航视图">{tabs.map(t => <button type="button" className={`${css.tab} ${tab === t ? css.active : ''}`} aria-pressed={tab === t} key={t} onClick={() => { setTab(t); if (t === '备份')
        void loadHistory(); }}>{t}</button>)}</nav>
  <div className={css.row}><label className={css.field}>查看日期<input className={css.input} type="date" value={day} onChange={e => { if (e.target.value) {
        setDay(e.target.value);
        setGenerated(null);
    } }}/></label><a className={css.link} href="/my-progress?navigation=week">查看 Health 健康周导航</a></div>
  <fieldset className={css.fieldset} disabled={busy}>
  {tab === '今日' ? <><section className={css.card}><h2>今天的 1 主 2 辅</h2><p className={css.muted}>主任务与辅助任务有上限；其他事项可选，无需额外健康录入。</p><div className={css.row}>{!todayTasks.some(t => t.role === 'main') ? button('添加主任务', () => addTask('main')) : null}{todayTasks.filter(t => t.role === 'auxiliary').length < 2 ? button('添加辅助任务', () => addTask('auxiliary')) : null}{button('添加可选事项', () => addTask('other'))}</div></section>{todayTasks.sort((a, b) => ['main', 'auxiliary', 'other'].indexOf(a.role) - ['main', 'auxiliary', 'other'].indexOf(b.role)).map(taskCard)}<section className={css.card}><h2>今日记录</h2><div className={css.grid}>{(['valuable', 'beautiful', 'mistake', 'learning'] as const).map((key, i) => field(['有价值的事', '美好的事', '错误与差距', '学到的事'][i], week.notes[day]?.[key] ?? '', v => editWeek(w => { w.notes[day] ??= { valuable: '', beautiful: '', mistake: '', learning: '' }; w.notes[day][key] = v; })))}</div></section></> : null}
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
    } setDraft(next); setDirty(true); save(next); }, true)}</section> : null}
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
 </main>;
}
