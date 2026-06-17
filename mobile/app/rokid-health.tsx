import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextStyle,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  getRokidIntegrationStatus,
  type RokidIntegrationStatus,
} from '../modules/rokid-bridge';
import {
  listRokidGlanceCards,
  openRokidCompanionIfAvailable,
} from '../services/rokidAmbient';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

type PrivacyMode = 'private' | 'workplace' | 'public';
type OpenState = 'idle' | 'opening' | 'opened' | 'unavailable' | 'failed';

type RokidGlanceCard = {
  id?: string | number;
  title?: string;
  text?: string;
  summary?: string;
  action_text?: string;
  priority?: string;
  priority_tier?: string;
};

const PRIVACY_MODES: Array<{ key: PrivacyMode; label: string; description: string }> = [
  { key: 'private', label: '私密', description: '可保留原始素材, 仍需主动触发' },
  { key: 'workplace', label: '办公', description: '默认保留摘要和 hash' },
  { key: 'public', label: '公共', description: '默认不保留原图和原音频' },
];

const CAPTURE_ACTIONS = [
  { icon: 'fast-food-outline', title: '食物视觉记录', detail: '拍菜单 / 餐盘后生成饮食草稿' },
  { icon: 'nutrition-outline', title: '补剂标签扫描', detail: 'OCR 后进入补剂待确认队列' },
  { icon: 'medkit-outline', title: '用药标签扫描', detail: '只做识别和安全提示, 不自动改药' },
] as const;

function statusLabel(status?: RokidIntegrationStatus) {
  if (!status) {
    return {
      hiRokid: '检测中',
      bridge: 'Bridge 检测中',
      sdk: 'SDK 检测中',
    };
  }
  return {
    hiRokid: status.hiRokidInstalled ? 'Hi Rokid 已安装' : '未检测到 Hi Rokid',
    bridge: status.bridgeAvailable ? 'Bridge 已就绪' : 'Bridge 未就绪',
    sdk: status.sdkLinked ? 'SDK 已链接' : 'SDK 未链接',
  };
}

function cardTitle(card: RokidGlanceCard) {
  return card.title || card.action_text || card.text || card.summary || `GlanceCard ${card.id ?? ''}`.trim();
}

export default function RokidHealthScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>('workplace');
  const [openState, setOpenState] = useState<OpenState>('idle');

  const statusQuery = useQuery({
    queryKey: ['rokid-health', 'status'],
    queryFn: getRokidIntegrationStatus,
    staleTime: 30_000,
  });
  const glanceQuery = useQuery({
    queryKey: ['rokid-health', 'glance-cards'],
    queryFn: listRokidGlanceCards,
    staleTime: 30_000,
  });

  const status = statusQuery.data;
  const labels = statusLabel(status);
  const glanceCards = Array.isArray(glanceQuery.data)
    ? (glanceQuery.data as RokidGlanceCard[])
    : [];
  const isRefreshing = statusQuery.isRefetching || glanceQuery.isRefetching;

  const refresh = () => {
    statusQuery.refetch();
    glanceQuery.refetch();
  };

  const openCompanion = async () => {
    setOpenState('opening');
    try {
      const result = await openRokidCompanionIfAvailable();
      setOpenState(result.opened ? 'opened' : 'unavailable');
      await statusQuery.refetch();
    } catch {
      setOpenState('failed');
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="返回"
          hitSlop={10}
        >
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </Pressable>
        <Text style={txt.title}>Rokid 眼镜健康模式</Text>
        <Pressable
          onPress={refresh}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="刷新 Rokid 状态"
          hitSlop={10}
        >
          <Ionicons name="refresh" size={20} color={c.labelSecondary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={refresh} />}
      >
        <View style={styles.panel}>
          <View style={styles.panelHeader}>
            <View style={styles.panelIcon}>
              <Ionicons name="scan-outline" size={20} color={c.brand} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.panelTitle}>Ambient capture surface</Text>
              <Text style={txt.panelSub}>眼镜只负责低摩擦捕获和短提示, 决策仍回到 Reva Health OS。</Text>
            </View>
          </View>

          <View style={styles.statusGrid}>
            <StatusPill label={labels.hiRokid} ok={status?.hiRokidInstalled === true} />
            <StatusPill label={labels.bridge} ok={status?.bridgeAvailable === true} />
            <StatusPill label={labels.sdk} ok={status?.sdkLinked === true} muted={!status?.sdkLinked} />
          </View>

          <Pressable
            onPress={openCompanion}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed,
              openState === 'opening' && styles.disabledButton,
            ]}
            disabled={openState === 'opening'}
            accessibilityRole="button"
          >
            <Ionicons name="open-outline" size={17} color="#fff" />
            <Text style={txt.primaryButton}>{openState === 'opening' ? '打开中...' : '打开 Hi Rokid'}</Text>
          </Pressable>

          {openState !== 'idle' && openState !== 'opening' ? (
            <Text style={[
              txt.openState,
              openState === 'opened' ? { color: s.success.solid } : { color: s.warning.solid },
            ]}>
              {openState === 'opened' ? '已请求打开 Hi Rokid' : '当前设备无法打开 Hi Rokid'}
            </Text>
          ) : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>隐私模式</Text>
          <View style={styles.segmentRow}>
            {PRIVACY_MODES.map((mode) => {
              const active = mode.key === privacyMode;
              return (
                <Pressable
                  key={mode.key}
                  onPress={() => setPrivacyMode(mode.key)}
                  style={[styles.segment, active && { backgroundColor: c.brand }]}
                  accessibilityRole="button"
                >
                  <Text style={[txt.segmentText, active && { color: '#fff' }]}>{mode.label}</Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={txt.privacyDesc}>
            {PRIVACY_MODES.find((mode) => mode.key === privacyMode)?.description}
          </Text>
          <BoundaryRow icon="radio-button-on-outline" text="仅主动触发拍照 / 录音" />
          <BoundaryRow icon="business-outline" text="办公 / 公共场景默认保留摘要和 hash" />
          <BoundaryRow icon="shield-checkmark-outline" text="用药和补剂只生成待确认草稿" />
        </View>

        <View style={styles.panel}>
          <View style={styles.sectionHeader}>
            <Text style={txt.sectionTitle}>待投递短提示</Text>
            {glanceQuery.isLoading ? <ActivityIndicator size="small" color={c.labelTertiary} /> : null}
          </View>
          {glanceQuery.isError ? (
            <Text style={txt.empty}>GlanceCard 加载失败, 下拉重试。</Text>
          ) : glanceCards.length === 0 ? (
            <Text style={txt.empty}>暂无 Rokid glasses surface 的行动卡。</Text>
          ) : (
            glanceCards.map((card, index) => (
              <View key={`${card.id ?? index}`} style={styles.glanceRow}>
                <View style={styles.glanceIndex}>
                  <Text style={txt.glanceIndex}>{index + 1}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={txt.glanceTitle} numberOfLines={2}>{cardTitle(card)}</Text>
                  <Text style={txt.glanceMeta} numberOfLines={1}>
                    {card.priority || card.priority_tier || 'manual_confirm'}
                  </Text>
                </View>
              </View>
            ))
          )}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>捕获动作</Text>
          <Text style={txt.sectionHint}>真实 SDK 未链接前, 这里只展示 Reva 对眼镜入口的安全合同。</Text>
          {CAPTURE_ACTIONS.map((action) => (
            <View key={action.title} style={styles.captureRow}>
              <View style={styles.captureIcon}>
                <Ionicons name={action.icon} size={18} color={c.brand} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={txt.captureTitle}>{action.title}</Text>
                <Text style={txt.captureDetail}>{action.detail}</Text>
              </View>
              <Text style={txt.captureStatus}>待 SDK 真机</Text>
            </View>
          ))}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>最近捕获</Text>
          <Text style={txt.empty}>等待主动触发。不会连续录音或后台拍摄。</Text>
          {status?.installedPackage ? (
            <Text style={txt.technical}>Hi Rokid package: {status.installedPackage}</Text>
          ) : null}
          {status?.iosSdkCompatibility ? (
            <Text style={txt.technical}>{status.iosSdkCompatibility}</Text>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );

  function StatusPill({
    label,
    ok,
    muted = false,
  }: {
    label: string;
    ok: boolean;
    muted?: boolean;
  }) {
    const color = ok ? s.success.solid : muted ? c.labelTertiary : s.warning.solid;
    const bg = ok ? s.success.bg : muted ? c.fill : s.warning.bg;
    return (
      <View style={[styles.statusPill, { backgroundColor: bg }]}>
        <View style={[styles.statusDot, { backgroundColor: color }]} />
        <Text style={[txt.statusPill, { color }]} numberOfLines={1}>{label}</Text>
      </View>
    );
  }

  function BoundaryRow({ icon, text }: { icon: keyof typeof Ionicons.glyphMap; text: string }) {
    return (
      <View style={styles.boundaryRow}>
        <Ionicons name={icon} size={15} color={c.labelSecondary} />
        <Text style={txt.boundaryText}>{text}</Text>
      </View>
    );
  }
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  content: {
    padding: spacing.lg,
    paddingBottom: 110,
  },
  panel: {
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
    padding: spacing.lg,
    marginBottom: spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
  },
  panelHeader: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  panelIcon: {
    width: 40,
    height: 40,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brandLight,
  },
  statusGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: spacing.md,
  },
  statusPill: {
    minHeight: 30,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  primaryButton: {
    minHeight: 44,
    borderRadius: radii.sm,
    backgroundColor: c.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  pressed: { opacity: 0.82 },
  disabledButton: { opacity: 0.55 },
  segmentRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  segment: {
    flex: 1,
    minHeight: 34,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boundaryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: spacing.sm,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  glanceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  glanceIndex: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  captureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
  },
  captureIcon: {
    width: 30,
    height: 30,
    borderRadius: radii.sm,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  panelTitle: { fontSize: 17, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  panelSub: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 3 } as TextStyle,
  primaryButton: { fontSize: 15, fontWeight: '800', color: '#fff' } as TextStyle,
  openState: { fontSize: 12, fontWeight: '700', marginTop: spacing.sm, textAlign: 'center' } as TextStyle,
  sectionTitle: { fontSize: 15, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  sectionHint: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 4, marginBottom: spacing.sm } as TextStyle,
  statusPill: { fontSize: 12, fontWeight: '800', maxWidth: 140 } as TextStyle,
  segmentText: { fontSize: 13, fontWeight: '800', color: c.labelSecondary } as TextStyle,
  privacyDesc: { fontSize: 12, color: c.labelSecondary, lineHeight: 17, marginBottom: spacing.xs } as TextStyle,
  boundaryText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.labelSecondary } as TextStyle,
  empty: { fontSize: 13, lineHeight: 19, color: c.labelTertiary } as TextStyle,
  glanceIndex: { fontSize: 12, fontWeight: '800', color: c.brand } as TextStyle,
  glanceTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary, lineHeight: 19 } as TextStyle,
  glanceMeta: { fontSize: 11, color: c.labelTertiary, fontWeight: '700', marginTop: 2 } as TextStyle,
  captureTitle: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  captureDetail: { fontSize: 12, color: c.labelSecondary, lineHeight: 17, marginTop: 2 } as TextStyle,
  captureStatus: { fontSize: 11, color: c.labelTertiary, fontWeight: '800' } as TextStyle,
  technical: { fontSize: 11, color: c.labelTertiary, marginTop: spacing.sm, lineHeight: 16 } as TextStyle,
});
