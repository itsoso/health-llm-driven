import React, { useState, useMemo, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../hooks/useAuth';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { loadCredentials, requestPhoneCode, saveCredentials } from '../services/auth';
import { APP_DISPLAY_NAME } from '../constants/brand';

type LoginMode = 'phone' | 'account';

export default function LoginScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { login, loginByPhoneCode } = useAuth();
  const [mode, setMode] = useState<LoginMode>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [phoneHint, setPhoneHint] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);

  // 启动时回填已记住的凭据 (存在 SecureStore / Keychain)
  useEffect(() => {
    let active = true;
    loadCredentials().then((saved) => {
      if (active && saved) {
        setUsername(saved.username);          // 总是回填最后登录的用户名
        setPassword(saved.password);          // 没记密码时为空串
        setRemember(saved.password.length > 0); // 有记住密码才勾上
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const handleRequestCode = async () => {
    const trimmed = phone.trim();
    if (!trimmed) {
      Alert.alert('提示', '请输入手机号');
      return;
    }
    setLoading(true);
    try {
      const result = await requestPhoneCode(trimmed, 'login');
      setCodeSent(true);
      if (result.dev_code) {
        setCode(result.dev_code);
        setPhoneHint('开发验证码已自动填入');
      } else {
        setPhoneHint(`验证码已发送至 ${result.phone}`);
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail || err?.message || '验证码发送失败，请稍后重试';
      Alert.alert('发送失败', msg);
    } finally {
      setLoading(false);
    }
  };

  const handlePhoneLogin = async () => {
    if (!phone.trim() || !code.trim()) {
      Alert.alert('提示', '请输入手机号和验证码');
      return;
    }
    setLoading(true);
    try {
      await loginByPhoneCode(phone.trim(), code.trim());
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail || err?.message || '登录失败，请重试';
      Alert.alert('登录失败', msg);
    } finally {
      setLoading(false);
    }
  };

  const handleAccountLogin = async () => {
    if (!username.trim() || !password.trim()) {
      Alert.alert('提示', '请输入用户名和密码');
      return;
    }
    setLoading(true);
    try {
      await login(username.trim(), password);
      // 登录成功才落盘:用户名总记(最后登录用户),密码按勾选记/清
      await saveCredentials(username.trim(), password, remember);
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail || err?.message || '登录失败，请重试';
      Alert.alert('登录失败', msg);
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (next: LoginMode) => {
    setMode(next);
    setPhoneHint('');
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.logoSection}>
          <View style={styles.logoCircle}>
            <Ionicons name="heart-circle" size={64} color={c.brand} />
          </View>
          <Text style={styles.title}>{APP_DISPLAY_NAME}</Text>
          <Text style={styles.subtitle}>AI 驱动的健康管理</Text>
        </View>

        <View style={styles.form}>
          {mode === 'phone' ? (
            <>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="call-outline"
                  size={20}
                  color={c.labelTertiary}
                  style={styles.inputIcon}
                />
                <TextInput
                  key="phone-login-input"
                  style={styles.input}
                  placeholder="请输入手机号"
                  placeholderTextColor={c.labelTertiary}
                  keyboardType="phone-pad"
                  textContentType="telephoneNumber"
                  autoComplete="tel"
                  value={phone}
                  onChangeText={(text) => {
                    setPhone(text);
                    setCodeSent(false);
                    setPhoneHint('');
                  }}
                  onSubmitEditing={handleRequestCode}
                  accessibilityLabel="手机号输入框"
                />
              </View>

              {codeSent && (
                <View style={styles.inputWrap}>
                  <Ionicons
                    name="keypad-outline"
                    size={20}
                    color={c.labelTertiary}
                    style={styles.inputIcon}
                  />
                  <TextInput
                    style={styles.input}
                    placeholder="请输入验证码"
                    placeholderTextColor={c.labelTertiary}
                    keyboardType="number-pad"
                    textContentType="oneTimeCode"
                    autoComplete="sms-otp"
                    value={code}
                    onChangeText={setCode}
                    onSubmitEditing={handlePhoneLogin}
                    accessibilityLabel="验证码输入框"
                  />
                </View>
              )}

              {phoneHint ? <Text style={styles.hintText}>{phoneHint}</Text> : null}

              <TouchableOpacity
                style={[styles.button, loading && styles.buttonDisabled]}
                onPress={codeSent ? handlePhoneLogin : handleRequestCode}
                disabled={loading}
                activeOpacity={0.8}
                accessibilityRole="button"
                accessibilityLabel={codeSent ? '登录或注册' : '获取验证码'}
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>{codeSent ? '登录 / 注册' : '获取验证码'}</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => switchMode('account')}
                style={styles.secondaryButton}
                activeOpacity={0.7}
              >
                <Text style={styles.secondaryText}>账号密码登录</Text>
              </TouchableOpacity>
            </>
          ) : (
            <>
              <View style={styles.inputWrap}>
                <Ionicons
                  name="person-outline"
                  size={20}
                  color={c.labelTertiary}
                  style={styles.inputIcon}
                />
                <TextInput
                  key="account-login-input"
                  style={styles.input}
                  placeholder="用户名 / 邮箱 / 手机号"
                  placeholderTextColor={c.labelTertiary}
                  keyboardType="default"
                  textContentType="username"
                  autoComplete="username"
                  autoCapitalize="none"
                  autoCorrect={false}
                  value={username}
                  onChangeText={setUsername}
                  accessibilityLabel="用户名输入框"
                />
              </View>

              <View style={styles.inputWrap}>
                <Ionicons
                  name="lock-closed-outline"
                  size={20}
                  color={c.labelTertiary}
                  style={styles.inputIcon}
                />
                <TextInput
                  style={styles.input}
                  placeholder="密码"
                  placeholderTextColor={c.labelTertiary}
                  secureTextEntry={!showPassword}
                  value={password}
                  onChangeText={setPassword}
                  onSubmitEditing={handleAccountLogin}
                  accessibilityLabel="密码输入框"
                />
                <TouchableOpacity
                  onPress={() => setShowPassword(!showPassword)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                >
                  <Ionicons
                    name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                    size={20}
                    color={c.labelTertiary}
                  />
                </TouchableOpacity>
              </View>

              <TouchableOpacity
                style={styles.rememberRow}
                onPress={() => setRemember((v) => !v)}
                activeOpacity={0.7}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: remember }}
                accessibilityLabel="记住密码"
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Ionicons
                  name={remember ? 'checkbox' : 'square-outline'}
                  size={20}
                  color={remember ? c.brand : c.labelTertiary}
                />
                <Text style={styles.rememberText}>记住密码</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.button, loading && styles.buttonDisabled]}
                onPress={handleAccountLogin}
                disabled={loading}
                activeOpacity={0.8}
                accessibilityRole="button"
                accessibilityLabel="登录"
              >
                {loading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>登录</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => switchMode('phone')}
                style={styles.secondaryButton}
                activeOpacity={0.7}
              >
                <Text style={styles.secondaryText}>手机号登录 / 注册</Text>
              </TouchableOpacity>
            </>
          )}

        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: c.bgPrimary,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 32,
  },
  logoSection: {
    alignItems: 'center',
    marginBottom: 48,
  },
  logoCircle: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: c.brandLight,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: c.labelPrimary,
    letterSpacing: -0.5,
  },
  subtitle: {
    fontSize: 15,
    color: c.labelSecondary,
    marginTop: 4,
  },
  form: {
    gap: 16,
  },
  rememberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: -4,
    paddingVertical: 2,
  },
  rememberText: {
    fontSize: 14,
    color: c.labelSecondary,
  },
  hintText: {
    color: c.brand,
    fontSize: 13,
    lineHeight: 18,
  },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: c.bgCard,
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 50,
    borderWidth: 1,
    borderColor: c.separator,
  },
  inputIcon: {
    marginRight: 10,
  },
  input: {
    flex: 1,
    fontSize: 16,
    color: c.labelPrimary,
  },
  button: {
    backgroundColor: c.brand,
    height: 50,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
    shadowColor: c.brand,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
  secondaryButton: {
    alignItems: 'center',
    paddingVertical: 8,
  },
  secondaryText: {
    color: c.brand,
    fontSize: 14,
    fontWeight: '600',
  },
});
