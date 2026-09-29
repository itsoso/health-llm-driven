import React, { useMemo, useState } from 'react';
import { View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator, RefreshControl, Alert, Modal, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchFamilyDashboard, createFamilyInvitation, acceptFamilyInvitation,
  createFamilyGroup, updateFamilyRelationship, leaveFamily, FAMILY_RELATIONSHIPS, type FamilyMember, type FamilyMembership,
} from '../services/family';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';
import { sharePlainText } from '../utils/share';
import { APP_DISPLAY_NAME } from '../constants/brand';
import { useAuth } from '../hooks/useAuth';
import FamilyHealthRecords from '../components/family/FamilyHealthRecords';
import FamilyRelationshipForm from '../components/family/FamilyRelationshipForm';

const RELATIONSHIP_ZH = FAMILY_RELATIONSHIPS;

export default function FamilyScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();
  const { user } = useAuth();
  const [selectedMember, setSelectedMember] = useState<FamilyMember | null>(null);
  const [relationshipMember, setRelationshipMember] = useState<FamilyMember | null>(null);
  const [acceptVisible, setAcceptVisible] = useState(false);
  const [createVisible, setCreateVisible] = useState(false);
  const [groupName, setGroupName] = useState('我家');
  const [creating, setCreating] = useState(false);

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['familyDashboard', user?.id],
    queryFn: fetchFamilyDashboard,
    staleTime: 0,
    gcTime: 0,
    meta: { persist: false },
  });

  const members = data?.members || [];
  const hasGroup = !!data?.group_name;

  // 邀请家人 (主人侧): 拉码 → 系统 share sheet 让用户分享给微信
  const inviteMut = useMutation({
    mutationFn: createFamilyInvitation,
    onSuccess: async (resp) => {
      const minutes = Math.floor(resp.expires_in_seconds / 60);
      const text = `加入我的家庭健康"${resp.group_name}"。打开${APP_DISPLAY_NAME} → 设置 → 家庭健康 → 输入邀请码：${resp.code}（${minutes} 分钟内有效）`;
      try {
        await sharePlainText({ title: '家庭健康邀请', message: text });
      } catch {
        // 分享失败仍弹码让用户手动复制
        Alert.alert(
          `邀请码: ${resp.code}`,
          `${minutes} 分钟内有效。让家人在${APP_DISPLAY_NAME} → 设置 → 家庭健康 → 输入邀请码`,
        );
      }
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.detail || e?.message || '请稍后再试';
      Alert.alert('生成邀请码失败', String(msg));
    },
  });

  const refreshFamily = async () => {
    qc.removeQueries({ queryKey: ['familyMemberHealth'] });
    await qc.invalidateQueries({ queryKey: ['familyDashboard'] });
  };

  const handleCreate = async () => {
    if (!groupName.trim()) return;
    setCreating(true);
    try {
      await createFamilyGroup(groupName.trim());
      setCreateVisible(false);
      await refreshFamily();
      inviteMut.mutate();
    } catch {
      Alert.alert('创建失败', '请稍后重试');
    } finally {
      setCreating(false);
    }
  };

  const handleLeave = (membership: FamilyMembership) => {
    Alert.alert(`退出${membership.group_name}并停止共享？`, '退出后，家庭创建者将无法继续查看你的共享健康记录。你的原始记录仍保留在自己的账号中。', [
      { text: '取消', style: 'cancel' },
      { text: '退出并停止共享', style: 'destructive', onPress: async () => {
        try {
          await leaveFamily(membership.member_id);
          setSelectedMember(null);
          await refreshFamily();
        } catch {
          Alert.alert('退出失败', '共享尚未撤销，请稍后重试');
        }
      } },
    ]);
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
            onPress={() => hasGroup ? inviteMut.mutate() : setCreateVisible(true)}
            disabled={inviteMut.isPending || (hasGroup && !data?.is_owner)}
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
            onPress={() => setAcceptVisible(true)}
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
        ) : isError ? (
          <View style={styles.empty}>
            <Text style={txt.emptyTitle}>家庭信息加载失败</Text>
            <TouchableOpacity accessibilityRole="button" onPress={() => { void refetch(); }}><Text style={txt.emptyHint}>重试</Text></TouchableOpacity>
          </View>
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
              <View key={m.user_id} style={{ gap: spacing.xs }}>
                <MemberCard member={m} c={c} onPress={() => setSelectedMember(m)} />
                {data?.is_owner && m.user_id !== user?.id && (
                  <TouchableOpacity accessibilityRole="button" onPress={() => setRelationshipMember(m)} style={styles.actionBtn}>
                    <Text style={{ color: c.brand }}>设置关系与昵称</Text>
                  </TouchableOpacity>
                )}

              </View>
            ))}
          </View>
        )}
        {!isError && !!data?.memberships?.length && (
          <View style={[styles.list, { marginTop: spacing.lg }]}>
            <Text style={txt.title}>我的家庭关联</Text>
            {data.memberships.map(membership => <View key={membership.member_id} style={styles.card}>
              <Text style={txt.memberName}>{membership.group_name}</Text>
              {membership.is_owner ? <Text style={txt.relTag}>你是家庭创建者</Text> : <TouchableOpacity accessibilityRole="button" accessibilityLabel={`退出${membership.group_name}并停止共享`} onPress={() => handleLeave(membership)} style={styles.actionBtn}>
                <Text style={{ color: c.red }}>退出家庭并停止共享</Text>
              </TouchableOpacity>}
            </View>)}
          </View>
        )}
      </ScrollView>
      <FamilyRelationshipForm visible={acceptVisible} c={c} mode="accept" onClose={() => setAcceptVisible(false)} onSubmit={async (relationship, nickname, code) => {
        await acceptFamilyInvitation(code!, relationship, nickname);
        setAcceptVisible(false);
        await refreshFamily();
      }} />
      <FamilyRelationshipForm visible={!!relationshipMember} c={c} mode="edit" member={relationshipMember} onClose={() => setRelationshipMember(null)} onSubmit={async (relationship, nickname) => {
        await updateFamilyRelationship(relationshipMember!.id, relationship, nickname);
        setRelationshipMember(null);
        await refreshFamily();
      }} />
      <Modal visible={!!selectedMember && !!user} animationType="slide" onRequestClose={() => setSelectedMember(null)}>
        <SafeAreaView style={styles.safe}>
          <View style={styles.header}>
            <TouchableOpacity accessibilityRole="button" accessibilityLabel="关闭健康记录" onPress={() => setSelectedMember(null)} style={styles.backBtn}><Ionicons name="chevron-back" size={26} color={c.labelPrimary} /></TouchableOpacity>
            <Text style={txt.title}>家人健康记录</Text>
          </View>
          {selectedMember && user && <FamilyHealthRecords key={`${user.id}-${selectedMember.user_id}`} viewerId={user.id} userId={selectedMember.user_id} c={c} />}
        </SafeAreaView>
      </Modal>
      <Modal visible={createVisible} animationType="slide" onRequestClose={() => { if (!creating) setCreateVisible(false); }}>
        <SafeAreaView style={styles.safe}>
          <View style={styles.scroll}>
            <Text style={txt.title}>给你的家庭起个名</Text>
            <TextInput accessibilityLabel="家庭名称" maxLength={100} value={groupName} onChangeText={setGroupName} style={{ color: c.labelPrimary, backgroundColor: c.fill, padding: spacing.md, marginVertical: spacing.md }} />
            <TouchableOpacity disabled={creating || !groupName.trim()} onPress={() => { void handleCreate(); }} style={styles.actionBtn}><Text style={{ color: c.brand }}>{creating ? '正在创建…' : '创建并邀请'}</Text></TouchableOpacity>
            <TouchableOpacity disabled={creating} onPress={() => setCreateVisible(false)} style={styles.actionBtn}><Text style={{ color: c.labelSecondary }}>取消</Text></TouchableOpacity>
          </View>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function MemberCard({ member, c, onPress }: { member: FamilyMember; c: ColorPalette; onPress: () => void }) {
  const styles = createStyles(c);
  const txt = createTxt(c);

  const displayName = member.nickname || member.name || RELATIONSHIP_ZH[member.relationship_type] || '家人';
  const relTag = RELATIONSHIP_ZH[member.relationship_type] || member.relationship_type;

  const sleep = member.sleep_score;
  const sleepColor = sleep == null ? c.labelTertiary : sleep >= 80 ? c.green : sleep >= 60 ? c.amber : c.red;

  const rhr = member.resting_hr;
  // Family members include children; do not apply adult heart-rate cutoffs.
  const rhrColor = rhr == null ? c.labelTertiary : c.labelPrimary;

  return (
    <TouchableOpacity accessibilityRole="button" accessibilityLabel={`查看${displayName}的健康记录`} disabled={!member.can_view} onPress={onPress} style={styles.card}>
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

      {member.can_view ? <View style={styles.metricsGrid}>
        <Metric c={c} label="睡眠" value={sleep != null ? `${sleep}` : '-'} unit="分" color={sleepColor} icon="moon-outline" />
        <Metric c={c} label="静息心率" value={rhr != null ? `${rhr}` : '-'} unit="bpm" color={rhrColor} icon="heart-outline" />
        <Metric c={c} label="今日步数" value={member.today_steps != null ? `${(member.today_steps / 1000).toFixed(1)}k` : '-'} unit="" color={c.labelPrimary} icon="walk-outline" />
        <Metric c={c} label="饮水" value={`${(member.today_water_ml / 1000).toFixed(1)}L`} unit="" color={c.blue} icon="water-outline" />
        {member.latest_weight != null && (
          <Metric c={c} label="最近体重" value={`${member.latest_weight.toFixed(1)}`} unit="kg" color={c.labelPrimary} icon="scale-outline" />
        )}
      </View> : <Text style={txt.relTag}>尚未向你共享健康记录</Text>}
      {member.can_view && <Text style={{ color: c.brand }}>查看检查报告与病程 ›</Text>}
    </TouchableOpacity>
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
