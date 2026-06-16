/**
 * RevaSectionGroup —— 首屏之下的分组容器(Reva 重设计)。
 *
 * 把首屏 6 块之下的存量卡片按「身体数据 / 进展 / 工具」分组:顶部一个 SectionLabel,
 * 下面统一间距堆叠 children。视觉降权,功能不动(各卡仍是原组件)。
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { SectionLabel } from '../reva/RevaKit';

export default function RevaSectionGroup({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View>
      <SectionLabel>{title}</SectionLabel>
      <View style={styles.body}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  body: { gap: 12 },
});
