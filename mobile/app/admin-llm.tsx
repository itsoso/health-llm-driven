/**
 * Admin LLM 模型管理页 — /admin-llm
 *
 * 列出 backend `/admin/llm/models`, 显示当前 active + 每个的可用性 (env 是否齐),
 * 点一行就切到那个模型 (`/admin/llm/select-model`).
 * 每行带"测延迟"按钮 → `/admin/llm/benchmark/<id>` 跑 3 次取平均.
 *
 * Admin only — 后端有 get_admin_user 守门, 非 admin 看到 403.
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
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

interface ModelInfo {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning';
  note: string;
  available: boolean;
  is_active: boolean;
}

interface ModelListResponse {
  active_id: string | null;
  fallback_provider: string;
  fallback_model: string;
  models: ModelInfo[];
}

interface BenchmarkResponse {
  model_id: string;
  label: string;
  runs: number;
  latency_ms: number[];
  avg_ms: number;
  ok: boolean;
  sample_reply: string;
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

export default function AdminLlmScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();
  const [benchmarks, setBenchmarks] = useState<Record<string, BenchmarkResponse>>({});
  const [benchingId, setBenchingId] = useState<string | null>(null);

  const { data, isLoading, isRefetching, refetch, error } = useQuery<ModelListResponse>({
    queryKey: ['admin-llm-models'],
    queryFn: () => api.get('/admin/llm/models').then(r => r.data),
    staleTime: 30_000,
  });

  const selectMut = useMutation({
    mutationFn: (model_id: string | null) => api.post('/admin/llm/select-model', { model_id }),
    onSuccess: (resp, model_id) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ['admin-llm-models'] });
      Alert.alert('已切换', model_id ? `当前模型: ${(resp.data as any)?.label || model_id}` : '已恢复默认');
    },
    onError: (e: any) => {
      Alert.alert('切换失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    },
  });

  const runBenchmark = useCallback(async (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setBenchingId(id);
    try {
      const resp = await api.post<BenchmarkResponse>(`/admin/llm/benchmark/${id}?runs=3`);
      setBenchmarks(prev => ({ ...prev, [id]: resp.data }));
    } catch (e: any) {
      Alert.alert('测试失败', e?.response?.data?.detail || e?.message || '');
    } finally {
      setBenchingId(null);
    }
  }, []);

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}><ActivityIndicator color={c.brand} size="large" /></View>
      </SafeAreaView>
    );
  }

  if (error || !data) {
    const msg = (error as any)?.response?.status === 403
      ? '需要 admin 权限'
      : (error as any)?.message || '加载失败';
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
          </TouchableOpacity>
          <Text style={txt.title}>LLM 模型</Text>
          <View style={{ width: 40 }} />
        </View>
        <View style={styles.center}>
          <Ionicons name="alert-circle-outline" size={48} color={c.labelTertiary} />
          <Text style={[txt.empty, { marginTop: spacing.sm }]}>{msg}</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>LLM 模型 (admin)</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />}
      >
        {/* 当前状态卡 */}
        <View style={styles.card}>
          <Text style={txt.sectionLabel}>当前生效</Text>
          <Text style={txt.activeLabel}>
            {data.active_id
              ? data.models.find(m => m.id === data.active_id)?.label || data.active_id
              : `默认 (${data.fallback_provider} · ${data.fallback_model})`}
          </Text>
          {data.active_id && (
            <TouchableOpacity
              style={styles.resetBtn}
              onPress={() => selectMut.mutate(null)}
              disabled={selectMut.isPending}
            >
              <Text style={[txt.btnLabel, { color: c.labelSecondary }]}>恢复默认</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* 模型列表 */}
        {data.models.map(m => {
          const bench = benchmarks[m.id];
          const isBenching = benchingId === m.id;
          return (
            <TouchableOpacity
              key={m.id}
              style={[styles.modelCard, m.is_active && styles.modelCardActive, !m.available && styles.modelCardDisabled]}
              onPress={() => {
                if (!m.available) {
                  Alert.alert('不可用', '该模型缺少 API Key, 请先在 .env-online 配置');
                  return;
                }
                if (m.is_active) return;
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                selectMut.mutate(m.id);
              }}
              activeOpacity={m.available ? 0.7 : 1}
            >
              <View style={styles.modelHeader}>
                <View style={[styles.tierBadge, { backgroundColor: `${TIER_COLOR[m.speed_tier]}20` }]}>
                  <Text style={[txt.tierText, { color: TIER_COLOR[m.speed_tier] }]}>
                    {TIER_LABEL[m.speed_tier]}
                  </Text>
                </View>
                <Text style={txt.modelLabel}>{m.label}</Text>
                {m.is_active && (
                  <Ionicons name="checkmark-circle" size={18} color={c.brand} style={{ marginLeft: 'auto' }} />
                )}
                {!m.available && (
                  <Ionicons name="lock-closed" size={14} color={c.labelTertiary} style={{ marginLeft: 'auto' }} />
                )}
              </View>

              <Text style={txt.providerLine}>
                {m.provider} · {m.model}
              </Text>
              {!!m.note && <Text style={txt.note}>{m.note}</Text>}

              {/* benchmark 行 */}
              {bench ? (
                <View style={styles.benchRow}>
                  <Text style={[txt.benchText, { color: bench.ok ? c.green : c.red }]}>
                    平均 {bench.avg_ms.toFixed(0)}ms · 3 次: {bench.latency_ms.map(l => `${l}ms`).join(' / ')}
                  </Text>
                  {bench.sample_reply && (
                    <Text style={txt.benchReply} numberOfLines={1}>"{bench.sample_reply}"</Text>
                  )}
                </View>
              ) : null}

              <TouchableOpacity
                style={styles.benchBtn}
                onPress={() => runBenchmark(m.id)}
                disabled={!m.available || isBenching}
                hitSlop={8}
              >
                {isBenching ? (
                  <ActivityIndicator size="small" color={c.brand} />
                ) : (
                  <>
                    <Ionicons name="speedometer-outline" size={14} color={c.brand} />
                    <Text style={[txt.btnLabel, { color: c.brand, marginLeft: 4 }]}>
                      测延迟
                    </Text>
                  </>
                )}
              </TouchableOpacity>
            </TouchableOpacity>
          );
        })}

        <Text style={[txt.empty, { textAlign: 'center', marginTop: spacing.md }]}>
          切换是进程内的, 重启服务后回到 .env 默认.
        </Text>
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
    modelCardDisabled: {
      opacity: 0.5,
    },
    modelHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    tierBadge: {
      paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6,
    },
    benchRow: { marginTop: 4 },
    benchBtn: {
      flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
      paddingHorizontal: 10, paddingVertical: 5, borderRadius: radii.sm,
      backgroundColor: c.brandLight, marginTop: 6,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
    sectionLabel: { fontSize: 12, color: c.labelSecondary, fontWeight: '500' } as TextStyle,
    activeLabel: { fontSize: 18, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    btnLabel: { fontSize: 13, fontWeight: '500' } as TextStyle,
    modelLabel: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    providerLine: { fontSize: 11, color: c.labelTertiary, fontFamily: 'monospace' } as TextStyle,
    note: { fontSize: 12, color: c.labelSecondary } as TextStyle,
    tierText: { fontSize: 10, fontWeight: '600' } as TextStyle,
    benchText: { fontSize: 12, fontVariant: ['tabular-nums'] as const } as TextStyle,
    benchReply: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    empty: { fontSize: 13, color: c.labelTertiary } as TextStyle,
  };
}
