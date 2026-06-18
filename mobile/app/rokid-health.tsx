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
  getRokidDeviceValidationSteps,
  getRokidIntegrationStatus,
  openRokidRevaCustomView,
  requestRokidAuthorization,
  takeRokidPhotoBase64,
  type RokidDeviceValidationStep,
  type RokidIntegrationStatus,
} from '../modules/rokid-bridge';
import {
  listRokidGlanceCards,
  openRokidCompanionIfAvailable,
  submitRokidVisualInput,
  type RokidVisualIntent,
} from '../services/rokidAmbient';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

type PrivacyMode = 'private' | 'workplace' | 'public';
type OpenState = 'idle' | 'opening' | 'opened' | 'unavailable' | 'failed';
type CaptureStatus = 'idle' | 'capturing' | 'submitted' | 'failed';
type SessionStatus = 'idle' | 'running' | 'ready' | 'waiting' | 'failed';

type CaptureState = {
  status: CaptureStatus;
  actionTitle?: string;
  message?: string;
};

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

const CAPTURE_ACTIONS: Array<{
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  detail: string;
  intent: RokidVisualIntent;
}> = [
  { icon: 'fast-food-outline', title: '食物视觉记录', detail: '拍菜单 / 餐盘后生成饮食草稿', intent: 'food_scan' },
  { icon: 'nutrition-outline', title: '补剂标签扫描', detail: 'OCR 后进入补剂待确认队列', intent: 'supplement_scan' },
  { icon: 'medkit-outline', title: '用药标签扫描', detail: '只做识别和安全提示, 不自动改药', intent: 'medication_scan' },
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

function readString(result: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'string' && value.length > 0) {
      return value;
    }
  }
  return undefined;
}

function iosAuthorizationLabel(status?: RokidIntegrationStatus) {
  switch (status?.authorizationState) {
    case 'authenticated':
      return '已授权';
    case 'authenticating':
      return '授权中';
    case 'expired':
      return '授权过期';
    case 'failed':
      return '授权失败';
    default:
      return '未授权';
  }
}

function isRecoverableRokidAuthorizationDelay(reason?: string) {
  if (!reason) {
    return false;
  }
  const normalized = reason.toLowerCase();
  return normalized.includes('鉴权请求超时')
    || normalized.includes('rgcxrclientautherror code=-1')
    || normalized.includes('authorization_callback_pending')
    || normalized.includes('authorization request timed out')
    || normalized.includes('request timeout')
    || normalized.includes('timeout');
}

function formatRokidAuthorizationIssue(reason?: string) {
  if (isRecoverableRokidAuthorizationDelay(reason)) {
    return '鉴权请求超时: Hi Rokid 未在等待窗口内回调 Reva';
  }
  return reason ?? 'authorization_failed';
}

function buildAuthDiagnosticLines(status?: RokidIntegrationStatus) {
  const lines: string[] = [];
  if (!status) {
    return lines;
  }
  if (status.lastAuthorizationError) {
    lines.push(`最近授权错误: ${formatRokidAuthorizationIssue(status.lastAuthorizationError)}`);
  }
  if (status.lastAuthorizationRequestAt) {
    lines.push(`最近授权请求: ${status.lastAuthorizationRequestAt}`);
  }
  if (typeof status.authorizationRequestTimeoutSeconds === 'number') {
    lines.push(`SDK 等待窗口: ${Math.round(status.authorizationRequestTimeoutSeconds)} 秒`);
  }
  if (status.lastCallbackAt) {
    lines.push(`最近回调: ${status.lastCallbackHandled ? 'SDK 已处理' : 'SDK 未确认'} · ${status.lastCallbackAt}`);
  } else if (status.lastAuthorizationError && isRecoverableRokidAuthorizationDelay(status.lastAuthorizationError)) {
    lines.push('最近回调: 尚未进入 Reva');
  }
  return lines;
}

export default function RokidHealthScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>('workplace');
  const [openState, setOpenState] = useState<OpenState>('idle');
  const [captureState, setCaptureState] = useState<CaptureState>({ status: 'idle' });
  const [sessionState, setSessionState] = useState<{
    status: SessionStatus;
    message?: string;
  }>({ status: 'idle' });

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
  const isIOS = status?.platform === 'ios';
  const iosCapabilitiesReady = isIOS && status?.capabilitiesReady === true;
  const validationSteps = useMemo(() => getRokidDeviceValidationSteps(status), [status]);
  const authDiagnosticLines = useMemo(() => buildAuthDiagnosticLines(status), [status]);
  const isRefreshing = statusQuery.isRefetching || glanceQuery.isRefetching;

  const refresh = () => {
    statusQuery.refetch();
    glanceQuery.refetch();
  };

  const settleRokidAuthorizationStatus = async (attempts: number) => {
    let latest = statusQuery.data;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const refreshed = await statusQuery.refetch();
      latest = refreshed.data ?? latest;
      if (latest?.authorizationState === 'authenticated') {
        break;
      }
    }
    return latest;
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

  const authorizeRokid = async () => {
    setSessionState({ status: 'running', message: 'Rokid 授权中...' });
    try {
      const result = await requestRokidAuthorization({
        appName: 'Reva',
        scopes: ['device_control', 'audio_stream'],
      });
      if (result.ok === false) {
        const reason = typeof result.reason === 'string' ? result.reason : 'rokid_authorization_failed';
        const settledStatus = await settleRokidAuthorizationStatus(3);
        if (settledStatus?.authorizationState === 'authenticated') {
          setSessionState({ status: 'ready', message: 'Rokid 已授权' });
          return;
        }
        if (isRecoverableRokidAuthorizationDelay(reason)) {
          setSessionState({
            status: 'waiting',
            message: '等待 Rokid 授权回调。请在 Hi Rokid 完成授权后回到 Reva 并点刷新; 若仍超时, 继续点授权重试。',
          });
          return;
        }
        throw new Error(reason);
      }
      await settleRokidAuthorizationStatus(1);
      setSessionState({ status: 'ready', message: 'Rokid 已授权' });
    } catch (error) {
      setSessionState({
        status: 'failed',
        message: `Rokid 授权失败: ${error instanceof Error ? error.message : 'authorization_failed'}`,
      });
    }
  };

  const openRevaCustomView = async () => {
    setSessionState({ status: 'running', message: '正在打开 Reva 眼镜视图...' });
    try {
      const result = await openRokidRevaCustomView({
        title: 'Reva Health',
        body: '等待 Reva 投递下一条健康行动',
        priority: 'manual_confirm',
      });
      if (result.ok === false) {
        throw new Error(typeof result.reason === 'string' ? result.reason : 'rokid_custom_view_failed');
      }
      setSessionState({ status: 'ready', message: 'Reva 眼镜视图已打开' });
      await statusQuery.refetch();
    } catch (error) {
      setSessionState({
        status: 'failed',
        message: `Reva 眼镜视图失败: ${error instanceof Error ? error.message : 'custom_view_failed'}`,
      });
    }
  };

  const handleVisualCapture = async (action: (typeof CAPTURE_ACTIONS)[number]) => {
    setCaptureState({ status: 'capturing', actionTitle: action.title, message: `${action.title}提交中...` });
    try {
      if (status?.platform === 'ios' && status.capabilitiesReady !== true) {
        throw new Error('rokid_custom_view_not_ready');
      }
      const captureResult = await takeRokidPhotoBase64({ width: 1024, height: 768, quality: 80 });
      if (captureResult.ok === false) {
        throw new Error(
          typeof captureResult.reason === 'string' ? captureResult.reason : 'rokid_capture_failed',
        );
      }

      await submitRokidVisualInput({
        intent: action.intent,
        imageUri: readString(captureResult, ['imageUri', 'image_uri', 'uri', 'localUri', 'path']),
        imageSha256: readString(captureResult, ['imageSha256', 'image_sha256', 'sha256']),
        privacyClass: 'health_l3',
        meta: {
          privacy_mode: privacyMode,
          source_surface: 'rokid_health_mode',
          raw_media_retained: false,
          manual_confirm_required: true,
        },
      });

      setCaptureState({
        status: 'submitted',
        actionTitle: action.title,
        message: `已提交${action.title}草稿`,
      });
    } catch (error) {
      setCaptureState({
        status: 'failed',
        actionTitle: action.title,
        message: `${action.title}失败: ${error instanceof Error ? error.message : 'capture_failed'}`,
      });
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

          {isIOS ? (
            <View style={styles.iosSessionBox}>
              <View style={styles.statusGrid}>
                <StatusPill
                  label={iosAuthorizationLabel(status)}
                  ok={status?.authorizationState === 'authenticated'}
                  muted={!status?.authorizationState || status.authorizationState === 'not_authenticated'}
                />
                <StatusPill
                  label={status?.customViewRunning ? 'CustomView 运行中' : 'CustomView 未运行'}
                  ok={status?.customViewRunning === true}
                  muted={!status?.customViewRunning}
                />
                <StatusPill
                  label={iosCapabilitiesReady ? '能力已就绪' : '能力未就绪'}
                  ok={iosCapabilitiesReady}
                  muted={!iosCapabilitiesReady}
                />
              </View>
              <View style={styles.buttonRow}>
                <Pressable
                  onPress={authorizeRokid}
                  disabled={!status?.sdkLinked || sessionState.status === 'running'}
                  style={({ pressed }) => [
                    styles.secondaryButton,
                    pressed && styles.pressed,
                    (!status?.sdkLinked || sessionState.status === 'running') && styles.disabledButton,
                  ]}
                  accessibilityRole="button"
                >
                  <Ionicons name="key-outline" size={16} color={c.brand} />
                  <Text style={txt.secondaryButton}>授权 Rokid</Text>
                </Pressable>
                <Pressable
                  onPress={openRevaCustomView}
                  disabled={!status?.sdkLinked || sessionState.status === 'running'}
                  style={({ pressed }) => [
                    styles.secondaryButton,
                    pressed && styles.pressed,
                    (!status?.sdkLinked || sessionState.status === 'running') && styles.disabledButton,
                  ]}
                  accessibilityRole="button"
                >
                  <Ionicons name="browsers-outline" size={16} color={c.brand} />
                  <Text style={txt.secondaryButton}>打开 Reva 眼镜视图</Text>
                </Pressable>
              </View>
              {sessionState.message ? (
                <Text style={[
                  txt.sessionMessage,
                  sessionState.status === 'ready' ? { color: s.success.solid } : null,
                  sessionState.status === 'waiting' ? { color: c.brand } : null,
                  sessionState.status === 'failed' ? { color: s.warning.solid } : null,
                ]}>
                  {sessionState.message}
                </Text>
              ) : null}

              {authDiagnosticLines.length > 0 ? (
                <View style={styles.authDiagnosticBox}>
                  {authDiagnosticLines.map((line) => (
                    <Text key={line} style={txt.authDiagnostic} numberOfLines={3}>{line}</Text>
                  ))}
                </View>
              ) : null}

              <View style={styles.validationBox}>
                <Text style={txt.validationHeading}>真机验证</Text>
                {validationSteps.map((step) => {
                  const tone = validationTone(step);
                  return (
                    <View key={step.id} style={styles.validationRow}>
                      <View style={[styles.validationIcon, { backgroundColor: tone.bg }]}>
                        <Ionicons name={validationIcon(step.status)} size={16} color={tone.fg} />
                      </View>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <View style={styles.validationTitleRow}>
                          <Text style={txt.validationTitle} numberOfLines={1}>{step.title}</Text>
                          {step.status === 'next' && step.actionLabel ? (
                            <Text style={txt.validationNext} numberOfLines={1}>
                              下一步: {step.actionLabel}
                            </Text>
                          ) : null}
                        </View>
                        <Text style={txt.validationDetail} numberOfLines={2}>{step.detail}</Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            </View>
          ) : null}

          {openState !== 'idle' && openState !== 'opening' ? (
            <Text style={[
              txt.openState,
              openState === 'opened' ? { color: s.success.solid } : { color: s.warning.solid },
            ]}>
              {openState === 'opened' ? '已请求打开 Hi Rokid' : '当前设备无法打开 Hi Rokid'}
            </Text>
          ) : null}

          <Pressable
            onPress={() => router.push('/rokid-pushup-coach' as any)}
            style={({ pressed }) => [styles.featureRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="打开 Rokid 俯卧撑计数"
          >
            <View style={styles.featureIcon}>
              <Ionicons name="body-outline" size={18} color={c.orange} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={txt.featureTitle}>俯卧撑计数</Text>
              <Text style={txt.featureDetail}>眼镜视图展示计数、动作评价和下一步建议。</Text>
            </View>
            <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
          </Pressable>
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
          <Text style={txt.sectionHint}>每次点击只触发一次拍照, 生成待确认草稿; 不连续录音、不后台拍摄。</Text>
          {CAPTURE_ACTIONS.map((action) => (
            <Pressable
              key={action.title}
              onPress={() => handleVisualCapture(action)}
              disabled={captureState.status === 'capturing'}
              style={({ pressed }) => [
                styles.captureRow,
                pressed && styles.pressed,
                captureState.status === 'capturing' && styles.disabledButton,
              ]}
              accessibilityRole="button"
              accessibilityLabel={`主动触发 ${action.title}`}
            >
              <View style={styles.captureIcon}>
                <Ionicons name={action.icon} size={18} color={c.brand} />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={txt.captureTitle}>{action.title}</Text>
                <Text style={txt.captureDetail}>{action.detail}</Text>
              </View>
              <Text style={txt.captureStatus}>
                {captureState.status === 'capturing' && captureState.actionTitle === action.title ? '提交中' : '主动触发'}
              </Text>
            </Pressable>
          ))}
          {captureState.message ? (
            <Text style={[
              txt.captureMessage,
              captureState.status === 'submitted' ? { color: s.success.solid } : null,
              captureState.status === 'failed' ? { color: s.warning.solid } : null,
            ]}>
              {captureState.message}
            </Text>
          ) : null}
        </View>

        <View style={styles.panel}>
          <Text style={txt.sectionTitle}>最近捕获</Text>
          <Text style={txt.empty}>
            {captureState.message ? `最近状态: ${captureState.message}` : '等待主动触发。不会连续录音或后台拍摄。'}
          </Text>
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

  function validationIcon(status: RokidDeviceValidationStep['status']): keyof typeof Ionicons.glyphMap {
    switch (status) {
      case 'done':
        return 'checkmark-circle';
      case 'blocked':
        return 'alert-circle';
      case 'next':
        return 'radio-button-on';
      default:
        return 'ellipse-outline';
    }
  }

  function validationTone(step: RokidDeviceValidationStep) {
    switch (step.status) {
      case 'done':
        return { fg: s.success.solid, bg: s.success.bg };
      case 'blocked':
        return { fg: s.warning.solid, bg: s.warning.bg };
      case 'next':
        return { fg: c.brand, bg: c.brandLight };
      default:
        return { fg: c.labelTertiary, bg: c.fill };
    }
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
  iosSessionBox: {
    marginTop: spacing.sm,
  },
  buttonRow: {
    flexDirection: 'column',
    gap: 8,
  },
  validationBox: {
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    paddingTop: spacing.md,
    gap: 10,
  },
  authDiagnosticBox: {
    marginTop: spacing.sm,
    borderRadius: radii.sm,
    backgroundColor: c.fill,
    padding: spacing.sm,
    gap: 4,
  },
  validationRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  validationIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  validationTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  secondaryButton: {
    minHeight: 42,
    borderRadius: radii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: c.separator,
    backgroundColor: c.fill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: spacing.sm,
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
  featureRow: {
    marginTop: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: c.separator,
    paddingTop: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  featureIcon: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    backgroundColor: c.tintOrange,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  panelTitle: { fontSize: 17, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  panelSub: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 3 } as TextStyle,
  primaryButton: { fontSize: 15, fontWeight: '800', color: '#fff' } as TextStyle,
  secondaryButton: { fontSize: 12, fontWeight: '800', color: c.brand, textAlign: 'center' } as TextStyle,
  openState: { fontSize: 12, fontWeight: '700', marginTop: spacing.sm, textAlign: 'center' } as TextStyle,
  sessionMessage: { fontSize: 12, fontWeight: '700', marginTop: spacing.sm, textAlign: 'center' } as TextStyle,
  authDiagnostic: { fontSize: 11, fontWeight: '700', color: c.labelSecondary, lineHeight: 16 } as TextStyle,
  validationHeading: { fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationTitle: { flex: 1, fontSize: 13, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  validationNext: { fontSize: 11, fontWeight: '800', color: c.brand, maxWidth: 140 } as TextStyle,
  validationDetail: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 2 } as TextStyle,
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
  captureMessage: { fontSize: 12, fontWeight: '700', lineHeight: 17, marginTop: spacing.sm } as TextStyle,
  featureTitle: { fontSize: 14, fontWeight: '800', color: c.labelPrimary } as TextStyle,
  featureDetail: { fontSize: 12, lineHeight: 17, color: c.labelSecondary, marginTop: 2 } as TextStyle,
  technical: { fontSize: 11, color: c.labelTertiary, marginTop: spacing.sm, lineHeight: 16 } as TextStyle,
});
