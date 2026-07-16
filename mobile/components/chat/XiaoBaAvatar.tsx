import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import {
  revaColors as C,
  revaSemantic,
  revaShadows,
} from '../../constants/revaTheme';

export type XiaoBaAvatarState = 'idle' | 'thinking' | 'listening';

const STATE_COLOR: Record<XiaoBaAvatarState, string> = {
  idle: C.green500,
  thinking: revaSemantic.info.fg,
  listening: C.greenBright,
};

// 小巴标 · 脉冲(founder 2026-07-16 定版:白底 + 细绿环 + 绿脉冲)。
// 头像走内联 SVG(react-native-svg)而非旧的 icon.png —— 精确控制"白底/绿标/绿环"
// 三要素,和 App 图标(浅底脉冲,走原生构建单独换)同一支笔。脉冲路径 = logo 锁版 01。
const PULSE_PATH = 'M4 24h6l3.5 9L21 12l4.5 24L31 20l2.5 4H44';

export default function XiaoBaAvatar({
  size = 32,
  state = 'idle',
  label = '小巴形象',
  style,
}: {
  size?: number;
  state?: XiaoBaAvatarState;
  label?: string;
  style?: ViewStyle;
}) {
  const radius = size / 2;
  const ring = Math.max(1.5, size * 0.045); // 细绿环,随尺寸微调
  const mark = size * 0.6;
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      style={[
        styles.avatar,
        { width: size, height: size, borderRadius: radius, borderWidth: ring },
        style,
      ]}
    >
      <Svg width={mark} height={mark} viewBox="0 0 48 48">
        <Path
          d={PULSE_PATH}
          fill="none"
          stroke={C.green500}
          strokeWidth={3.4}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Svg>
      <View
        style={[
          styles.statusDot,
          {
            backgroundColor: STATE_COLOR[state],
            borderRadius: Math.max(3, size * 0.09),
            bottom: Math.max(1, size * 0.04),
            height: Math.max(6, size * 0.18),
            right: Math.max(1, size * 0.04),
            width: Math.max(6, size * 0.18),
          },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  avatar: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    backgroundColor: C.surface, // 白底
    borderColor: C.green500, // 细绿环(borderWidth 按 size 传入)
    ...revaShadows.sm,
  },
  statusDot: {
    position: 'absolute',
    borderWidth: 1.5,
    borderColor: C.surface,
  },
});
