/**
 * /llm-preference — 用户级 LLM 模型偏好 (2026-05-13)
 *
 * 跟 /admin-llm 区别:
 *   - /admin-llm = admin 全局切换, 进程级, 重启失效, 影响所有用户
 *   - /llm-preference = 个人偏好, 持久化到 user_profiles.llm_model_id, 只影响自己
 *
 * 优先级 (后端 factory.create_provider_for_user):
 *   user > admin global > settings 默认.
 *
 * Admin 用户额外能从顶部按钮进 /admin-llm.
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, RefreshControl, Alert, TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

interface ModelOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning';
  note: string;
}

interface PreferenceResponse {
  model_id: string | null;
  options: ModelOption[];
}

const TIER_LABEL: Record<string, string> = {
  fast: '快',
  balanced: '均衡',
  reasoning: '推理',
};

const TIER_COLOR: Record<string, string> = {
  fast: '#30D158',
  balanced: '#0A84FF',
  reasoning: '#BF5AF2',
};

export default function LlmPreferenceScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const { user } = useAuth();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();
  const isAdmin = (user as any)?.is_admin === true;

  const { data, isLoading, isRefetching, refetch, error } = useQuery<PreferenceResponse>({
    queryKey: ['llm-preference'],
    queryFn: () => api.get('/me/llm-preference').then(r => r.data),
    staleTime: 30_000,
  });

  const updateMut = useMutation({
    mutationFn: (model_id: string | null) =>
      api.put<PreferenceResponse>('/me/llm-preference', { model_id }),
    onSuccess: (resp, model_id) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.setQueryData(['llm-preference'], resp.data);
      const lbl = model_id
        ? data?.options.find(m => m.id === model_id)?.label || model_id
        : '系统默认';
      Alert.alert('已切换', `当前模型: ${lbl}`);
    },
    onError: (e: any) => {
      Alert.alert('切换失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    },
  });

  const onPickModel = useCallback((m: ModelOption) => {
    if (data?.model_id === m.id) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    updateMut.mutate(m.id);
  }, [data?.model_id, updateMut]);

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}><ActivityIndicator color={c.brand} size="large" /></View>
      </SafeAreaView>
    );
  }

  if (error || !data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          </TouchableOpacity>
          <Text style={txt.title}>AI 模型</Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={styles.center}>
          <Ionicons name="alert-circle-outline" size={48} color={c.labelTertiary} />
          <Text style={[txt.empty, { marginTop: spacing.sm }]}>{(error as any)?.message || '加载失败'}</Text>
        </View>
      </SafeAreaView>
    );
  }

  const activeId = data.model_id;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>AI 模型</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
      >
        {/* 当前状态卡 */}
        <View style={styles.card}>
          <Text style={txt.sectionLabel}>当前我的选择</Text>
          <Text style={txt.activeLabel}>
            {activeId
              ? data.options.find(m => m.id === activeId)?.label || activeId
              : '系统默认'}
          </Text>
          <Text style={txt.hint}>
            {activeId
              ? '只对我自己的对话生效, 不影响其他用户.'
              : '走 admin 全局或服务器默认配置.'}
          </Text>
          {activeId && (
            <TouchableOpacity
              style={styles.resetBtn}
              onPress={() => updateMut.mutate(null)}
              disabled={updateMut.isPending}
            >
              <Text style={[txt.btnLabel, { color: c.labelSecondary }]}>恢复默认</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* 可选模型列表 */}
        {data.options.map(m => (
          <TouchableOpacity
            key={m.id}
            style={[styles.modelCard, m.id === activeId && styles.modelCardActive]}
            onPress={() => onPickModel(m)}
            activeOpacity={0.7}
            disabled={updateMut.isPending}
          >
            <View style={styles.modelHeader}>
              <View style={[styles.tierBadge, { backgroundColor: `${TIER_COLOR[m.speed_tier]}20` }]}>
                <Text style={[txt.tierText, { color: TIER_COLOR[m.speed_tier] }]}>
                  {TIER_LABEL[m.speed_tier]}
                </Text>
              </View>
              <Text style={txt.modelLabel}>{m.label}</Text>
              {m.id === activeId && (
                <Ionicons name="checkmark-circle" size={18} color={c.brand} style={{ marginLeft: 'auto' }} />
              )}
            </View>
            <Text style={txt.providerLine}>{m.provider} · {m.model}</Text>
            {!!m.note && <Text style={txt.note}>{m.note}</Text>}
          </TouchableOpacity>
        ))}

        {data.options.length === 0 && (
          <Text style={[txt.empty, { textAlign: 'center', marginTop: spacing.md }]}>
            暂无可用模型, 请联系管理员配置 API Key.
          </Text>
        )}

        {/* admin 进阶入口 */}
        {isAdmin && (
          <TouchableOpacity
            style={styles.adminBtn}
            onPress={() => router.push('/admin-llm' as any)}
            activeOpacity={0.7}
          >
            <Ionicons name="settings-outline" size={16} color={c.labelSecondary} />
            <Text style={[txt.btnLabel, { color: c.labelSecondary, marginLeft: 6 }]}>
              全局管理 (admin)
            </Text>
          </TouchableOpacity>
        )}
      </ScrollView>
    </SafeAreaView>
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
    scroll: { padding: spacing.md, gap: spacing.md, paddingBottom: 100 },
    center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      padding: spacing.md, gap: spacing.xs,
    },
    resetBtn: {
      alignSelf: 'flex-start', marginTop: spacing.xs,
      paddingHorizontal: 10, paddingVertical: 4,
      backgroundColor: c.fill, borderRadius: radii.sm,
    },
    modelCard: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: 4,
      borderWidth: 1, borderColor: 'transparent',
    },
    modelCardActive: {
      borderColor: c.brand, backgroundColor: c.brandLight,
    },
    modelHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    tierBadge: {
      paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6,
    },
    adminBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      paddingVertical: 10, marginTop: spacing.lg,
      backgroundColor: c.fill, borderRadius: radii.md,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
    sectionLabel: { fontSize: 12, color: c.labelSecondary, fontWeight: '500' } as TextStyle,
    activeLabel: { fontSize: 18, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    hint: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    btnLabel: { fontSize: 13, fontWeight: '500' } as TextStyle,
    modelLabel: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    providerLine: { fontSize: 11, color: c.labelTertiary, fontFamily: 'monospace' } as TextStyle,
    note: { fontSize: 12, color: c.labelSecondary } as TextStyle,
    tierText: { fontSize: 10, fontWeight: '600' } as TextStyle,
    empty: { fontSize: 13, color: c.labelTertiary } as TextStyle,
  };
}
