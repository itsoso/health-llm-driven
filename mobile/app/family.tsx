/**
 * 家庭健康仪表盘 (G 产品改进 MVP).
 *
 * 现状: 后端 family API 全齐 (groups/members/dashboard/switch/...) 但 mobile 完全未暴露.
 * MVP: 建一个只读的家庭页 — 看到所有家庭成员的关键指标 + 告警计数.
 *      后续迭代: 邀请流 / 切换视角 / 跨成员告警路由.
 *
 * 入口: settings → 家庭健康
 */
import React, { useMemo, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator, RefreshControl, Alert, Modal, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import {
  fetchFamilyDashboard, createFamilyInvitation, acceptFamilyInvitation,
  createFamilyGroup, type FamilyMember,
} from '../services/family';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { sharePlainText } from '../utils/share';

const RELATIONSHIP_ZH: Record<string, string> = {
  self: '我',
  father: '爸爸',
  mother: '妈妈',
  spouse: '配偶',
  child: '孩子',
  sibling: '兄弟姐妹',
  other: '其他',
};

export default function FamilyScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['familyDashboard'],
    queryFn: fetchFamilyDashboard,
    staleTime: 60_000,
  });

  const members = data?.members || [];
  const hasGroup = !!data?.group_name;

  // 邀请家人 (主人侧): 拉码 → 系统 share sheet 让用户分享给微信
  const inviteMut = useMutation({
    mutationFn: createFamilyInvitation,
    onSuccess: async (resp) => {
      const minutes = Math.floor(resp.expires_in_seconds / 60);
      const text = `加入我的家庭健康"${resp.group_name}"。打开阿衡 → 设置 → 家庭健康 → 输入邀请码：${resp.code}（${minutes} 分钟内有效）`;
      try {
        await sharePlainText({ title: '家庭健康邀请', message: text });
      } catch {
        // 分享失败仍弹码让用户手动复制
        Alert.alert(
          `邀请码: ${resp.code}`,
          `${minutes} 分钟内有效。让家人在阿衡 → 设置 → 家庭健康 → 输入邀请码`,
        );
      }
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.detail || e?.message || '请稍后再试';
      // 没建组先建一个 (常见场景: 用户第一次用)
      if (String(msg).includes('请先创建家庭组')) {
        Alert.prompt?.(
          '给你的家庭起个名',
          '比如"我家"或者"妈妈的家"',
          async (name) => {
            if (!name) return;
            try {
              await createFamilyGroup(name);
              await qc.invalidateQueries({ queryKey: ['familyDashboard'] });
              inviteMut.mutate();  // 建完再创建邀请
            } catch {
              Alert.alert('创建失败');
            }
          },
        );
      } else {
        Alert.alert('生成邀请码失败', String(msg));
      }
    },
  });

  // 输入码加入 (家人侧): RN Alert.prompt 收码 + 关系
  const handleAcceptInvite = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (!Alert.prompt) {
      Alert.alert('请升级 iOS 版本', 'Alert.prompt 仅 iOS 支持. 后续我们做表单 modal.');
      return;
    }
    Alert.prompt(
      '输入邀请码',
      '6 位字符的邀请码（家人发给你的）',
      async (code) => {
        if (!code) return;
        const cleanCode = code.trim().toUpperCase();
        // 第二步: 选关系
        Alert.alert(
          '你和对方的关系是？',
          undefined,
          [
            { text: '爸爸', onPress: () => doAccept(cleanCode, 'father') },
            { text: '妈妈', onPress: () => doAccept(cleanCode, 'mother') },
            { text: '配偶', onPress: () => doAccept(cleanCode, 'spouse') },
            { text: '其他', onPress: () => doAccept(cleanCode, 'other') },
            { text: '取消', style: 'cancel' },
          ],
        );
      },
      'plain-text',
    );
  };

  const doAccept = async (code: string, relType: string) => {
    try {
      const resp = await acceptFamilyInvitation(code, relType);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      Alert.alert('已加入', resp.message);
      qc.invalidateQueries({ queryKey: ['familyDashboard'] });
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '请稍后再试';
      Alert.alert('加入失败', String(msg));
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>家庭健康</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isFetching} onRefresh={() => { refetch(); }} tintColor={c.brand} />}
      >
        {/* G Phase 2: 邀请操作区 */}
        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.actionBtn, { backgroundColor: c.brandLight }]}
            onPress={() => inviteMut.mutate()}
            disabled={inviteMut.isPending}
            activeOpacity={0.7}
          >
            {inviteMut.isPending ? (
              <ActivityIndicator size="small" color={c.brand} />
            ) : (
              <Ionicons name="person-add-outline" size={18} color={c.brand} />
            )}
            <Text style={[txt.actionLabel, { color: c.brand }]}>
              {hasGroup ? '邀请家人' : '创建并邀请'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, { backgroundColor: c.fill }]}
            onPress={handleAcceptInvite}
            activeOpacity={0.7}
          >
            <Ionicons name="enter-outline" size={18} color={c.labelPrimary} />
            <Text style={[txt.actionLabel, { color: c.labelPrimary }]}>输入邀请码</Text>
          </TouchableOpacity>
        </View>

        {data?.group_name && (
          <Text style={txt.groupName}>{data.group_name}</Text>
        )}

        {isLoading ? (
          <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
        ) : members.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="people-outline" size={48} color={c.labelTertiary} />
            <Text style={txt.emptyTitle}>还没有家庭成员</Text>
            <Text style={txt.emptyHint}>
              添加家庭成员后, 可以在这里查看他们的健康概况.
              {'\n'}支持父母 / 配偶 / 孩子等多种关系.
            </Text>
            <Text style={[txt.emptyHint, { color: c.labelTertiary, marginTop: spacing.md }]}>
              点上方"邀请家人"生成邀请码, 让家人输入加入.
            </Text>
          </View>
        ) : (
          <View style={styles.list}>
            {members.map((m) => (
              <MemberCard key={m.user_id} member={m} c={c} />
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function MemberCard({ member, c }: { member: FamilyMember; c: ColorPalette }) {
  const styles = createStyles(c);
  const txt = createTxt(c);

  const displayName = member.nickname || member.name || RELATIONSHIP_ZH[member.relationship_type] || '家人';
  const relTag = RELATIONSHIP_ZH[member.relationship_type] || member.relationship_type;

  const sleep = member.sleep_score;
  const sleepColor = sleep == null ? c.labelTertiary : sleep >= 80 ? c.green : sleep >= 60 ? c.amber : c.red;

  const rhr = member.resting_hr;
  const rhrColor = rhr == null ? c.labelTertiary : rhr <= 60 ? c.green : rhr <= 70 ? c.amber : c.red;

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.avatar}>
          <Text style={txt.avatarText}>{displayName.slice(0, 1)}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={txt.memberName}>{displayName}</Text>
          <Text style={txt.relTag}>{relTag}{member.is_managed ? ' · 由你代管' : ''}</Text>
        </View>
        {member.unread_alerts > 0 && (
          <View style={styles.alertBadge}>
            <Ionicons name="warning" size={12} color="#fff" />
            <Text style={txt.alertBadgeText}>{member.unread_alerts}</Text>
          </View>
        )}
      </View>

      <View style={styles.metricsGrid}>
        <Metric c={c} label="睡眠" value={sleep != null ? `${sleep}` : '-'} unit="分" color={sleepColor} icon="moon-outline" />
        <Metric c={c} label="静息心率" value={rhr != null ? `${rhr}` : '-'} unit="bpm" color={rhrColor} icon="heart-outline" />
        <Metric c={c} label="今日步数" value={member.today_steps != null ? `${(member.today_steps / 1000).toFixed(1)}k` : '-'} unit="" color={c.labelPrimary} icon="walk-outline" />
        <Metric c={c} label="饮水" value={`${(member.today_water_ml / 1000).toFixed(1)}L`} unit="" color={c.blue} icon="water-outline" />
        {member.latest_weight != null && (
          <Metric c={c} label="最近体重" value={`${member.latest_weight.toFixed(1)}`} unit="kg" color={c.labelPrimary} icon="scale-outline" />
        )}
      </View>
    </View>
  );
}

function Metric({ c, label, value, unit, color, icon }: { c: ColorPalette; label: string; value: string; unit: string; color: string; icon: keyof typeof Ionicons.glyphMap }) {
  const styles = createStyles(c);
  const txt = createTxt(c);
  return (
    <View style={styles.metricCell}>
      <Ionicons name={icon} size={14} color={c.labelSecondary} />
      <Text style={txt.metricLabel}>{label}</Text>
      <Text style={[txt.metricValue, { color }]}>
        {value}
        {unit ? <Text style={txt.metricUnit}>{` ${unit}`}</Text> : null}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 40, alignItems: 'flex-start' },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },
    center: { paddingTop: 80, alignItems: 'center' },
    empty: { paddingTop: 60, alignItems: 'center', paddingHorizontal: spacing.lg },
    list: { gap: spacing.md, paddingTop: spacing.sm },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.sm, ...shadows.subtle,
    },
    cardHeader: {
      flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    },
    avatar: {
      width: 44, height: 44, borderRadius: 22,
      backgroundColor: c.brandLight,
      alignItems: 'center', justifyContent: 'center',
    },
    alertBadge: {
      flexDirection: 'row', alignItems: 'center', gap: 3,
      backgroundColor: c.red, paddingHorizontal: 8, paddingVertical: 3,
      borderRadius: 10,
    },
    metricsGrid: {
      flexDirection: 'row', flexWrap: 'wrap',
      gap: spacing.sm, marginTop: 4,
    },
    metricCell: {
      minWidth: '30%', flex: 1,
      gap: 2,
    },
    actionRow: {
      flexDirection: 'row',
      gap: spacing.sm,
      paddingTop: spacing.sm,
      paddingBottom: spacing.xs,
    },
    actionBtn: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      paddingVertical: 12,
      paddingHorizontal: spacing.sm,
      borderRadius: radii.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    groupName: { fontSize: 13, color: c.labelSecondary, paddingVertical: spacing.sm } as TextStyle,
    emptyTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, marginTop: spacing.md } as TextStyle,
    emptyHint: { fontSize: 13, color: c.labelSecondary, lineHeight: 20, textAlign: 'center', marginTop: spacing.xs } as TextStyle,
    avatarText: { fontSize: 18, fontWeight: '600', color: c.brand } as TextStyle,
    memberName: { fontSize: 16, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    relTag: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    alertBadgeText: { fontSize: 11, color: '#fff', fontWeight: '600' } as TextStyle,
    metricLabel: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    metricValue: { fontSize: 16, fontWeight: '600' } as TextStyle,
    metricUnit: { fontSize: 11, fontWeight: '400', color: c.labelTertiary } as TextStyle,
    actionLabel: { fontSize: 14, fontWeight: '600' } as TextStyle,
  };
}
