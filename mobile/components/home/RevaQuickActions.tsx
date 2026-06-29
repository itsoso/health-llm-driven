/**
 * RevaQuickActions —— 首页快捷动作行(Reva 重设计第 6 块)。
 *
 * 主按钮「补今日记录」(Button primary → /(tabs)/record)
 * + 语音记录(/voice-chat?intent=journal)+ 加号记录(/(tabs)/record)两个次级 icon 按钮。
 * 纯表现型:导航回调全部由 index.tsx 注入,本组件不取数。
 */
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { revaColors as C } from '../../constants/revaTheme';
import { Button } from '../reva/RevaKit';

export default function RevaQuickActions({
  onRun,
  onVoice,
  onRecord,
}: {
  onRun: () => void;
  onVoice: () => void;
  onRecord: () => void;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.primary}>
        <Button variant="primary" size="md" icon="plus" full onPress={onRun} accessibilityLabel="补今日记录">
          补今日记录
        </Button>
      </View>
      <IconBtn label="语音记录" icon="mic-outline" onPress={onVoice} />
      <IconBtn label="记录" icon="add" onPress={onRecord} />
    </View>
  );
}

function IconBtn({
  label,
  icon,
  onPress,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
}) {
  return (
    <Pressable
      style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={22} color={C.green600} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  primary: { flex: 1 },
  iconBtn: {
    width: 50,
    height: 50,
    borderRadius: 999,
    backgroundColor: C.green50,
    borderWidth: 1.5,
    borderColor: C.green100,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
