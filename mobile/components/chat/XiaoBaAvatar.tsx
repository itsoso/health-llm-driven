import React from 'react';
import { Image, StyleSheet, View, ViewStyle } from 'react-native';

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

// Chat and launcher share the selected cloud-agent artwork.
const BRAND_ICON = require('../../assets/images/icon.png');

export default function XiaoBaAvatar({
  size = 32,
  state = 'idle',
  label = '小气候形象',
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
      <Image source={BRAND_ICON} style={{ width: size, height: size }} resizeMode="cover" accessible={false} />
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
    backgroundColor: C.surface,
    ...revaShadows.sm,
  },
  statusDot: {
    position: 'absolute',
    borderWidth: 1.5,
    borderColor: C.surface,
  },
});
