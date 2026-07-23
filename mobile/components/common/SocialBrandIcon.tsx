import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';

import { SOCIAL_BRAND } from '../../constants/brand';

export type SocialBrand = 'wechat' | 'xiaohongshu';

export function SocialBrandIcon({
  brand,
  size = 16,
}: {
  brand: SocialBrand;
  size?: number;
}) {
  if (brand === 'xiaohongshu') {
    return (
      <Image
        source={require('../../assets/social/xiaohongshu.jpg')}
        style={{ width: size, height: size, borderRadius: Math.max(3, Math.round(size * 0.22)) }}
        contentFit="cover"
        accessibilityIgnoresInvertColors
      />
    );
  }

  return (
    <View
      style={[
        styles.wechat,
        {
          width: size,
          height: size,
          borderRadius: Math.max(3, Math.round(size * 0.25)),
        },
      ]}
    >
      <Ionicons
        name="logo-wechat"
        size={Math.max(9, Math.round(size * 0.7))}
        color="#FFFFFF"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wechat: {
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: SOCIAL_BRAND.wechat,
  },
});
