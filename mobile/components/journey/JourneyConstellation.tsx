import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Path, Circle } from 'react-native-svg';
import { revaColors as C } from '../../constants/revaTheme';
import { APP_DISPLAY_NAME } from '../../constants/brand';

/** Intentionally schematic: ordinal nodes, never projected GPS coordinates. */
export default function JourneyConstellation({ month, cities, count, partial = false }: { month: string; cities: string[]; count: number; partial?: boolean }) {
  const nodes = cities.slice(0, 6);
  return <View style={styles.hero}>
    <Text style={styles.eyebrow}>{APP_DISPLAY_NAME} / 这一路</Text>
    <Text style={styles.title}>{month.replace('-', ' / ')}</Text>
    <Text style={styles.caption}>把平常的日子，留成自己的风景。</Text>
    {nodes.length > 0 && <View style={styles.constellation}>
      <Svg width="100%" height={126} viewBox="0 0 300 126">
        {nodes.slice(1).map((_, index) => <Path key={index} d={`M ${20 + index * 48} ${index % 2 ? 85 : 35} Q ${44 + index * 48} 60 ${68 + index * 48} ${index % 2 ? 35 : 85}`} stroke={C.green300} strokeWidth="1.5" fill="none" strokeDasharray="4 5" />)}
        {nodes.map((_, index) => <Circle key={index} cx={20 + index * 48} cy={index % 2 ? 85 : 35} r={index === 0 ? 7 : 5} fill={C.greenBright} />)}
      </Svg>
    </View>}
    <Text style={styles.cities}>{nodes.join('  ·  ')}{cities.length > 6 ? `  +${cities.length - 6}` : ''}</Text>
    <Text style={styles.caption}>{partial ? '已加载' : '已选'} {count} 个片段 · 足迹连线示意，非实际路线</Text>
  </View>;
}
const styles = StyleSheet.create({
  hero: { backgroundColor: C.focusBg, padding: 24, borderRadius: 24, gap: 12 },
  eyebrow: { color: C.focusInk2, fontSize: 12, letterSpacing: 1.4 },
  title: { color: C.focusInk1, fontSize: 34, fontWeight: '700' },
  caption: { color: C.focusInk2, fontSize: 12, lineHeight: 20 },
  constellation: { height: 126 },
  cities: { color: C.focusInk1, fontSize: 17, fontWeight: '600', lineHeight: 26 },
});
