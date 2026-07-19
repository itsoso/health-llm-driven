import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { useAppSession } from '../../hooks/useAppSession';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

export default function LocalModeBlockedScreen({ errorCode }: { errorCode: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { switchMode } = useAppSession();
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState(false);
  const missingKey = errorCode === 'vault_key_missing';

  const continueToCloud = async () => {
    setSwitching(true);
    setSwitchError(false);
    try {
      await switchMode('cloud_account');
    } catch {
      setSwitchError(true);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.content}>
        <View style={styles.iconBox}>
          <Ionicons name="lock-closed-outline" size={32} color={c.brand} />
        </View>
        <Text style={styles.title}>
          {missingKey ? '本地保险库需要恢复' : '本地模式配置需要修复'}
        </Text>
        <Text style={styles.detail}>
          {missingKey
            ? '检测到本机加密资料，但设备密钥已不存在。系统不会覆盖或重建这些资料。请保留当前数据，稍后用恢复文件和恢复密钥恢复。'
            : '本地模式配置无法安全读取。为避免误开云端或覆盖本机资料，应用已停止自动继续。'}
        </Text>
        <Pressable
          style={({ pressed }) => [styles.button, pressed ? styles.buttonPressed : null]}
          onPress={() => void continueToCloud()}
          disabled={switching}
          accessibilityRole="button"
          accessibilityLabel="切换到云端账号"
        >
          <Text style={styles.buttonText}>{switching ? '切换中…' : '切换到云端账号'}</Text>
        </Pressable>
        <Text style={styles.note}>切换不会删除或上传本机加密资料。</Text>
        {switchError ? <Text style={styles.error}>切换没有完成，请稍后重试。</Text> : null}
      </View>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 30,
    gap: 14,
  },
  iconBox: {
    width: 68,
    height: 68,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brandLight,
  },
  title: { color: c.labelPrimary, fontSize: 22, fontWeight: '800', textAlign: 'center' },
  detail: { color: c.labelSecondary, fontSize: 14, lineHeight: 21, textAlign: 'center' },
  button: {
    minWidth: 210,
    height: 48,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brand,
    marginTop: 6,
  },
  buttonPressed: { opacity: 0.75 },
  buttonText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  note: { color: c.labelTertiary, fontSize: 12 },
  error: { color: c.labelSecondary, fontSize: 13 },
});
