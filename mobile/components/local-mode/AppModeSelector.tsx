import React, { useCallback, useMemo, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useAppSession } from '../../hooks/useAppSession';
import type { AppMode } from '../../services/localIdentity';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

const MODE_OPTIONS: {
  mode: AppMode;
  title: string;
  detail: string;
  icon: React.ComponentProps<typeof Ionicons>['name'];
}[] = [
  {
    mode: 'strict_local',
    title: '严格本地',
    detail: '无需注册；健康资料和识别都留在本机，不调用云端。',
    icon: 'shield-checkmark-outline',
  },
  {
    mode: 'local_first',
    title: '本地优先',
    detail: '健康资料留在本机；只有你明确使用云端 AI 时才连接服务端。',
    icon: 'phone-portrait-outline',
  },
  {
    mode: 'cloud_account',
    title: '云端账号',
    detail: '使用现有账号、跨设备数据和完整在线功能。',
    icon: 'cloud-outline',
  },
];

function switchConfirmation(from: AppMode | null, to: AppMode): string | null {
  if (from === to) return null;
  if (to === 'cloud_account') {
    return '本机资料不会自动上传或迁移。若当前没有有效账号，切换后会进入登录页。';
  }
  if (from === 'cloud_account') {
    return '云端账号中的既有资料不会自动下载到本机；本地保险库将作为独立资料空间。';
  }
  if (to === 'local_first') {
    return '本地优先仍默认保存在本机；只有你主动使用云端 AI 时才会发送该次必要内容。';
  }
  return '切换后将停止云端 AI 调用，本地资料保持不变。';
}

export default function AppModeSelector() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { session, switchMode } = useAppSession();
  const [changing, setChanging] = useState<AppMode | null>(null);

  const applyMode = useCallback(async (mode: AppMode) => {
    setChanging(mode);
    try {
      await switchMode(mode);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('device_passcode_required')) {
        Alert.alert('需要先设置锁屏密码', '请先在 iPhone 设置中启用锁屏密码，再回来选择本地模式。');
      } else if (message.includes('vault_key_missing')) {
        Alert.alert('需要恢复本地保险库', '本机还有加密资料，但解密密钥已不存在。请使用之前保存的恢复文件和恢复密钥。');
      } else {
        Alert.alert('切换失败', '运行模式没有改变，请稍后重试。');
      }
    } finally {
      setChanging(null);
    }
  }, [switchMode]);

  const requestMode = useCallback((mode: AppMode) => {
    if (mode === session?.mode || changing) return;
    const message = switchConfirmation(session?.mode ?? null, mode);
    if (!message) return;
    Alert.alert('切换运行模式', message, [
      { text: '取消', style: 'cancel' },
      { text: '确认切换', onPress: () => void applyMode(mode) },
    ]);
  }, [applyMode, changing, session?.mode]);

  return (
    <View style={styles.container}>
      {MODE_OPTIONS.map((option) => {
        const selected = session?.mode === option.mode;
        const pending = changing === option.mode;
        return (
          <Pressable
            key={option.mode}
            style={({ pressed }) => [
              styles.option,
              selected ? styles.optionSelected : null,
              pressed && !selected ? styles.optionPressed : null,
            ]}
            onPress={() => requestMode(option.mode)}
            accessibilityRole="radio"
            accessibilityState={{ selected, disabled: !!changing }}
            accessibilityLabel={`${option.title}，${option.detail}`}
          >
            <View style={[styles.iconBox, selected ? styles.iconBoxSelected : null]}>
              <Ionicons name={option.icon} size={21} color={selected ? c.brand : c.labelSecondary} />
            </View>
            <View style={styles.copy}>
              <View style={styles.titleRow}>
                <Text style={styles.title}>{option.title}</Text>
                {selected ? <Text style={styles.selectedText}>当前</Text> : null}
                {pending ? <Text style={styles.pendingText}>切换中…</Text> : null}
              </View>
              <Text style={styles.detail}>{option.detail}</Text>
            </View>
            <Ionicons
              name={selected ? 'checkmark-circle' : 'chevron-forward'}
              size={20}
              color={selected ? c.brand : c.labelTertiary}
            />
          </Pressable>
        );
      })}
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  container: { gap: 10 },
  option: {
    minHeight: 92,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: c.separator,
    backgroundColor: c.bgCard,
    paddingHorizontal: 14,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  optionSelected: { borderColor: c.brand, backgroundColor: c.brandLight },
  optionPressed: { opacity: 0.72 },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.bgPrimary,
  },
  iconBoxSelected: { backgroundColor: c.bgCard },
  copy: { flex: 1, gap: 5 },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { color: c.labelPrimary, fontSize: 16, fontWeight: '700' },
  selectedText: { color: c.brand, fontSize: 12, fontWeight: '700' },
  pendingText: { color: c.labelSecondary, fontSize: 12 },
  detail: { color: c.labelSecondary, fontSize: 13, lineHeight: 19 },
});
