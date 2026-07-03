/**
 * BackToChatBar — 二级屏 (今日 / 记录 / 我) 顶部的「返回阿衡」入口。
 *
 * Agent-native shell 去掉了底部 Tab Bar, 阿衡(chat) 是主屏; 二级屏需要一个一致的
 * 回主屏出口。走 useTheme().c 主题色 (自动明暗), 由调用方放在各自 SafeAreaView 内
 * (edges top) 顶部。点击 → router.navigate('/(tabs)/chat')。
 */
import React from 'react';
import { StyleSheet, Text, TextStyle, TouchableOpacity, View, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useTheme } from '../../hooks/useTheme';
import { FONT_SIZE_CAPS } from '../../constants/theme';

export default function BackToChatBar({
  right,
  style,
}: {
  /** 可选右侧插槽 (标题右侧动作), 默认空。 */
  right?: React.ReactNode;
  style?: ViewStyle;
}) {
  const { c } = useTheme();
  return (
    <View style={[styles.row, style]}>
      <TouchableOpacity
        onPress={() => router.navigate('/(tabs)/chat')}
        hitSlop={8}
        activeOpacity={0.7}
        style={[styles.back, { backgroundColor: c.bgCard, borderColor: c.separator }]}
        accessibilityRole="button"
        accessibilityLabel="返回阿衡"
        accessibilityHint="回到与阿衡的对话主屏"
      >
        <Ionicons name="chevron-back" size={16} color={c.brand} />
        <Text
          maxFontSizeMultiplier={FONT_SIZE_CAPS.default}
          style={[styles.label, { color: c.labelPrimary }]}
          numberOfLines={1}
        >
          返回阿衡
        </Text>
      </TouchableOpacity>
      {right ? <View style={styles.right}>{right}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  back: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    alignSelf: 'flex-start',
    paddingLeft: 8,
    paddingRight: 12,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
  },
  label: {
    fontSize: 14,
    fontWeight: '700',
  } as TextStyle,
  right: {
    flexShrink: 0,
  },
});
