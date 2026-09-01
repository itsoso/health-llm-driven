import React, { useEffect, useMemo, useRef, useState } from 'react';
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
import { AxiosError } from 'axios';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { APP_DISPLAY_NAME } from '../constants/brand';
import { useAuth } from '../hooks/useAuth';
import { useTheme, type ColorPalette, type SemanticPalette } from '../hooks/useTheme';
import {
  loadCredentials,
  registrationAuthErrorCode,
  requestPhoneCode,
  saveCredentials,
} from '../services/auth';

type LoginMode = 'phone' | 'account';

interface LoginScreenProps {
  invitationLinkToken?: string | null;
  onInvitationLinkCleared?: () => void;
  registrationCompleted?: boolean;
  onInvitedRegistrationComplete?: () => void;
  onStartHealthProfile?: () => void;
}

const MANUAL_INVITE_PATTERN = /^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{8}$/;
const PHONE_PATTERN = /^\+[1-9]\d{6,14}$/;
const OTP_PATTERN = /^\d{4,8}$/;
const ACCOUNT_LOGIN_ACTIONABLE_ERRORS = new Set([
  '登录状态无法安全保存，请解锁设备后重试',
]);
const NETWORK_ERROR_CODES = new Set([
  AxiosError.ERR_NETWORK,
  AxiosError.ECONNABORTED,
  AxiosError.ETIMEDOUT,
]);

const INVITATION_ERROR_MESSAGES: Record<string, string> = {
  INVITATION_PHONE_MISMATCH: '该邀请码不是发送给当前手机号的，请确认手机号或联系管理员。',
  INVITATION_EXPIRED: '邀请码已过期，请联系管理员重新发送。',
  INVITATION_REVOKED: '邀请码已被撤销，请联系管理员。',
  INVITATION_ALREADY_USED: '邀请码已使用；如已注册，请返回使用手机号登录。',
  INVITATION_INVALID: '邀请码无效，请检查后重试或联系管理员。',
  REGISTRATION_INPUT_INVALID: '邀请码格式不正确，请检查后重试。',
  REGISTRATION_STATE_CONFLICT: '注册状态暂时冲突，请稍后重试。',
  REGISTRATION_USER_ALREADY_EXISTS: '该手机号已注册，请返回使用手机号登录。',
};

function normalizeInternationalPhone(value: string): string | null {
  const normalized = value.replace(/[\s()-]/g, '');
  return PHONE_PATTERN.test(normalized) ? normalized : null;
}

function maskPhone(value: string): string {
  if (value.startsWith('+86') && value.length === 14) {
    return `${value.slice(0, 6)}****${value.slice(-4)}`;
  }
  if (value.length <= 7) return value;
  return `${value.slice(0, 4)}****${value.slice(-3)}`;
}

function isNetworkError(error: unknown): boolean {
  return error instanceof AxiosError
    && Boolean(error.code && NETWORK_ERROR_CODES.has(error.code));
}

function accountLoginErrorMessage(error: unknown): string {
  if (error instanceof Error && ACCOUNT_LOGIN_ACTIONABLE_ERRORS.has(error.message)) {
    return error.message;
  }
  if (isNetworkError(error)) {
    return '网络暂时不可用，请检查网络后重试。';
  }
  if (error instanceof AxiosError && error.response) {
    return '登录失败，请检查账号信息。';
  }
  return '登录失败，请稍后重试。';
}

export default function LoginScreen({
  invitationLinkToken = null,
  onInvitationLinkCleared,
  registrationCompleted = false,
  onInvitedRegistrationComplete,
  onStartHealthProfile,
}: LoginScreenProps) {
  const router = useRouter();
  const { c, s } = useTheme();
  const styles = useMemo(() => createStyles(c, s), [c, s]);
  const {
    login,
    verifyPhoneCode,
    completeInvitedRegistration,
    pendingRegistration,
  } = useAuth();

  const [mode, setMode] = useState<LoginMode>('phone');
  const [phone, setPhone] = useState('+86 ');
  const [sentPhone, setSentPhone] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [inviteVerified, setInviteVerified] = useState(false);
  const [useManualCredential, setUseManualCredential] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [loading, setLoading] = useState(false);
  const [inlineError, setInlineError] = useState('');
  const [ticketExpiredMessage, setTicketExpiredMessage] = useState('');
  const [registrationComplete, setRegistrationComplete] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const previousInvitationLinkToken = useRef(invitationLinkToken);

  const restoredPending = Boolean(
    pendingRegistration && pendingRegistration.expiresAt > Date.now(),
  );
  const showInvite = !ticketExpiredMessage && (inviteVerified || restoredPending);
  const displayMaskedPhone = pendingRegistration?.phoneMasked
    || (sentPhone ? maskPhone(sentPhone) : '已验证手机号');
  const secureLinkReady = Boolean(invitationLinkToken) && !useManualCredential;

  useEffect(() => {
    let active = true;
    void loadCredentials().then((saved) => {
      if (!active || !saved) return;
      setUsername(saved.username);
      setPassword(saved.password);
      setRemember(saved.password.length > 0);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (
      invitationLinkToken
      && invitationLinkToken !== previousInvitationLinkToken.current
    ) {
      setUseManualCredential(false);
      setInviteCode('');
    }
    previousInvitationLinkToken.current = invitationLinkToken;
  }, [invitationLinkToken]);

  useEffect(() => {
    if (countdown <= 0) return undefined;
    const timer = setInterval(() => setCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const handleRequestCode = async () => {
    const normalized = normalizeInternationalPhone(phone);
    if (!normalized) {
      Alert.alert('手机号格式不正确', '请输入含国家区号的手机号，例如 +86 138 0013 8000。');
      return;
    }
    setLoading(true);
    setCode('');
    setInviteVerified(false);
    setInlineError('');
    setTicketExpiredMessage('');
    try {
      const result = await requestPhoneCode(normalized, 'login');
      setSentPhone(normalized);
      setCountdown(60);
      if (result.dev_code) setCode(result.dev_code);
    } catch (error) {
      setInlineError(isNetworkError(error)
        ? '网络暂时不可用，请检查网络后重试。'
        : '验证码发送失败，请稍后重试。');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyCode = async () => {
    if (!sentPhone || !OTP_PATTERN.test(code.trim())) {
      setInlineError('请输入短信中的验证码。');
      return;
    }
    setLoading(true);
    setInlineError('');
    try {
      const outcome = await verifyPhoneCode(sentPhone, code.trim());
      if (outcome === 'invitation_required') {
        setInviteVerified(true);
      } else if (outcome === 'authenticated') {
        onInvitationLinkCleared?.();
      }
    } catch (error) {
      setInlineError(isNetworkError(error)
        ? '网络暂时不可用，请检查网络后重试。'
        : '验证码无效或已过期，请重新获取。');
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteRegistration = async () => {
    const normalizedCode = inviteCode.trim().toUpperCase();
    if (!secureLinkReady && !MANUAL_INVITE_PATTERN.test(normalizedCode)) {
      setInlineError('请输入管理员发送的 8 位邀请码。');
      return;
    }
    setLoading(true);
    setInlineError('');
    try {
      await completeInvitedRegistration(
        secureLinkReady
          ? { linkToken: invitationLinkToken as string }
          : { manualCode: normalizedCode },
      );
      onInvitationLinkCleared?.();
      setRegistrationComplete(true);
      onInvitedRegistrationComplete?.();
    } catch (error) {
      const codeValue = registrationAuthErrorCode(error);
      if (codeValue === 'VERIFIED_PHONE_TICKET_EXPIRED') {
        setInviteVerified(false);
        setCode('');
        setCountdown(0);
        setTicketExpiredMessage('验证码已过期，请重新验证。');
      } else {
        setInlineError(
          (codeValue && INVITATION_ERROR_MESSAGES[codeValue])
          || (isNetworkError(error)
            ? '网络暂时不可用，请检查网络后重试。'
            : '暂时无法完成注册，请稍后重试或联系管理员。'),
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleAccountLogin = async () => {
    if (!username.trim() || !password) {
      Alert.alert('提示', '请输入用户名和密码');
      return;
    }
    setLoading(true);
    setInlineError('');
    try {
      await login(username.trim(), password);
      await saveCredentials(username.trim(), password, remember);
    } catch (error) {
      setInlineError(accountLoginErrorMessage(error));
    } finally {
      setLoading(false);
    }
  };

  const changePhone = () => {
    setSentPhone(null);
    setCode('');
    setCountdown(0);
    setInlineError('');
    setTicketExpiredMessage('');
  };

  const renderPrimaryButton = (label: string, onPress: () => void, disabled: boolean) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        disabled && styles.buttonDisabled,
        pressed && !disabled && styles.buttonPressed,
      ]}
    >
      {loading ? <ActivityIndicator color={c.bgCard} /> : <Text style={styles.buttonText}>{label}</Text>}
    </Pressable>
  );

  if (registrationCompleted || registrationComplete) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.successContainer}>
          <Ionicons name="checkmark-circle" size={72} color={c.brand} />
          <Text style={styles.successTitle}>邀请验证成功，欢迎加入小巴</Text>
          {renderPrimaryButton(
            '开始设置我的健康档案',
            () => {
              if (onStartHealthProfile) {
                onStartHealthProfile();
              } else {
                router.replace('/reva-onboarding');
              }
            },
            false,
          )}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.safe}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
          contentInsetAdjustmentBehavior="automatic"
        >
          <View style={styles.logoSection}>
            <View style={styles.logoCircle}>
              <Ionicons name="heart-circle" size={64} color={c.brand} />
            </View>
            <Text style={styles.brand}>{APP_DISPLAY_NAME}</Text>
            <Text style={styles.title}>{showInvite ? '输入邀请码' : '登录小巴'}</Text>
            <Text style={styles.subtitle}>
              {showInvite
                ? '小巴目前采用邀请制，请输入管理员发送的邀请码。'
                : '首次使用需获得管理员邀请'}
            </Text>
          </View>

          <View style={styles.form}>
            {mode === 'account' ? (
              <>
                <View style={styles.inputWrap}>
                  <Ionicons name="person-outline" size={20} color={c.labelTertiary} style={styles.inputIcon} />
                  <TextInput
                    style={styles.input}
                    placeholder="用户名 / 邮箱 / 手机号"
                    placeholderTextColor={c.labelTertiary}
                    textContentType="username"
                    autoComplete="username"
                    autoCapitalize="none"
                    autoCorrect={false}
                    value={username}
                    onChangeText={setUsername}
                    accessibilityLabel="用户名输入框"
                    editable={!loading}
                  />
                </View>
                <View style={styles.inputWrap}>
                  <Ionicons name="lock-closed-outline" size={20} color={c.labelTertiary} style={styles.inputIcon} />
                  <TextInput
                    style={styles.input}
                    placeholder="密码"
                    placeholderTextColor={c.labelTertiary}
                    secureTextEntry={!showPassword}
                    value={password}
                    onChangeText={setPassword}
                    onSubmitEditing={handleAccountLogin}
                    accessibilityLabel="密码输入框"
                    editable={!loading}
                  />
                  <Pressable
                    disabled={loading}
                    onPress={() => setShowPassword((value) => !value)}
                    accessibilityRole="button"
                    accessibilityLabel={showPassword ? '隐藏密码' : '显示密码'}
                    accessibilityState={{ disabled: loading }}
                    hitSlop={10}
                  >
                    <Ionicons
                      name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                      size={20}
                      color={c.labelTertiary}
                    />
                  </Pressable>
                </View>
                <Pressable
                  disabled={loading}
                  style={styles.rememberRow}
                  onPress={() => setRemember((value) => !value)}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: remember }}
                  accessibilityLabel="记住密码"
                >
                  <Ionicons
                    name={remember ? 'checkbox' : 'square-outline'}
                    size={20}
                    color={remember ? c.brand : c.labelTertiary}
                  />
                  <Text style={styles.rememberText}>记住密码</Text>
                </Pressable>
                {inlineError ? (
                  <Text accessibilityRole="alert" style={styles.errorText}>
                    {inlineError}
                  </Text>
                ) : null}
                {renderPrimaryButton('登录', handleAccountLogin, loading)}
                <Pressable
                  disabled={loading}
                  onPress={() => setMode('phone')}
                  style={styles.secondaryButton}
                  accessibilityRole="button"
                  accessibilityLabel="手机号登录"
                  accessibilityState={{ disabled: loading }}
                >
                  <Text style={styles.secondaryText}>手机号登录</Text>
                </Pressable>
              </>
            ) : showInvite ? (
              <>
                <View style={styles.verifiedPhoneRow}>
                  <Ionicons name="checkmark-circle" size={20} color={c.brand} />
                  <View>
                    <Text style={styles.verifiedLabel}>手机号已验证</Text>
                    <Text style={styles.verifiedPhone}>{displayMaskedPhone}</Text>
                  </View>
                </View>
                {secureLinkReady ? (
                  <>
                    <View style={styles.secureLinkRow}>
                      <Ionicons name="link-outline" size={20} color={c.brand} />
                      <Text style={styles.secureLinkText}>已读取安全邀请链接</Text>
                    </View>
                    <Pressable
                      disabled={loading}
                      onPress={() => setUseManualCredential(true)}
                      style={styles.secondaryButton}
                      accessibilityRole="button"
                      accessibilityLabel="改用 8 位邀请码"
                      accessibilityState={{ disabled: loading }}
                    >
                      <Text style={styles.secondaryText}>改用 8 位邀请码</Text>
                    </Pressable>
                  </>
                ) : (
                  <View style={styles.inputWrap}>
                    <Ionicons name="ticket-outline" size={20} color={c.labelTertiary} style={styles.inputIcon} />
                    <TextInput
                      style={styles.input}
                      placeholder="8 位邀请码"
                      placeholderTextColor={c.labelTertiary}
                      autoCapitalize="characters"
                      autoCorrect={false}
                      maxLength={8}
                      value={inviteCode}
                      onChangeText={(value) => setInviteCode(value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
                      onSubmitEditing={handleCompleteRegistration}
                      accessibilityLabel="邀请码输入框"
                      editable={!loading}
                    />
                  </View>
                )}
                {inlineError ? <Text style={styles.errorText}>{inlineError}</Text> : null}
                {renderPrimaryButton(
                  '完成注册',
                  handleCompleteRegistration,
                  loading || (!secureLinkReady && inviteCode.length !== 8),
                )}
              </>
            ) : sentPhone ? (
              <>
                <Text style={styles.phoneSummary}>验证码已发送至 {maskPhone(sentPhone)}</Text>
                <View style={styles.inputWrap}>
                  <Ionicons name="keypad-outline" size={20} color={c.labelTertiary} style={styles.inputIcon} />
                  <TextInput
                    style={styles.input}
                    placeholder="短信验证码"
                    placeholderTextColor={c.labelTertiary}
                    keyboardType="number-pad"
                    textContentType="oneTimeCode"
                    autoComplete="sms-otp"
                    maxLength={8}
                    value={code}
                    onChangeText={(value) => setCode(value.replace(/\D/g, ''))}
                    onSubmitEditing={handleVerifyCode}
                    accessibilityLabel="验证码输入框"
                    editable={!loading}
                  />
                </View>
                {ticketExpiredMessage ? <Text style={styles.errorText}>{ticketExpiredMessage}</Text> : null}
                {inlineError ? <Text style={styles.errorText}>{inlineError}</Text> : null}
                {renderPrimaryButton(
                  '验证并登录',
                  handleVerifyCode,
                  loading || !OTP_PATTERN.test(code),
                )}
                <View style={styles.inlineActions}>
                  <Pressable
                    disabled={loading || countdown > 0}
                    onPress={handleRequestCode}
                    accessibilityRole="button"
                    accessibilityLabel="重新发送验证码"
                    accessibilityState={{ disabled: loading || countdown > 0 }}
                  >
                    <Text style={[styles.secondaryText, countdown > 0 && styles.mutedText]}>
                      {countdown > 0 ? `重新发送 (${countdown}s)` : '重新发送'}
                    </Text>
                  </Pressable>
                  <Pressable
                    disabled={loading}
                    onPress={changePhone}
                    accessibilityRole="button"
                    accessibilityLabel="修改手机号"
                    accessibilityState={{ disabled: loading }}
                  >
                    <Text style={styles.secondaryText}>修改手机号</Text>
                  </Pressable>
                </View>
              </>
            ) : (
              <>
                <View style={styles.inputWrap}>
                  <Ionicons name="call-outline" size={20} color={c.labelTertiary} style={styles.inputIcon} />
                  <TextInput
                    style={styles.input}
                    placeholder="+86 138 0013 8000"
                    placeholderTextColor={c.labelTertiary}
                    keyboardType="phone-pad"
                    textContentType="telephoneNumber"
                    autoComplete="tel"
                    value={phone}
                    onChangeText={setPhone}
                    onSubmitEditing={handleRequestCode}
                    accessibilityLabel="手机号输入框"
                    editable={!loading}
                  />
                </View>
                <Text style={styles.helperText}>请保留国家区号；中国大陆手机号默认使用 +86。</Text>
                {invitationLinkToken ? (
                  <View style={styles.invitationReadyRow}>
                    <Ionicons name="ticket-outline" size={18} color={c.brand} />
                    <Text style={styles.secureLinkText}>已获得邀请</Text>
                  </View>
                ) : null}
                {ticketExpiredMessage ? <Text style={styles.errorText}>{ticketExpiredMessage}</Text> : null}
                {inlineError ? <Text style={styles.errorText}>{inlineError}</Text> : null}
                {renderPrimaryButton(
                  '获取验证码',
                  handleRequestCode,
                  loading || normalizeInternationalPhone(phone) === null,
                )}
                <Pressable
                  disabled={loading}
                  onPress={() => Alert.alert(
                    '先验证手机号',
                    '邀请码需与手机号匹配，请先获取并验证短信验证码。',
                  )}
                  style={styles.secondaryButton}
                  accessibilityRole="button"
                  accessibilityLabel="我有邀请码"
                  accessibilityState={{ disabled: loading }}
                >
                  <Text style={styles.secondaryText}>我有邀请码</Text>
                </Pressable>
                <Pressable
                  disabled={loading}
                  onPress={() => setMode('account')}
                  style={styles.secondaryButton}
                  accessibilityRole="button"
                  accessibilityLabel="账号密码登录"
                  accessibilityState={{ disabled: loading }}
                >
                  <Text style={styles.secondaryText}>账号密码登录</Text>
                </Pressable>
              </>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette, s: SemanticPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  container: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 32, paddingVertical: 28 },
  logoSection: { alignItems: 'center', marginBottom: 32 },
  logoCircle: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  brand: { fontSize: 16, fontWeight: '700', color: c.brand, marginBottom: 10 },
  title: { fontSize: 28, fontWeight: '700', color: c.labelPrimary, letterSpacing: -0.5 },
  subtitle: { fontSize: 15, lineHeight: 22, color: c.labelSecondary, marginTop: 6, textAlign: 'center' },
  form: { gap: 14 },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: c.bgCard,
    borderRadius: 12,
    paddingHorizontal: 14,
    minHeight: 52,
    borderWidth: 1,
    borderColor: c.separator,
  },
  inputIcon: { marginRight: 10 },
  input: { flex: 1, minHeight: 48, fontSize: 16, color: c.labelPrimary },
  button: {
    backgroundColor: c.brand,
    minHeight: 52,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 6,
  },
  buttonDisabled: { opacity: 0.5 },
  buttonPressed: { opacity: 0.82 },
  buttonText: { color: c.bgCard, fontSize: 17, fontWeight: '600' },
  secondaryButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  secondaryText: { color: c.brand, fontSize: 14, fontWeight: '600' },
  mutedText: { color: c.labelTertiary },
  helperText: { color: c.labelSecondary, fontSize: 13, lineHeight: 19 },
  invitationReadyRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    borderRadius: 12,
    backgroundColor: c.brandLight,
  },
  errorText: { color: s.danger.fg, backgroundColor: s.danger.bg, borderRadius: 10, padding: 12, fontSize: 14, lineHeight: 20 },
  phoneSummary: { color: c.labelSecondary, fontSize: 14, textAlign: 'center' },
  inlineActions: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 44 },
  rememberRow: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 },
  rememberText: { fontSize: 14, color: c.labelSecondary },
  verifiedPhoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    padding: 14,
    backgroundColor: c.brandLight,
  },
  verifiedLabel: { fontSize: 13, color: c.labelSecondary },
  verifiedPhone: { marginTop: 2, fontSize: 16, fontWeight: '600', color: c.labelPrimary },
  secureLinkRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
    borderRadius: 12,
    padding: 14,
    backgroundColor: c.brandLight,
  },
  secureLinkText: { color: c.brandDark, fontSize: 14, fontWeight: '600' },
  successContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 20, paddingHorizontal: 32 },
  successTitle: { color: c.labelPrimary, fontSize: 24, lineHeight: 32, fontWeight: '700', textAlign: 'center' },
});
