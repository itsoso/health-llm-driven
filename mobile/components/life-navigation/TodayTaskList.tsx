import React, { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import type { LifeTask } from '../../types/lifeNavigation';
import { useTheme } from '../../hooks/useTheme';

type Props = {
    tasks: LifeTask[];
    expandedTaskId: string | null;
    onCollapseTask: () => void;
    renderTask: (task: LifeTask) => React.ReactNode;
    disabled?: boolean;
    searchOpen?: boolean;
};
const priority = (task: LifeTask) => task.status === 'doing' ? 0 : task.role === 'main' ? 1 : task.role === 'auxiliary' ? 2 : 3;
export default function TodayTaskList({ tasks, expandedTaskId, onCollapseTask, renderTask, disabled = false, searchOpen = false }: Props) {
    const { c } = useTheme();
    const [showFinished, setShowFinished] = useState(false);
    const [query, setQuery] = useState('');
    useEffect(() => { if (!searchOpen) setQuery(''); }, [searchOpen]);
    const term = searchOpen ? query.trim().toLowerCase() : '';
    const matches = (task: LifeTask) => [task.title, task.criterion, task.result, task.root_cause, task.improvement].some(value => value.toLowerCase().includes(term));
    const matchingTasks = term ? tasks.filter(matches) : tasks;
    const retainedEditor = Boolean(term && tasks.some(task => task.id === expandedTaskId && !matches(task)));
    const visibleTasks = term ? tasks.filter(task => matches(task) || task.id === expandedTaskId) : tasks;
    const dailyPending = tasks.filter(task => task.status === 'planned' || task.status === 'doing');
    const pending = visibleTasks.filter(task => task.status === 'planned' || task.status === 'doing').sort((a, b) => priority(a) - priority(b));
    const finished = visibleTasks.filter(task => task.status === 'done' || task.status === 'skipped');
    const completedCount = finished.filter(task => task.status === 'done').length;
    const unknownCount = dailyPending.filter(task => task.estimated_minutes === null).length;
    const estimated = dailyPending.reduce((sum, task) => sum + (task.estimated_minutes ?? 0), 0);
    const summary = !dailyPending.length ? '当日暂无待办' : [
        `待办 ${dailyPending.length}`,
        dailyPending.length > unknownCount ? `${unknownCount ? '已估' : '预计'} ${estimated} 分` : '',
        unknownCount ? `${unknownCount} 项未估时` : '',
    ].filter(Boolean).join(' · ');
    const hasExpandedFinished = finished.some(task => task.id === expandedTaskId);
    const finishedVisible = Boolean(term) || showFinished || hasExpandedFinished;
    function toggleFinished() {
        setShowFinished(!finishedVisible);
        if (hasExpandedFinished) onCollapseTask();
    }
    return <View style={{gap:8}}>
        {searchOpen && <View style={{flexDirection:'row',alignItems:'center',gap:4}}>
            <TextInput accessibilityLabel="搜索当日任务" placeholder="标题、标准、结果与复盘" placeholderTextColor={c.labelSecondary}
                value={query} onChangeText={setQuery} editable={!disabled} autoFocus autoCorrect={false} autoCapitalize="none" returnKeyType="search" maxLength={200}
                style={{flex:1,minWidth:0,minHeight:44,paddingHorizontal:8,paddingVertical:6,borderWidth:1,borderColor:c.separator,borderRadius:8,fontSize:13,lineHeight:18,color:c.labelPrimary}}/>
            {!!query && <Pressable accessibilityRole="button" accessibilityLabel="清空任务搜索" disabled={disabled} onPress={()=>setQuery('')}
                style={{minWidth:44,minHeight:44,justifyContent:'center',alignItems:'center',opacity:disabled?0.5:1}}><Text style={{fontSize:12,color:c.brand}}>清空</Text></Pressable>}
        </View>}
        {!!tasks.length && <Text style={{fontSize:12,lineHeight:16,color:c.labelSecondary}}>{summary}</Text>}
        {!!term && <Text accessibilityLiveRegion="polite" style={{fontSize:12,lineHeight:16,color:c.labelSecondary}}>{`匹配 ${matchingTasks.length} / 当日 ${tasks.length}`}</Text>}
        {retainedEditor && <Text style={{fontSize:12,lineHeight:16,color:c.labelSecondary}}>保留正在编辑的任务</Text>}
        {!tasks.length && <Text style={{fontSize:13,lineHeight:18,color:c.labelSecondary}}>还没有个人安排。</Text>}
        {!!tasks.length && !visibleTasks.length && <Text style={{fontSize:13,lineHeight:18,color:c.labelSecondary}}>当日没有匹配任务</Text>}
        {pending.map(renderTask)}
        {!!finished.length && <>
            {term ? <Text style={{fontSize:12,lineHeight:16,color:c.labelSecondary}}>已完成 {completedCount} · 已跳过 {finished.length-completedCount}</Text> : <Pressable accessibilityRole="button" accessibilityLabel={finishedVisible?'收起已结束任务':'展开已结束任务'}
                accessibilityState={{expanded:finishedVisible,disabled}} aria-expanded={finishedVisible} disabled={disabled} onPress={toggleFinished}
                style={{minHeight:44,flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8,paddingHorizontal:2,opacity:disabled?0.5:1}}>
                <Text style={{fontSize:12,lineHeight:16,color:c.labelSecondary}}>已完成 {completedCount} · 已跳过 {finished.length-completedCount}</Text>
                <Text style={{fontSize:12,lineHeight:16,color:c.brand}}>{finishedVisible?'收起 ▴':'展开 ▾'}</Text>
            </Pressable>}
            {finishedVisible && finished.map(renderTask)}
        </>}
    </View>;
}
