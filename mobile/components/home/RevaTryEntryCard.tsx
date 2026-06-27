/**
 * 首页「试试新版 · 复元」入口卡 —— 把休眠的 /reva(复元 4-tab 体验)
 * 提升为可见入口。点击 router.push('/reva')。非破坏:只是首页一张卡,
 * 不动现有导航;不满意删掉本组件的渲染即可。
 *
 * 视觉走 Reva 设计语言(深绿 focus 底 + bright green accent + 就绪环 motif)。
 */
import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { Icon, RevaMark } from '../reva/RevaKit';
import { revaColors as C } from '../../constants/revaTheme';

export default function RevaTryEntryCard() {
  const router = useRouter();
  const onPress = () => {
    Haptics.selectionAsync().catch(() => {});
    router.push('/reva' as any);
  };
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel="试试新版复元"
      style={({ pressed }) => [styles.card, { transform: [{ scale: pressed ? 0.985 : 1 }] }]}
    >
      {/* 角落辉光,呼应 Reva hero */}
      <View style={styles.glow} pointerEvents="none" />
      <View style={styles.markWrap}>
        <RevaMark size={34} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.overline}>试试新版 · 体检后 90 天</Text>
        <Text style={styles.title}>复元</Text>
        <Text style={styles.sub} numberOfLines={1}>就绪度 · 数据 · 复元对话,一套主动健康体验</Text>
      </View>
      <Icon name="chevron-right" size={20} color={C.greenBright} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 13,
    backgroundColor: C.focusBg,
    borderRadius: 18,
    paddingVertical: 16,
    paddingHorizontal: 18,
    overflow: 'hidden',
    shadowColor: '#08140F',
    shadowOpacity: 0.28,
    shadowRadius: 22,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  glow: {
    position: 'absolute',
    top: -50,
    right: -30,
    width: 150,
    height: 150,
    borderRadius: 75,
    backgroundColor: 'rgba(58,210,159,0.16)',
  },
  markWrap: {
    width: 44,
    height: 44,
    borderRadius: 13,
    backgroundColor: C.focusBg2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  overline: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.6,
    color: C.focusInk2,
    marginBottom: 2,
  },
  title: {
    fontSize: 19,
    fontWeight: '800',
    letterSpacing: -0.3,
    color: C.focusInk1,
  },
  sub: {
    fontSize: 12.5,
    color: C.focusInk2,
    marginTop: 2,
  },
});
