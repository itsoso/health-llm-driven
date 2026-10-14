import React from 'react';
import { Pressable, Text, View } from 'react-native';
import type { LifeTask } from '../../types/lifeNavigation';
import { slotLabels, statusLabels } from '../../utils/lifeNavigationModel';
import { useTheme } from '../../hooks/useTheme';

type Props = { task: LifeTask; expanded: boolean; disabled: boolean; onToggle: () => void; children: React.ReactNode };
export default function TaskCard({ task, expanded, disabled, onToggle, children }: Props) {
    const { c } = useTheme();
    const title = task.title || '未命名任务';
    const role = task.role === 'main' ? '主任务' : task.role === 'auxiliary' ? '辅助任务' : '可选任务';
    const timing = [task.estimated_minutes !== null ? `预计 ${task.estimated_minutes} 分钟` : '', task.actual_minutes !== null ? `实际 ${task.actual_minutes} 分钟` : ''].filter(Boolean).join(' · ');
    return <View style={{ borderWidth: 1, borderColor: expanded ? c.brand : c.separator, borderRadius: 8, backgroundColor: c.bgCard }}>
        <Pressable accessibilityRole="button" accessibilityLabel={`${expanded ? '收起' : '展开'}任务 ${title}`}
            accessibilityHint="展开后可编辑任务详情，修改后需保存个人安排"
            accessibilityState={{ expanded, disabled }} disabled={disabled} onPress={onToggle}
            style={{ minHeight: 60, padding: 10, gap: 4, opacity: disabled ? .5 : 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
                <Text style={{ flex: 1, fontSize: 13, lineHeight: 18, fontWeight: '600', color: c.labelPrimary }}>{title}</Text>
                <Text style={{ fontSize: 12, lineHeight: 18, color: c.labelSecondary }}>{statusLabels[task.status]}</Text>
                <Text style={{ fontSize: 12, lineHeight: 18, color: c.brand }}>{expanded ? '收起' : '编辑'}</Text>
            </View>
            <Text style={{ fontSize: 12, lineHeight: 16, color: c.labelSecondary }}>{role} · {slotLabels[task.slot]}{timing ? ` · ${timing}` : ''}</Text>
            {!expanded && task.criterion ? <Text numberOfLines={2} style={{ fontSize: 12, lineHeight: 16, color: c.labelSecondary }}>完成标准：{task.criterion}</Text> : null}
        </Pressable>
        {expanded && <View style={{ padding: 10, paddingTop: 0, gap: 8 }}>{children}</View>}
    </View>;
}
