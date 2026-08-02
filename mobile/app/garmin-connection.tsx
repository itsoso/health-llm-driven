import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Stack } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { invalidateHealthSnapshot } from '../applib/queryKeys';
import {
  deleteGarminCredentials,
  fetchGarminStatus,
  garminErrorMessage,
  saveGarminCredentials,
  setGarminSyncEnabled,
  syncGarmin,
  testGarminConnection,
  verifyGarminMfa,
  type GarminCredentialStatus,
  type GarminCredentialsInput,
} from '../services/garmin';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaSpacing,
  revaType,
} from '../constants/revaTheme';

type BusyAction = 'connect' | 'mfa' | 'sync' | 'toggle' | 'delete' | null;

function statusCopy(status: GarminCredentialStatus): { title: string; body: string; tone: string } {
  if (status.requires_mfa) {
    return {
      title: '需要两步验证',
      body: status.last_error || '重新连接后输入 Garmin 验证码，即可恢复同步。',
      tone: revaSemantic.caution.fg,
    };
  }
  if (!status.credentials_valid) {
    return {
      title: '需要重新连接',
      body: status.last_error || 'Garmin 登录状态已失效，请重新输入账号凭证。',
      tone: revaSemantic.risk.fg,
    };
  }
  if (status.sync_enabled === false) {
    return {
      title: '自动同步已暂停',
      body: '连接仍然保留，恢复后会继续自动拉取健康数据。',
      tone: revaSemantic.caution.fg,
    };
  }
  if (status.health === 'healthy') {
    return {
      title: '连接正常',
      body: status.minutes_since_last_sync == null
        ? '账号已连接，等待首次同步。'
        : `最近同步：${Math.max(0, Math.floor(status.minutes_since_last_sync))} 分钟前`,
      tone: revaSemantic.normal.fg,
    };
  }
  return {
    title: '等待数据更新',
    body: status.last_error || '连接可用，可以立即同步最近的 Garmin 数据。',
    tone: revaSemantic.caution.fg,
  };
}

function ActionButton({
  label,
  onPress,
  disabled = false,
  variant = 'primary',
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.actionButton,
        variant === 'primary' ? styles.primaryButton : null,
        variant === 'secondary' ? styles.secondaryButton : null,
        variant === 'danger' ? styles.dangerButton : null,
        disabled ? styles.disabled : null,
      ]}
    >
      <Text
        style={[
          styles.actionLabel,
          variant === 'primary' ? styles.primaryLabel : null,
          variant === 'secondary' ? styles.secondaryLabel : null,
          variant === 'danger' ? styles.dangerLabel : null,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export default function GarminConnectionScreen() {
  const queryClient = useQueryClient();
  const { data: status, isLoading, refetch } = useQuery({
    queryKey: ['garminStatus'],
    queryFn: fetchGarminStatus,
    staleTime: 30_000,
  });
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isCn, setIsCn] = useState(false);
  const [editing, setEditing] = useState(false);
  const [mfaSession, setMfaSession] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const isBusy = busy !== null;
  const showCredentialForm = !status?.bound || editing;
  const display = status?.bound ? statusCopy(status) : null;

  const refreshStatus = async () => {
    await refetch();
  };

  const connect = async () => {
    const cleanEmail = email.trim();
    if (!cleanEmail || !password) {
      setError('请输入 Garmin 邮箱和密码');
      return;
    }
    const input: GarminCredentialsInput = {
      garmin_email: cleanEmail,
      garmin_password: password,
      is_cn: isCn,
    };
    setBusy('connect');
    setError(null);
    setNotice(null);
    try {
      await saveGarminCredentials(input);
      const result = await testGarminConnection(input);
      setPassword('');
      if (result.success) {
        setEditing(false);
        setNotice('Garmin 已连接，可以开始同步。');
        await refreshStatus();
        return;
      }
      if (result.mfa_required && result.mfa_session_id) {
        setMfaSession(result.mfa_session_id);
        setNotice('Garmin 已发送验证请求，请输入 6 位验证码。');
        return;
      }
      setError(result.message || '连接失败，请检查账号和服务器区域');
    } catch (connectError) {
      setError(garminErrorMessage(connectError));
    } finally {
      setBusy(null);
    }
  };

  const verifyMfa = async () => {
    if (!mfaSession || mfaCode.length !== 6) {
      setError('请输入 6 位 Garmin 验证码');
      return;
    }
    setBusy('mfa');
    setError(null);
    try {
      const result = await verifyGarminMfa(mfaCode, mfaSession);
      if (!result.success) {
        setError(result.message || '验证码无效，请重新输入');
        return;
      }
      setMfaSession(null);
      setMfaCode('');
      setEditing(false);
      setNotice('两步验证完成，Garmin 连接已恢复。');
      await refreshStatus();
    } catch (mfaError) {
      setError(garminErrorMessage(mfaError));
    } finally {
      setBusy(null);
    }
  };

  const runSync = async () => {
    setBusy('sync');
    setError(null);
    setNotice(null);
    try {
      const result = await syncGarmin(1);
      setNotice(result.message || 'Garmin 数据已更新。');
      await invalidateHealthSnapshot(queryClient);
      await refreshStatus();
    } catch (syncError) {
      setError(garminErrorMessage(syncError));
    } finally {
      setBusy(null);
    }
  };

  const toggleSync = async () => {
    if (!status?.bound) return;
    const nextEnabled = status.sync_enabled === false;
    setBusy('toggle');
    setError(null);
    try {
      await setGarminSyncEnabled(nextEnabled);
      setNotice(nextEnabled ? 'Garmin 自动同步已恢复。' : 'Garmin 自动同步已暂停。');
      await refreshStatus();
    } catch (toggleError) {
      setError(garminErrorMessage(toggleError));
    } finally {
      setBusy(null);
    }
  };

  const confirmDelete = () => {
    Alert.alert(
      '断开 Garmin 连接',
      '将删除保存的 Garmin 凭证并停止后续同步，已同步的健康记录不会被删除。',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '断开连接',
          style: 'destructive',
          onPress: async () => {
            setBusy('delete');
            setError(null);
            try {
              await deleteGarminCredentials();
              setEmail('');
              setPassword('');
              setMfaSession(null);
              setEditing(false);
              setNotice('Garmin 连接已断开。');
              await refreshStatus();
            } catch (deleteError) {
              setError(garminErrorMessage(deleteError));
            } finally {
              setBusy(null);
            }
          },
        },
      ],
    );
  };

  return (
    <>
      <Stack.Screen
        options={{
          headerShown: true,
          title: 'Garmin 连接',
          headerBackTitle: '设置',
          headerStyle: { backgroundColor: C.paper },
          headerShadowVisible: false,
          headerTintColor: C.ink1,
        }}
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.screen}
      >
        <ScrollView
          contentInsetAdjustmentBehavior="automatic"
          automaticallyAdjustKeyboardInsets
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.content}
        >
          <View style={styles.intro}>
            <View style={styles.watchIcon}>
              <Ionicons name="watch-outline" size={28} color={C.green500} />
            </View>
            <View style={styles.introCopy}>
              <Text style={styles.eyebrow}>DATA CONNECTION</Text>
              <Text style={styles.heading}>连接 Garmin Connect</Text>
              <Text style={styles.bodyCopy}>
                加密保存登录凭证，用于同步睡眠、心率、活动和身体指标。Reva 不会在界面或日志中显示密码。
              </Text>
            </View>
          </View>

          {isLoading ? (
            <View style={styles.loadingCard}>
              <ActivityIndicator color={C.green500} />
              <Text style={styles.muted}>正在读取连接状态…</Text>
            </View>
          ) : null}

          {display && !showCredentialForm && !mfaSession ? (
            <View style={styles.statusCard}>
              <View style={styles.statusHeader}>
                <View style={[styles.statusDot, { backgroundColor: display.tone }]} />
                <Text style={styles.cardTitle}>{display.title}</Text>
              </View>
              <Text style={styles.bodyCopy}>{display.body}</Text>
              {status?.error_count ? (
                <Text style={styles.meta}>连续失败 {status.error_count} 次</Text>
              ) : null}
            </View>
          ) : null}

          {notice ? (
            <View style={styles.noticeBox}>
              <Ionicons name="checkmark-circle-outline" size={18} color={revaSemantic.normal.fg} />
              <Text style={styles.noticeText}>{notice}</Text>
            </View>
          ) : null}
          {error ? (
            <View style={styles.errorBox}>
              <Ionicons name="alert-circle-outline" size={18} color={revaSemantic.risk.fg} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          {mfaSession ? (
            <View style={styles.formCard}>
              <Text style={styles.cardTitle}>完成两步验证</Text>
              <Text style={styles.bodyCopy}>输入 Garmin 验证器或邮件中的 6 位验证码。</Text>
              <TextInput
                accessibilityLabel="Garmin 两步验证码"
                autoComplete="one-time-code"
                keyboardType="number-pad"
                maxLength={6}
                onChangeText={(value) => setMfaCode(value.replace(/\D/g, '').slice(0, 6))}
                placeholder="6 位验证码"
                placeholderTextColor={C.ink3}
                style={[styles.input, styles.codeInput]}
                value={mfaCode}
              />
              <ActionButton
                label={busy === 'mfa' ? '验证中…' : '验证并完成连接'}
                onPress={() => void verifyMfa()}
                disabled={isBusy || mfaCode.length !== 6}
              />
              <ActionButton
                label="重新输入账号"
                variant="secondary"
                disabled={isBusy}
                onPress={() => {
                  setMfaSession(null);
                  setMfaCode('');
                  setEditing(true);
                  setError(null);
                }}
              />
            </View>
          ) : null}

          {showCredentialForm && !mfaSession ? (
            <View style={styles.formCard}>
              <Text style={styles.cardTitle}>{status?.bound ? '重新连接账号' : '绑定账号'}</Text>
              <TextInput
                accessibilityLabel="Garmin 邮箱"
                autoCapitalize="none"
                autoComplete="email"
                keyboardType="email-address"
                onChangeText={setEmail}
                placeholder="Garmin 邮箱"
                placeholderTextColor={C.ink3}
                style={styles.input}
                value={email}
              />
              <TextInput
                accessibilityLabel="Garmin 密码"
                autoCapitalize="none"
                autoComplete="password"
                onChangeText={setPassword}
                onSubmitEditing={() => void connect()}
                placeholder="Garmin 密码"
                placeholderTextColor={C.ink3}
                secureTextEntry
                style={styles.input}
                value={password}
              />

              <View style={styles.regionGroup} accessibilityRole="radiogroup">
                <Pressable
                  accessibilityRole="radio"
                  accessibilityLabel="Garmin 国际服务器"
                  accessibilityState={{ selected: !isCn }}
                  onPress={() => setIsCn(false)}
                  style={[styles.regionOption, !isCn ? styles.regionOptionSelected : null]}
                >
                  <Text style={[styles.regionText, !isCn ? styles.regionTextSelected : null]}>国际版</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="radio"
                  accessibilityLabel="Garmin 中国服务器"
                  accessibilityState={{ selected: isCn }}
                  onPress={() => setIsCn(true)}
                  style={[styles.regionOption, isCn ? styles.regionOptionSelected : null]}
                >
                  <Text style={[styles.regionText, isCn ? styles.regionTextSelected : null]}>中国版</Text>
                </Pressable>
              </View>

              <ActionButton
                label={busy === 'connect' ? '连接中…' : '连接 Garmin'}
                onPress={() => void connect()}
                disabled={isBusy}
              />
              {status?.bound ? (
                <ActionButton
                  label="取消重新连接"
                  variant="secondary"
                  disabled={isBusy}
                  onPress={() => {
                    setEditing(false);
                    setPassword('');
                    setError(null);
                  }}
                />
              ) : null}
            </View>
          ) : null}

          {status?.bound && !showCredentialForm && !mfaSession ? (
            <View style={styles.actionsCard}>
              <ActionButton
                label={busy === 'sync' ? '同步中…' : '立即同步 Garmin'}
                onPress={() => void runSync()}
                disabled={isBusy || status.sync_enabled === false}
              />
              <ActionButton
                label={status.sync_enabled === false ? '恢复 Garmin 自动同步' : '暂停 Garmin 自动同步'}
                variant="secondary"
                onPress={() => void toggleSync()}
                disabled={isBusy}
              />
              <ActionButton
                label="重新连接 Garmin"
                variant="secondary"
                onPress={() => {
                  setEditing(true);
                  setNotice(null);
                  setError(null);
                }}
                disabled={isBusy}
              />
              <ActionButton
                label={busy === 'delete' ? '正在断开…' : '断开 Garmin 连接'}
                variant="danger"
                onPress={confirmDelete}
                disabled={isBusy}
              />
            </View>
          ) : null}

          <Text style={styles.privacyNote}>
            Garmin 账号密码仅加密存储在服务端，用于建立 Garmin 会话；客户端不会持久化密码或登录令牌。
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: C.paper },
  content: { padding: revaSpacing.s5, paddingBottom: revaSpacing.s10, gap: revaSpacing.s4 },
  intro: { flexDirection: 'row', alignItems: 'flex-start', gap: revaSpacing.s4 },
  introCopy: { flex: 1, gap: revaSpacing.s1 },
  watchIcon: {
    width: 52,
    height: 52,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
  },
  eyebrow: { ...revaType.overline, color: C.green600 },
  heading: { ...revaType.h2 },
  bodyCopy: { ...revaType.body2, color: C.ink2 },
  muted: { ...revaType.body2, color: C.ink3 },
  loadingCard: {
    minHeight: 96,
    alignItems: 'center',
    justifyContent: 'center',
    gap: revaSpacing.s2,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderCurve: 'continuous',
  },
  statusCard: {
    padding: revaSpacing.s5,
    gap: revaSpacing.s2,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    borderCurve: 'continuous',
  },
  statusHeader: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  statusDot: { width: 10, height: 10, borderRadius: revaRadii.pill },
  cardTitle: { ...revaType.title, color: C.ink1 },
  meta: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3 },
  noticeBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    padding: revaSpacing.s3,
    backgroundColor: revaSemantic.normal.bg,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
  },
  noticeText: { ...revaType.body2, color: revaSemantic.normal.fg, flex: 1 },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    padding: revaSpacing.s3,
    backgroundColor: revaSemantic.risk.bg,
    borderRadius: revaRadii.md,
    borderCurve: 'continuous',
  },
  errorText: { ...revaType.body2, color: revaSemantic.risk.fg, flex: 1 },
  formCard: {
    padding: revaSpacing.s5,
    gap: revaSpacing.s3,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    borderCurve: 'continuous',
  },
  input: {
    minHeight: 50,
    paddingHorizontal: revaSpacing.s4,
    color: C.ink1,
    backgroundColor: C.surface2,
    borderWidth: 1,
    borderColor: C.lineStrong,
    borderRadius: revaRadii.sm,
    borderCurve: 'continuous',
    fontFamily: revaFonts.sans,
    fontSize: 16,
  },
  codeInput: { fontFamily: revaFonts.mono, textAlign: 'center', letterSpacing: 8, fontSize: 20 },
  regionGroup: {
    flexDirection: 'row',
    padding: 3,
    gap: 3,
    backgroundColor: C.paper2,
    borderRadius: revaRadii.sm,
    borderCurve: 'continuous',
  },
  regionOption: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.xs,
    borderCurve: 'continuous',
  },
  regionOptionSelected: { backgroundColor: C.surface },
  regionText: { ...revaType.body2, color: C.ink2 },
  regionTextSelected: { color: C.green600, fontWeight: '700' },
  actionsCard: { gap: revaSpacing.s2 },
  actionButton: {
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: revaSpacing.s4,
    borderRadius: revaRadii.sm,
    borderCurve: 'continuous',
  },
  primaryButton: { backgroundColor: C.green500 },
  secondaryButton: { backgroundColor: C.surface, borderWidth: 1, borderColor: C.lineStrong },
  dangerButton: { backgroundColor: revaSemantic.risk.bg },
  actionLabel: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '700' },
  primaryLabel: { color: C.greenOn },
  secondaryLabel: { color: C.ink1 },
  dangerLabel: { color: revaSemantic.risk.fg },
  disabled: { opacity: 0.52 },
  privacyNote: { ...revaType.caption, color: C.ink3, textAlign: 'center' },
});
