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
import { loadCredentials, saveCredentials, clearCredentials } from '../services/auth';

export default function LoginScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { login } = useAuth();
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
        setUsername(saved.username);
        setPassword(saved.password);
        setRemember(true);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) {
      Alert.alert('提示', '请输入用户名和密码');
      return;
    }
    setLoading(true);
    try {
      await login(username.trim(), password);
      // 登录成功才落盘凭据; 取消勾选则清除旧记忆
      if (remember) {
        await saveCredentials(username.trim(), password);
      } else {
        await clearCredentials();
      }
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail || err?.message || '登录失败，请重试';
      Alert.alert('登录失败', msg);
    } finally {
      setLoading(false);
    }
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
          <Text style={styles.title}>HealthPilot</Text>
          <Text style={styles.subtitle}>AI 驱动的健康管理</Text>
        </View>

        <View style={styles.form}>
          <View style={styles.inputWrap}>
            <Ionicons
              name="person-outline"
              size={20}
              color={c.labelTertiary}
              style={styles.inputIcon}
            />
            <TextInput
              style={styles.input}
              placeholder="用户名"
              placeholderTextColor={c.labelTertiary}
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
              onSubmitEditing={handleLogin}
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
            onPress={handleLogin}
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
});
