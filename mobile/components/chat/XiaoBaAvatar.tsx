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

// Every avatar size shares the selected guardian artwork with the launcher.
const BRAND_ICON = require('../../assets/images/icon.png');

export default function XiaoBaAvatar({
  size = 32,
  state = 'idle',
  label = '小气候形象',
  compact = false,
  style,
}: {
  size?: number;
  state?: XiaoBaAvatarState;
  label?: string;
  compact?: boolean;
  style?: ViewStyle;
}) {
  const radius = size / 2;
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      style={[
        compact ? styles.compactAvatar : styles.avatar,
        { width: size, height: size, borderRadius: radius },
        style,
      ]}
    >
      <Image source={BRAND_ICON} style={{ width: size, height: size }} resizeMode="cover" accessible={false} />
      {!compact && <View
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
      />}
    </View>
  );
}

const styles = StyleSheet.create({
  compactAvatar: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
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
