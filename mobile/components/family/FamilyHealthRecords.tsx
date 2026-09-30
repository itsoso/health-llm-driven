import React, { useEffect } from 'react';
import { ActivityIndicator, AppState, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { fetchFamilyMemberHealth, FAMILY_RELATIONSHIPS } from '../../services/family';
import type { ColorPalette } from '../../hooks/useTheme';
import { radii, spacing } from '../../constants/theme';

const STATUS: Record<string, string> = { active: '进行中', improving: '好转中', recovering: '恢复中', recovered: '已恢复', resolved: '已结束', chronic: '持续观察' };
const ABNORMAL: Record<string, string> = { high: '偏高', low: '偏低', abnormal: '异常' };

function conclusionText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object') return '';
  const item = value as Record<string, unknown>;
  return ['title', 'description', 'content', 'text', 'recommendation']
    .map(key => item[key]).filter((text): text is string => typeof text === 'string').join(' · ');
}

/** Data remains ephemeral and uses the viewer's session, never a proxy token. */
export default function FamilyHealthRecords({ userId, viewerId, c }: { userId: number; viewerId: number; c: ColorPalette }) {
  const query = useQuery({
    queryKey: ['familyMemberHealth', viewerId, userId],
    queryFn: () => fetchFamilyMemberHealth(userId),
    staleTime: 0,
    gcTime: 0,
    retry: false,
    refetchInterval: 30_000,
    meta: { persist: false },
  });
  const { refetch } = query;
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') void refetch();
    });
    return () => subscription.remove();
  }, [refetch]);
  const styles = StyleSheet.create({
    content: { padding: spacing.md, gap: spacing.md },
    card: { backgroundColor: c.bgCard, borderRadius: radii.md, padding: spacing.md, gap: spacing.sm },
    title: { fontSize: 18, fontWeight: '600', color: c.labelPrimary },
    text: { fontSize: 14, color: c.labelPrimary, lineHeight: 21 },
    hint: { fontSize: 13, color: c.labelSecondary, lineHeight: 20 },
    item: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator, paddingTop: spacing.sm, gap: spacing.xs },
    button: { padding: spacing.md, alignItems: 'center' },
  });
  if (query.isPending) return <View style={styles.content}><ActivityIndicator color={c.brand} /><Text style={styles.hint}>正在读取共享健康记录…</Text></View>;
  // Check error before cached data: a revoked grant must never keep old records visible.
  if (query.isError) {
    const status = (query.error as { response?: { status?: number } }).response?.status;
    return <View style={styles.content}>
      <Text style={styles.text}>{status === 403 || status === 404 ? '暂时无法查看，家庭关系或共享权限可能已变更。' : '健康记录加载失败，请检查网络后重试。'}</Text>
      <TouchableOpacity accessibilityRole="button" style={styles.button} onPress={() => { void query.refetch(); }}><Text style={{ color: c.brand }}>重试</Text></TouchableOpacity>
    </View>;
  }
  const { member, reports, episodes, limit } = query.data;
  const name = member.name || member.nickname || '家人';
  const identity = member.nickname && member.name && member.nickname !== member.name ? `${name}（${member.nickname}）` : name;
  return <ScrollView contentContainerStyle={styles.content}>
    <Text style={styles.title}>{identity}</Text>
    <Text style={styles.hint}>{FAMILY_RELATIONSHIPS[member.relationship_type] || '家人'} · 只读健康记录</Text>
    <Text style={styles.hint}>当前仍使用你的账号。这里展示家人已共享的原始记录，不修改报告或用药。</Text>
    <Text style={styles.title}>检查报告</Text>
    {!reports.length && <Text style={styles.hint}>暂无检查报告</Text>}
    {reports.map(report => <View key={report.id} style={styles.card}>
      <Text style={styles.text}>{report.exam_date} · {report.hospital_name || '检查报告'}</Text>
      {report.overall_assessment ? <Text style={styles.text}>{report.overall_assessment}</Text> : null}
      {report.notes ? <Text style={styles.text}>{report.notes}</Text> : null}
      {(report.conclusions || []).map((value, index) => {
        const text = conclusionText(value);
        return text ? <Text key={index} style={styles.text}>{text}</Text> : null;
      })}
      {report.items.map(item => <View key={item.id} style={styles.item}>
        <Text style={styles.text}>{item.item_name}</Text>
        <Text style={[styles.text, ABNORMAL[item.is_abnormal || ''] ? { color: c.red } : null]}>{item.display_value}{item.unit ? ` ${item.unit}` : ''}</Text>
        {ABNORMAL[item.is_abnormal || ''] ? <Text style={{ color: c.red }}>{ABNORMAL[item.is_abnormal || '']}</Text> : null}
        {item.reference_range ? <Text style={styles.hint}>参考范围：{item.reference_range}</Text> : null}
        {item.notes ? <Text style={styles.hint}>{item.notes}</Text> : null}
      </View>)}
    </View>)}
    <Text style={styles.title}>病程与近况</Text>
    {!episodes.length && <Text style={styles.hint}>暂无病程记录</Text>}
    {episodes.map(episode => <View key={episode.id} style={styles.card}>
      <Text style={styles.text}>{episode.name} · {STATUS[episode.status] || episode.status}</Text>
      <Text style={styles.hint}>{episode.start_date}{episode.end_date ? ` 至 ${episode.end_date}` : ' 起'}</Text>
      {episode.severity != null && <Text style={styles.hint}>记录的严重程度：{episode.severity}/10</Text>}
      {episode.notes ? <Text style={styles.text}>{episode.notes}</Text> : null}
      {episode.updates.map(update => <View key={update.id} style={styles.item}>
        <Text style={styles.hint}>{update.update_date}{update.status ? ` · ${STATUS[update.status] || update.status}` : ''}</Text>
        {update.severity != null && <Text style={styles.hint}>记录的严重程度：{update.severity}/10</Text>}
        {update.notes ? <Text style={styles.text}>{update.notes}</Text> : null}
      </View>)}
    </View>)}
    {(reports.length >= limit || episodes.length >= limit) && <Text style={styles.hint}>当前展示最近 {limit} 份报告和 {limit} 条病程。</Text>}
  </ScrollView>;
}
