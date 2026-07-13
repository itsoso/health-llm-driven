import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { Image } from 'expo-image';

import {
  revaColors as C,
  revaSemantic,
  revaShadows,
} from '../../constants/revaTheme';

const XIAOBA_ICON = require('../../assets/images/icon.png');

export type XiaoBaAvatarState = 'idle' | 'thinking' | 'listening';

const STATE_COLOR: Record<XiaoBaAvatarState, string> = {
  idle: C.green500,
  thinking: revaSemantic.info.fg,
  listening: C.greenBright,
};

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
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      style={[
        styles.avatar,
        { width: size, height: size, borderRadius: radius },
        style,
      ]}
    >
      <Image
        source={XIAOBA_ICON}
        style={styles.image}
        contentFit="cover"
        accessibilityIgnoresInvertColors
      />
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
    overflow: 'hidden',
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    ...revaShadows.sm,
  },
  image: {
    width: '100%',
    height: '100%',
  },
  statusDot: {
    position: 'absolute',
    borderWidth: 1.5,
    borderColor: C.surface,
  },
});
