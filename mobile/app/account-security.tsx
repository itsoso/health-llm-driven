import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { useAuth } from '../hooks/useAuth';
import { changePassword, setPassword } from '../services/auth';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function AccountSecurityScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const hasPassword = Boolean(user?.has_password);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (hasPassword && !oldPassword.trim()) {
      Alert.alert('提示', '请输入当前密码');
      return;
    }
    if (newPassword.length < 6) {
      Alert.alert('提示', '新密码至少 6 位');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('提示', '两次输入的新密码不一致');
      return;
    }
    setSubmitting(true);
    try {
      if (hasPassword) {
        await changePassword(oldPassword, newPassword);
      } else {
        await setPassword(newPassword);
      }
      Alert.alert(hasPassword ? '密码已修改' : '密码已设置', '下次也可以用手机号 + 密码登录。', [
        { text: '知道了', onPress: () => router.back() },
      ]);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || '保存失败，请稍后重试';
      Alert.alert('保存失败', msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.iconButton}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>账号安全</Text>
        <View style={styles.iconButton} />
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.body}
      >
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{hasPassword ? '修改登录密码' : '设置登录密码'}</Text>
          <Text style={styles.help}>
            手机号验证码是主登录方式。密码作为备用凭证，用于 Web/Mac 或验证码不可用时登录。
          </Text>

          {hasPassword && (
            <TextInput
              style={styles.input}
              value={oldPassword}
              onChangeText={setOldPassword}
              placeholder="当前密码"
              placeholderTextColor={c.labelTertiary}
              secureTextEntry
              accessibilityLabel="当前密码输入框"
            />
          )}
          <TextInput
            style={styles.input}
            value={newPassword}
            onChangeText={setNewPassword}
            placeholder="新密码"
            placeholderTextColor={c.labelTertiary}
            secureTextEntry
            accessibilityLabel="新密码输入框"
          />
          <TextInput
            style={styles.input}
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            placeholder="再次输入新密码"
            placeholderTextColor={c.labelTertiary}
            secureTextEntry
            onSubmitEditing={submit}
            accessibilityLabel="确认新密码输入框"
          />

          <TouchableOpacity
            style={[styles.primaryButton, submitting && styles.disabled]}
            onPress={submit}
            disabled={submitting}
            accessibilityRole="button"
            accessibilityLabel={hasPassword ? '保存新密码' : '设置登录密码'}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryText}>{hasPassword ? '保存新密码' : '设置登录密码'}</Text>
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
  header: {
    height: 56,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: c.labelPrimary,
  },
  body: {
    flex: 1,
    padding: 16,
  },
  card: {
    backgroundColor: c.bgCard,
    borderRadius: 16,
    padding: 18,
    borderWidth: 1,
    borderColor: c.separator,
    gap: 14,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: c.labelPrimary,
  },
  help: {
    fontSize: 14,
    lineHeight: 20,
    color: c.labelSecondary,
  },
  input: {
    height: 48,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: c.separator,
    paddingHorizontal: 14,
    color: c.labelPrimary,
    fontSize: 16,
    backgroundColor: c.fill,
  },
  primaryButton: {
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brand,
    marginTop: 4,
  },
  primaryText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  disabled: {
    opacity: 0.6,
  },
});
