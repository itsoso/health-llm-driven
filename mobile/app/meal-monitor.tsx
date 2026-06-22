import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { Stack, useFocusEffect, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  getRokidIntegrationStatus,
  takeRokidPhotoBase64,
} from '../modules/rokid-bridge';
import { MealDraftSummary } from '../components/meal/MealDraftSummary';
import {
  MEAL_SESSION_MAX_FRAMES,
  type MealSessionSource,
} from '../services/mealMonitoring';
import { useMealCapture, type MealCaptureResult } from '../hooks/useMealCapture';
import { radii, spacing } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

const CONSENT_BODY =
  '本次用视觉 AI 分析餐食,照片 7 天后删除、不用于训练、不做实时"吃多少"指导(只餐后记录与观察)。开始?';

// 眼镜经 BLE 回传单张照片可达 25s,且 native 完成闭包无超时——给宽裕超时,超时降级手机相机。
const ROKID_PHOTO_CAPTURE_TIMEOUT_MS = 25000;

async function takeRokidPhotoBase64WithTimeout(options: {
  width: number;
  height: number;
  quality: number;
}): Promise<Record<string, unknown>> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<Record<string, unknown>>((resolve) => {
    timer = setTimeout(() => resolve({ ok: false, reason: 'rokid_photo_timeout' }), ROKID_PHOTO_CAPTURE_TIMEOUT_MS);
  });
  try {
    return await Promise.race([takeRokidPhotoBase64(options), timeout]);
  } finally {
    if (timer) {
      clearTimeout(timer);
    }
  }
}

function readString(result: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = result[key];
    if (typeof value === 'string' && value.length > 0) {
      return value;
    }
  }
  return undefined;
}

export default function MealMonitorScreen() {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const [consentGiven, setConsentGiven] = useState(false);
  const [phoneFallbackActive, setPhoneFallbackActive] = useState(false);
  const sourceRef = useRef<MealSessionSource>('rokid_glasses');

  // 顺序采样:每帧先试眼镜拍照,失败/超时/眼镜未就绪 → 手机相机兜底(像 rokid-health)。
  const captureFrame = useCallback(async (): Promise<MealCaptureResult> => {
    const capturedAt = new Date().toISOString();
    // 1) 眼镜可用时优先眼镜拍照。
    let glassesReady = false;
    try {
      const status = await getRokidIntegrationStatus();
      glassesReady = status?.platform === 'ios'
        && status?.sdkLinked === true
        && status?.iosBleConnected !== false
        && status?.customViewRunning === true;
    } catch {
      glassesReady = false;
    }
    if (glassesReady) {
      const result = await takeRokidPhotoBase64WithTimeout({ width: 1024, height: 768, quality: 80 });
      if (result.ok !== false) {
        const base64 = readString(result, ['base64', 'imageBase64', 'image_base64']);
        const uri = readString(result, ['imageUri', 'image_uri', 'uri', 'localUri', 'path']);
        if (base64 || uri) {
          sourceRef.current = 'rokid_glasses';
          setPhoneFallbackActive(false);
          return { frame: { imageBase64: base64, imageUri: uri, capturedAt } };
        }
      }
    }
    // 2) 手机相机兜底。
    setPhoneFallbackActive(true);
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      return { frame: null, reason: '需要相机权限才能采样餐食' };
    }
    const shot = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.6, base64: true });
    if (shot.canceled || !shot.assets?.[0]) {
      return { frame: null, reason: '已取消拍照，停止采样' };
    }
    const asset = shot.assets[0];
    sourceRef.current = 'phone';
    return {
      frame: { imageBase64: asset.base64 ?? undefined, imageUri: asset.uri, capturedAt },
    };
  }, []);

  const { state, startSession, finish, confirm, abort, abortOnUnmount } = useMealCapture({
    source: sourceRef.current,
    captureFrame,
  });

  // 离屏/返回时若会话仍 active → abort,原始帧立即清除(镜像 rokid-health 卸载清理)。
  useFocusEffect(
    useCallback(
      () => () => {
        abortOnUnmount();
      },
      [abortOnUnmount],
    ),
  );

  const onStart = useCallback(() => {
    if (!consentGiven) {
      return;
    }
    void startSession(true);
  }, [consentGiven, startSession]);

  const onConfirm = useCallback(() => {
    void confirm();
  }, [confirm]);

  const onAbort = useCallback(() => {
    Alert.alert('放弃这餐?', '将丢弃草稿并立即清除原始照片。', [
      { text: '取消', style: 'cancel' },
      { text: '放弃', style: 'destructive', onPress: () => void abort() },
    ]);
  }, [abort]);

  const isMonitoring = state.phase === 'monitoring' || state.phase === 'starting';
  const isDraft = state.phase === 'draft' && state.summary != null;
  const showConsentGate = state.phase === 'idle' || state.phase === 'error';

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
        <Text style={styles.title}>监控这餐</Text>
        <View style={styles.iconButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {showConsentGate ? (
          <View style={styles.panel}>
            <View style={styles.consentIcon}>
              <Ionicons name="restaurant-outline" size={22} color={c.brand} />
            </View>
            <Text style={styles.panelTitle}>视觉分析说明</Text>
            <Text style={styles.consentBody}>{CONSENT_BODY}</Text>
            <Pressable
              onPress={() => setConsentGiven((prev) => !prev)}
              style={styles.consentToggle}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: consentGiven }}
              accessibilityLabel="我已了解并同意"
            >
              <Ionicons
                name={consentGiven ? 'checkbox' : 'square-outline'}
                size={22}
                color={consentGiven ? c.brand : c.labelTertiary}
              />
              <Text style={styles.consentToggleText}>我已了解并同意上述说明</Text>
            </Pressable>
            <Pressable
              onPress={onStart}
              disabled={!consentGiven}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                !consentGiven && styles.disabledButton,
              ]}
              accessibilityRole="button"
              accessibilityLabel="开始监控这餐"
            >
              <Ionicons name="play" size={17} color="#fff" />
              <Text style={styles.primaryButtonText}>开始监控这餐</Text>
            </Pressable>
            {state.phase === 'error' && state.message ? (
              <Text style={[styles.message, { color: s.danger.fg }]}>{state.message}</Text>
            ) : null}
          </View>
        ) : null}

        {isMonitoring ? (
          <View style={styles.panel}>
            <View style={styles.liveHeader}>
              <ActivityIndicator size="small" color={c.brand} />
              <Text style={styles.liveTitle}>
                {state.phase === 'starting' ? '正在开始…' : '采样中'}
              </Text>
            </View>
            <View style={styles.frameStat}>
              <Text style={styles.frameCount}>{state.frameCount}</Text>
              <Text style={styles.frameCountLabel}>/ {MEAL_SESSION_MAX_FRAMES} 帧</Text>
            </View>
            <Text style={styles.liveMeta}>
              {phoneFallbackActive ? '手机相机采样' : '眼镜采样'}
              {state.lastFrameAt ? ` · 最近一帧 ${new Date(state.lastFrameAt).toLocaleTimeString()}` : ''}
            </Text>
            {state.reachedFrameCap ? (
              <Text style={[styles.message, { color: s.success.fg }]}>已采够样本</Text>
            ) : null}
            {state.message ? <Text style={styles.message}>{state.message}</Text> : null}
            <Pressable
              onPress={() => void finish()}
              disabled={state.frameCount === 0}
              style={({ pressed }) => [
                styles.primaryButton,
                pressed && styles.pressed,
                state.frameCount === 0 && styles.disabledButton,
              ]}
              accessibilityRole="button"
              accessibilityLabel="结束并分析"
            >
              <Ionicons name="checkmark-done" size={17} color="#fff" />
              <Text style={styles.primaryButtonText}>结束并分析</Text>
            </Pressable>
            <Pressable
              onPress={onAbort}
              style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="放弃这餐"
            >
              <Ionicons name="close" size={16} color={c.labelSecondary} />
              <Text style={styles.secondaryButtonText}>放弃</Text>
            </Pressable>
          </View>
        ) : null}

        {state.phase === 'finishing' ? (
          <View style={styles.panel}>
            <ActivityIndicator size="small" color={c.brand} />
            <Text style={styles.liveTitle}>正在分析这餐…</Text>
          </View>
        ) : null}

        {isDraft && state.summary ? (
          <>
            <MealDraftSummary summary={state.summary} />
            <View style={styles.panel}>
              <Pressable
                onPress={onConfirm}
                disabled={state.isBusy}
                style={({ pressed }) => [
                  styles.primaryButton,
                  pressed && styles.pressed,
                  state.isBusy && styles.disabledButton,
                ]}
                accessibilityRole="button"
                accessibilityLabel="确认记录这餐"
              >
                <Ionicons name="save-outline" size={17} color="#fff" />
                <Text style={styles.primaryButtonText}>确认记录这餐</Text>
              </Pressable>
              <Pressable
                onPress={onAbort}
                disabled={state.isBusy}
                style={({ pressed }) => [styles.secondaryButton, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="放弃这餐"
              >
                <Ionicons name="trash-outline" size={16} color={c.labelSecondary} />
                <Text style={styles.secondaryButtonText}>放弃</Text>
              </Pressable>
            </View>
          </>
        ) : null}

        {state.phase === 'confirmed' ? (
          <View style={styles.panel}>
            <View style={styles.consentIcon}>
              <Ionicons name="checkmark-circle" size={22} color={s.success.solid} />
            </View>
            <Text style={styles.panelTitle}>已记录这餐</Text>
            <Pressable
              onPress={() => router.back()}
              style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
              accessibilityRole="button"
            >
              <Text style={styles.primaryButtonText}>完成</Text>
            </Pressable>
          </View>
        ) : null}

        {state.phase === 'confirming' || state.phase === 'aborting' ? (
          <View style={styles.panel}>
            <ActivityIndicator size="small" color={c.brand} />
            <Text style={styles.liveTitle}>{state.phase === 'confirming' ? '记录中…' : '清除中…'}</Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
    },
    iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
    title: { fontSize: 17, fontWeight: '700', color: c.labelPrimary },
    content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxxl },
    panel: { backgroundColor: c.bgCard, borderRadius: radii.lg, padding: spacing.lg, gap: spacing.md },
    consentIcon: {
      width: 44,
      height: 44,
      borderRadius: radii.full,
      backgroundColor: c.tintGreen,
      alignItems: 'center',
      justifyContent: 'center',
    },
    panelTitle: { fontSize: 17, fontWeight: '700', color: c.labelPrimary },
    consentBody: { fontSize: 15, lineHeight: 23, color: c.labelSecondary },
    consentToggle: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    consentToggleText: { fontSize: 14, color: c.labelPrimary, flex: 1 },
    primaryButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      backgroundColor: c.brand,
      borderRadius: radii.md,
      paddingVertical: spacing.md,
    },
    primaryButtonText: { fontSize: 16, fontWeight: '700', color: '#fff' },
    secondaryButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.sm,
      borderRadius: radii.md,
      paddingVertical: spacing.sm,
    },
    secondaryButtonText: { fontSize: 14, fontWeight: '600', color: c.labelSecondary },
    disabledButton: { opacity: 0.45 },
    pressed: { opacity: 0.85 },
    liveHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    liveTitle: { fontSize: 16, fontWeight: '700', color: c.labelPrimary },
    frameStat: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing.xs },
    frameCount: { fontSize: 44, fontWeight: '700', color: c.brand, fontVariant: ['tabular-nums'], lineHeight: 48 },
    frameCountLabel: { fontSize: 16, color: c.labelTertiary, marginBottom: spacing.sm },
    liveMeta: { fontSize: 13, color: c.labelTertiary },
    message: { fontSize: 14, lineHeight: 20, color: c.labelSecondary },
  });
}
