import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect } from 'expo-router';
import { useTheme } from '../../hooks/useTheme';
import { subscribeAIConsentInvalidation } from '../../services/aiConsentState';
import { fetchLifeWorkspace, saveLifeWorkspace, fetchLifeHistory, restoreLifeWorkspace, fetchLifeBackup, importLifeBackup, type LifeData, type LifeWorkspace, type LifeTask, type LifeBackup, type LifeVersion } from '../../services/lifeNavigation';
import { addDays, applyReviewDraft, blankData, blankTask, blankWeek, copy, ensureWeek, focusAdvance, focusEnd, focusPause, focusResume, focusStart, localDate, mondayOf, newId, reviewDraft, slotLabels, statusLabels, tracks, validateData } from '../../utils/lifeNavigationModel';
import { exportLifeBackup, pickLifeBackup } from '../../utils/lifeNavigationFiles';
const tabs = ['今日', '周计划', '时段导航', '周复盘', '成果', '方向与季度', '机会', '备份'] as const;
const reviewFields = { summary: '复盘总结', gap: '差距与根因', learning: '复盘收获', next_week: '下周改进' };
const noteFields = { valuable: '有价值的事', beautiful: '美好的事', mistake: '失误', learning: '今日所学' };
const quarterFields = { review: '季度回顾', strategy: '季度战略', decomposition: '季度拆解', plan: '季度计划', risk: '季度风险' };
const opportunityFields = { insight: '机会洞察', evidence: '依据', personal_fit: '个人适配', assumption: '待验证假设', next_step: '验证行动', success_criteria: '成功标准', risk_limit: '风险边界', result: '验证结果' };
function confirm(title: string, body: string, run: () => void) { Alert.alert(title, body, [{ text: '取消', style: 'cancel' }, { text: '确认', onPress: run }]); }
export default function Workspace({ owner, onViewHealth }: {
    owner: number; onViewHealth:()=>void;
}) {
    const { c } = useTheme();
    const [workspace, setWorkspace] = useState<LifeWorkspace | null>(null), [draft, setDraft] = useState<LifeData | null>(null), [tab, setTab] = useState<typeof tabs[number]>('今日'), [date, setDate] = useState(localDate()), [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [dirty, setDirty] = useState(false), [refresh, setRefresh] = useState(0), [now, setNow] = useState(Date.now());
    const [title, setTitle] = useState(''), [criterion, setCriterion] = useState(''), [role, setRole] = useState<LifeTask['role']>('main'), [newSlot,setNewSlot]=useState<LifeTask['slot']>('flexible'), [history, setHistory] = useState<LifeVersion[]>([]), [preview, setPreview] = useState<LifeBackup | null>(null), [generated, setGenerated] = useState<ReturnType<typeof reviewDraft> | null>(null);
    const snapshot = useRef<{
        workspace: LifeWorkspace | null;
        draft: LifeData | null;
        title: string;
        criterion: string;
        dirty: boolean;
        date: string;
    } | null>(null), suspended = useRef<typeof snapshot.current>(null);
    snapshot.current = { workspace, draft, title, criterion, dirty, date };
    const nativeDialog=useRef(false);
    const epoch = useRef(0), lock = useRef(false), active = useRef(true), alive = useRef(true);
    const monday = mondayOf(date), days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
    const quarter = `${date.slice(0, 4)}-Q${Math.ceil(Number(date.slice(5, 7)) / 3)}`;
    const clear = useCallback(() => { snapshot.current = null; epoch.current++; lock.current = false; setBusy(false); setWorkspace(null); setDraft(null); setTitle(''); setCriterion(''); setHistory([]); setPreview(null); setGenerated(null); setDirty(false); }, []);
    useEffect(() => { alive.current = true; const off = subscribeAIConsentInvalidation(() => { suspended.current = null; clear(); setMessage('登录状态已变化，请重新打开导航。'); }); const sub = AppState.addEventListener('change', state => { if(nativeDialog.current&&(state==='inactive'||(state==='active'&&active.current)))return;
        active.current = state === 'active'; if (!active.current) {
        if (snapshot.current?.workspace && snapshot.current.draft)
                suspended.current = snapshot.current;
        clear();
    }
    else if (suspended.current?.workspace && suspended.current.draft) {
        const saved = suspended.current;
        suspended.current = null;
        setWorkspace(saved.workspace);
        setDraft(saved.draft);
        setTitle(saved.title);
        setCriterion(saved.criterion);
        setDirty(saved.dirty);
        setDate(saved.date);
        setMessage(saved.dirty ? '已恢复未保存草稿，请保存后再离开页面。' : saved.title || saved.criterion ? '已恢复任务输入，请先加入今日安排，再保存。' : '已恢复个人安排');
    }
    else {
        clear();
        setRefresh(v => v + 1);
    } }); const timer = setInterval(() => setNow(Date.now()), 1000); return () => { alive.current = false; suspended.current = null; epoch.current++; off(); sub.remove(); clearInterval(timer); }; }, [clear]);
    useFocusEffect(useCallback(() => { const version = ++epoch.current; active.current = true; setWorkspace(null); setDraft(null); fetchLifeWorkspace(owner).then(w => { if (alive.current && active.current && version === epoch.current) {
        setWorkspace(w);
        setDraft({ ...blankData(), ...w.data });
        setDirty(false);
    } }).catch(() => { if (version === epoch.current)
        setMessage('个人安排暂不可用，请重新读取。'); }); return () => { active.current = false; suspended.current = null; clear(); }; }, [owner, refresh, clear]));
    const week = draft?.weeks[monday] ?? blankWeek(), tasks = week.tasks, focus = draft?.focus;
    function edit(change: (d: LifeData) => void) { if (!draft || lock.current)
        return; const next = ensureWeek(draft, monday); change(next); setDraft(next); setDirty(true); setMessage('草稿尚未保存'); }
    function editWeek(change: (w: typeof week) => void) { edit(d => change(d.weeks[monday])); }
    async function write(send: () => Promise<LifeWorkspace>) { if (!workspace || lock.current || !alive.current || !active.current)
        return; lock.current = true; setBusy(true); const version = ++epoch.current; try {
        const saved = await send();
        if (alive.current && active.current && version === epoch.current) {
            setWorkspace(saved);
            setDraft(copy(saved.data));
            setDirty(false);
            setHistory([]);
            setPreview(null);
            setGenerated(null);
            setTitle('');
            setCriterion('');
            setMessage('已保存个人安排');
        }
    }
    catch (e) {
        if (version === epoch.current)
            setMessage((e as {
                response?: {
                    status: number;
                };
            }).response?.status === 409 ? '另一设备已更新，草稿已保留，请重新读取后核对。' : '保存失败，草稿已保留，请检查字段或稍后重试。');
    }
    finally {
        if (version === epoch.current) {
            lock.current = false;
            setBusy(false);
        }
    } }
    function ask(title: string, body: string, run: () => void) { const version = epoch.current; confirm(title, body, () => { if (alive.current && active.current && version === epoch.current)
        run(); }); }
    function checkedSave(data: LifeData) { validateData(data); return saveLifeWorkspace(owner, workspace!.revision, data); }
    const save = () => { if (draft && workspace)
        void write(() => checkedSave(copy(draft))); };
    function persistFocus(next: NonNullable<typeof focus>) { if (!draft || !workspace)
        return; const data = copy(draft); data.focus = next; setDraft(data); setDirty(true); void write(() => checkedSave(data)); }
    const names: Record<string, string> = { main: '主任务', auxiliary: '辅助任务', other: '可选任务', aux1: '辅助一', aux2: '辅助二', important: '重要事项', misc: '其他事项', morning: '上午', afternoon: '下午', evening: '晚上', flexible: '灵活', planned: '未开始', doing: '进行中', done: '已完成', skipped: '已跳过', macro: '宏观', industry: '行业', people: '人群', customer: '客户', unknown: '未知', hypothesis: '假设', signal: '信号', supported: '有支持证据', low: '低', medium: '中', high: '高', idle: '未启动', focus: '专注', rest: '休息', paused: '已暂停' };
    const cleanLabel = (value: string) => value.replace(/ [a-f0-9]{8}-[a-f0-9-]{27,}$/i, '');
    const text = (value: string) => <Text style={{ color: c.labelPrimary }}>{value}</Text>;
    const button = (label: string, onPress: () => void, disabled = false, visibleLabel?: string) => <Pressable key={label} accessibilityRole="button" accessibilityLabel={label} disabled={busy || disabled} onPress={onPress} style={{ padding: 12, borderWidth: 1, borderColor: c.separator, borderRadius: 12, opacity: (busy || disabled) ? 0.5 : 1 }}><Text style={{ color: c.brand, fontWeight: '600' }}>{visibleLabel ?? cleanLabel(label)}</Text></Pressable>;
    const field = (label: string, value: string, onChange: (v: string) => void, maxLength = 4000, numeric = false) => <View key={label} style={{ gap: 5 }}>{text(cleanLabel(label))}<TextInput accessibilityLabel={label} value={value} onChangeText={onChange} editable={!busy} maxLength={maxLength} multiline={!numeric} keyboardType={numeric ? 'number-pad' : 'default'} style={{ padding: 12, borderWidth: 1, borderColor: c.separator, borderRadius: 10, color: c.labelPrimary, minHeight: 44 }}/></View>;
    const choices = <T extends string>(label: string, value: T, values: readonly T[], onChange: (v: T) => void) => <View style={{ gap: 5 }}>{text(`${label}：${names[value] ?? value}`)}<View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{values.map(v => button(`${label} ${v}`, () => onChange(v), v === value, names[v] ?? v))}</View></View>;
    function updateTask(id: string, patch: Partial<LifeTask>) { const current = tasks.find(t => t.id === id); if (!current)
        return; const next = { ...current, ...patch }, same = tasks.filter(t => t.id !== id && t.date === next.date && t.role === next.role); if (mondayOf(next.date) !== monday || (next.role === 'main' && same.length >= 1) || (next.role === 'auxiliary' && same.length >= 2)) {
        setMessage('任务必须属于本周，每日最多一项主任务、两项辅助任务。');
        return;
    } editWeek(w => { const t = w.tasks.find(v => v.id === id); if (t)
        Object.assign(t, patch); }); }
    function add() { if (!title.trim() || !draft)
        return; const same = tasks.filter(t => t.date === date && t.role === role); if (tasks.length >= 100 || (role === 'main' && same.length >= 1) || (role === 'auxiliary' && same.length >= 2)) {
        setMessage('每日最多一项主任务、两项辅助任务，每周最多100项任务。');
        return;
    } editWeek(w => { const task = blankTask(date, role); task.title = title.trim(); task.criterion = criterion; task.slot=newSlot; if (role === 'auxiliary' && same.length)
        task.track_id = 'aux2'; w.tasks.push(task); }); setTitle(''); setCriterion(''); }
    const taskCard = (task: LifeTask) => <View key={task.id} style={{ padding: 16, gap: 10, borderRadius: 14, backgroundColor: c.bgCard }}>{text(`${task.role === 'main' ? '主任务' : task.role === 'auxiliary' ? '辅助任务' : '可选任务'} · ${task.date}`)}{choices('任务日期', task.date, days, v => updateTask(task.id, { date: v }))}{choices('任务角色', task.role, ['main', 'auxiliary', 'other'], v => updateTask(task.id, { role: v }))}{field(`任务标题 ${task.id}`, task.title, v => updateTask(task.id, { title: v }))}{field(`完成标准 ${task.id}`, task.criterion, v => updateTask(task.id, { criterion: v }))}{choices('时段', task.slot, Object.keys(slotLabels) as LifeTask['slot'][], v => updateTask(task.id, { slot: v }))}{choices('任务主线', task.track_id, tracks.map(t => t.id), v => updateTask(task.id, { track_id: v }))}{choices('状态', task.status, Object.keys(statusLabels) as LifeTask['status'][], v => updateTask(task.id, { status: v }))}{(['estimated_minutes', 'actual_minutes'] as const).map(k => field(`${k === 'estimated_minutes' ? '预计' : '实际'}分钟 ${task.id}`, task[k] === null ? '' : String(task[k]), v => { if (v === '' || /^\d{1,4}$/.test(v) && Number(v) <= 1440)
        updateTask(task.id, { [k]: v === '' ? null : Number(v) }); }, 4, true))}{(['result', 'root_cause', 'improvement'] as const).map((k, i) => field(`${['任务结果', '根因', '改进'][i]} ${task.id}`, task[k], v => updateTask(task.id, { [k]: v })))}{button('开始此任务计时 ' + task.id, () => focus && persistFocus(focusStart(focus, task.id, Date.now())))}{button('删除任务 ' + task.id, () => ask('删除任务', '确认移除此任务？尚未保存的修改也会保留在草稿中。', () => edit(d => { d.weeks[monday].tasks = d.weeks[monday].tasks.filter(t => t.id !== task.id); if (d.focus.task_id === task.id)
        d.focus = focusEnd(d.focus); })))}</View>;
    async function readExtras(kind: 'history' | 'backup' | 'pick' | 'draft') { const version = epoch.current; nativeDialog.current=kind!=='history';try {
        if (kind === 'history') {
            const data = await fetchLifeHistory(owner);
            if (version === epoch.current && active.current)
                setHistory(data);
        }
        else if (kind === 'pick') {
            const data = await pickLifeBackup(() => version === epoch.current && alive.current && active.current);
            if (version === epoch.current && active.current)
                setPreview(data);
        }
        else {
            const backup = kind === 'draft' && workspace && draft ? { schema_version: 'life_navigation.backup.v1' as const, workspace: { ...workspace, data: copy(draft) }, history: [] } : await fetchLifeBackup(owner);
            if (version === epoch.current && active.current) {
                const shared = await exportLifeBackup(backup, () => version === epoch.current && alive.current && active.current);
                if (version === epoch.current)
                    setMessage(shared ? '已打开备份分享，请以系统保存结果为准。' : '已取消导出');
            }
        }
    }
    catch {
        if (version === epoch.current)
            setMessage('备份或历史读取失败，请检查文件格式与大小。');
    } finally {nativeDialog.current=false;} }
    return <><Stack.Screen options={{ title: '人生战略导航仪', headerShown: true, headerBackTitle: '返回' }}/><ScrollView style={{ backgroundColor: c.bgPrimary }} contentContainerStyle={{ padding: 20, gap: 14 }}><Text style={{ fontSize: 25, fontWeight: '700', color: c.labelPrimary }}>人生战略导航仪</Text>{text('个人安排、记录与方向 · 健康执行请在 Health 中确认。后台会隐藏正文；返回恢复同账号草稿，离开页面或切换账号会清除未保存草稿。')}{button('查看健康周导航', onViewHealth)}
 <ScrollView horizontal><View style={{ flexDirection: 'row', gap: 8 }}>{tabs.map(t => button(t, () => setTab(t), tab === t))}</View></ScrollView>
 {message ? <Text accessibilityRole="alert" style={{ color: c.labelSecondary }}>{message}</Text> : null}
 {!draft || !workspace ? <ActivityIndicator /> : <>
 {text(`本周 ${monday} · 已保存版本 ${workspace.revision} · ${dirty ? '有未保存草稿' : title || criterion ? '任务输入尚未加入安排，加入后再保存' : '已与服务端同步'}`)}{button('保存个人安排', save, !dirty)}
 <View style={{ flexDirection: 'row', gap: 8 }}>{button('前一天', () => { setDate(addDays(date, -1)); setGenerated(null); })}{button('后一天', () => { setDate(addDays(date, 1)); setGenerated(null); })}</View>{text('所选日期 ' + date)}
 {tab === '今日' && <>
 {!tasks.filter(t => t.date === date).length && text('还没有个人安排。')}{tasks.filter(t => t.date === date).map(taskCard)}
 {choices('新任务角色', role, ['main', 'auxiliary', 'other'], setRole)}{choices('新任务时段',newSlot,Object.keys(slotLabels) as LifeTask['slot'][],setNewSlot)}{field('个人任务标题', title, v => { setTitle(v); setMessage('任务输入尚未加入安排，请先加入今日安排，再保存。'); })}{field('完成标准', criterion, v => { setCriterion(v); setMessage('任务输入尚未加入安排，请先加入今日安排，再保存。'); })}{button('加入今日安排', add)}
 {Object.entries(noteFields).map(([k, label]) => field(label, week.notes[date]?.[k as keyof typeof noteFields] ?? '', v => editWeek(w => { w.notes[date] ??= { valuable: '', beautiful: '', mistake: '', learning: '' }; w.notes[date][k as keyof typeof noteFields] = v; })))}
 </>}
 {tab === '周计划' && <>{tracks.map(t => { const track = week.tracks.find(v => v.id === t.id) ?? { id: t.id, title: '', criterion: '', strategy_link: '', next_step: '' }; return <View key={t.id} style={{ padding: 16, gap: 10, backgroundColor: c.bgCard, borderRadius: 14 }}>{text(t.label)}{(['title', 'criterion', 'strategy_link', 'next_step'] as const).map((k, i) => field(`${t.label}${['标题', '标准', '战略关联', '下一步'][i]}`, track[k], v => editWeek(w => { let item = w.tracks.find(x => x.id === t.id); if (!item) {
            item = { ...track };
            w.tracks.push(item);
        } item[k] = v; })))}</View>; })}</>}
 {(tab === '周计划' || tab === '时段导航') && <ScrollView horizontal><View style={{ gap: 8 }}>{days.map(day => <View key={day} style={{ flexDirection: 'row', gap: 8 }}><Text style={{ width: 90, color: c.labelPrimary }}>{day}</Text>{(Object.keys(slotLabels) as LifeTask['slot'][]).map(slot => <View key={slot} style={{ width: 180, padding: 10, borderWidth: 1, borderColor: c.separator, borderRadius: 8, gap: 8 }}>{text(slotLabels[slot])}{!tasks.some(t => t.date === day && t.slot === slot) && button('添加安排 ' + day + ' ' + slot, () => { setDate(day); setNewSlot(slot); setTab('今日'); }, false, '添加安排')}{tasks.filter(t => t.date === day && t.slot === slot).map(t => button(t.title || '未命名任务', () => { setDate(day); setTab('今日'); }))}</View>)}</View>)}</View></ScrollView>}
 {tab === '时段导航' && focus && <>
 {text('计时只记录时段；结束不会完成任务。计时操作会保存当前全部草稿。')}{text(`阶段 ${names[focus.phase]} · 轮次 ${focus.current_round}/${focus.rounds} · 剩余 ${focus.phase === 'paused' ? focus.remaining_seconds ?? 0 : focus.deadline ? Math.max(0, Math.ceil((Date.parse(focus.deadline) - now) / 1000)) : 0} 秒`)}
 {(['focus_minutes', 'rest_minutes', 'rounds'] as const).map((k, i) => field(['专注分钟', '休息分钟', '轮数'][i], String(focus[k]), v => { const max = [180, 60, 12][i]; if (/^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= max)
                edit(d => { d.focus[k] = Number(v); d.focus.current_round = Math.min(d.focus.current_round, d.focus.rounds); }); }, 3, true))}
 {focus.phase === 'idle' ? button('开始计时并保存', () => persistFocus(focusStart(focus, null, Date.now()))) : focus.phase === 'paused' ? button('继续计时并保存', () => persistFocus(focusResume(focus, Date.now()))) : button('暂停计时并保存', () => persistFocus(focusPause(focus, Date.now())))}
 {focus.deadline && Date.parse(focus.deadline) <= now && button('进入下一阶段并保存', () => persistFocus(focusAdvance(focus, Date.now())))}{focus.phase !== 'idle' && button('结束计时并保存', () => persistFocus(focusEnd(focus)))}
 </>}
 {tab === '周复盘' && <>{button('生成实际记录草稿', () => setGenerated(reviewDraft(week)))}{generated && <>{Object.values(generated).map((v, i) => <Text key={i} style={{ color: c.labelSecondary }}>{v}</Text>)}{button('仅填入空白复盘字段', () => editWeek(w => { w.review = applyReviewDraft(w.review, generated); }))}</>}{Object.entries(reviewFields).map(([k, label]) => field(label, week.review[k as keyof typeof reviewFields], v => editWeek(w => { w.review[k as keyof typeof reviewFields] = v; })))}{button('定稿并归档', () => ask('定稿归档', '保存当前所有草稿并将复盘正文加入成果？', () => { if (!workspace || !draft)
            return; const data = ensureWeek(draft, monday), w = data.weeks[monday]; if (w.archives.length >= 20) {
            setMessage('本周成果已达20项，请先整理。');
            return;
        } w.archives.push({ id: newId(), created_at: new Date().toISOString(), title: monday + ' 周复盘', body: Object.entries(reviewFields).map(([k, label]) => `${label}\n${w.review[k as keyof typeof reviewFields]}`).join('\n\n'), source_revision: workspace.revision }); setDraft(data); setDirty(true); void write(() => checkedSave(data)); }))}</>}
 {tab === '成果' && <>{!week.archives.length && text('尚无成果。周复盘定稿后可在这里编辑正文。')}{week.archives.map(a => <View key={a.id} style={{ gap: 10 }}>{field('成果标题 ' + a.id, a.title, v => editWeek(w => { w.archives.find(x => x.id === a.id)!.title = v; }), 200)}{field('成果正文 ' + a.id, a.body, v => editWeek(w => { w.archives.find(x => x.id === a.id)!.body = v; }), 20000)}{text(`来源版本 ${a.source_revision}`)}</View>)}{text('恢复成果旧正文请在备份页预览历史版本，再确认恢复整个工作区。')}</>}
 {tab === '方向与季度' && <>{(['vision', 'annual_goal', 'primary_question'] as const).map((k, i) => field(['愿景', '年度目标', '核心问题'][i], draft.strategy[k], v => edit(d => { d.strategy[k] = v; })))}{text(quarter)}{Object.entries(quarterFields).map(([k, label]) => field(label, draft.quarters[quarter]?.[k as keyof typeof quarterFields] ?? '', v => edit(d => { d.quarters[quarter] ??= { review: '', strategy: '', decomposition: '', plan: '', risk: '' }; d.quarters[quarter][k as keyof typeof quarterFields] = v; })))}</>}
 {tab === '机会' && <>{text('记录证据与验证行动；不会自动生成预测、评分或无证据结论。')}{button('添加机会验证卡', () => { if (draft.opportunities.length >= 100) {
            setMessage('机会卡最多100项');
            return;
        } edit(d => d.opportunities.push({ id: newId(), category: 'macro', insight: '', evidence: '', personal_fit: '', assumption: '', next_step: '', success_criteria: '', risk_limit: '', review_date: null, result: '', evidence_level: 'unknown', fit: 'unknown' })); })}{draft.opportunities.map(o => <View key={o.id} style={{ padding: 16, gap: 10, backgroundColor: c.bgCard, borderRadius: 14 }}>{Object.entries(opportunityFields).map(([k, label]) => field(label + ' ' + o.id, o[k as keyof typeof opportunityFields], v => edit(d => { d.opportunities.find(x => x.id === o.id)![k as keyof typeof opportunityFields] = v; })))}{choices('机会类别', o.category, ['macro', 'industry', 'people', 'customer'], v => edit(d => { d.opportunities.find(x => x.id === o.id)!.category = v; }))}{choices('证据程度', o.evidence_level, ['unknown', 'hypothesis', 'signal', 'supported'], v => edit(d => { d.opportunities.find(x => x.id === o.id)!.evidence_level = v; }))}{choices('适配判断', o.fit, ['unknown', 'low', 'medium', 'high'], v => edit(d => { d.opportunities.find(x => x.id === o.id)!.fit = v; }))}{field('复查日期 YYYY-MM-DD ' + o.id, o.review_date ?? '', v => edit(d => { d.opportunities.find(x => x.id === o.id)!.review_date = v || null; }), 10)}{button('删除机会 ' + o.id, () => ask('删除机会', '确认删除此验证卡？', () => edit(d => { d.opportunities = d.opportunities.filter(x => x.id !== o.id); })))}</View>)}</>}
 {tab === '备份' && <>{text('备份仅包含个人导航正文，不包含 Health 原文或引用。导入会替换整个工作区；冲突不会覆盖草稿。')}{button('导出已保存备份', () => void readExtras('backup'))}{button('导出当前草稿', () => void readExtras('draft'))}{button('选择备份并预览', () => void readExtras('pick'))}{preview && <>{text(`备份预览 · 版本 ${preview.workspace.revision} · ${Object.keys(preview.workspace.data.weeks).length} 周 · ${preview.history.length} 个历史版本`)}{Object.entries(preview.workspace.data.strategy).map(([k, v]) => <Text key={k} style={{ color: c.labelPrimary }}>{({ vision: '愿景', annual_goal: '年度目标', primary_question: '核心问题' } as Record<string, string>)[k]}：{v || '未填写'}</Text>)}{button('确认替换工作区', () => ask('替换整个工作区', '将覆盖当前草稿。先导出需要保留的内容；确认导入此备份？', () => void write(() => importLifeBackup(owner, workspace.revision, preview))))}</>}{button('读取最近20个版本', () => void readExtras('history'))}{history.slice(-20).reverse().map(v => <View key={v.revision} style={{ gap: 8 }}>{text(`历史版本 ${v.revision} · ${v.updated_at}`)}{Object.entries(v.data.strategy).map(([k, value]) => <Text key={k} style={{ color: c.labelPrimary }}>{({ vision: '愿景', annual_goal: '年度目标', primary_question: '核心问题' } as Record<string, string>)[k]}：{value || '未填写'}</Text>)}{button('恢复版本 ' + v.revision, () => ask('恢复整个工作区', '这会替换当前全部草稿，确认恢复该版本？', () => void write(() => restoreLifeWorkspace(owner, v.revision, workspace.revision))))}</View>)}</>}
 </>}
 {button('重新读取个人安排', () => dirty ? ask('重新读取', '当前草稿会被替换，可先在备份页导出草稿。', () => { clear(); setRefresh(v => v + 1); }) : setRefresh(v => v + 1))}
 </ScrollView></>;
}
