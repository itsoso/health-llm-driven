import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii } from '../../../constants/theme';
import { useTheme, type ColorPalette } from '../../../hooks/useTheme';
import type { CardSpec } from './types';

interface RecordData {
  type: string;
  detail: string;
}

// 颜色保留 (语义 accent, 亮/暗模式都用); tint 改成主题感知, 暗色自动反色.
function _icons(c: ColorPalette): Record<string, { icon: string; color: string; bg: string }> {
  return {
    water:           { icon: 'water',             color: c.blue,   bg: c.tintBlue },
    supplement:      { icon: 'medical',           color: c.purple, bg: c.tintPurple },
    diet:            { icon: 'restaurant',        color: c.orange, bg: c.tintOrange },
    exercise:        { icon: 'fitness',           color: c.pink,   bg: c.tintPink },
    weight:          { icon: 'scale',             color: c.brand,  bg: c.brandLight },
    blood_pressure:  { icon: 'heart',             color: c.red,    bg: c.tintRed },
    rhinitis:        { icon: 'water',             color: c.teal,   bg: c.tintTeal },
    checkin:         { icon: 'checkbox',          color: c.green,  bg: c.tintGreen },
    medication:      { icon: 'flask',             color: c.purple, bg: c.tintPurple },
    default:         { icon: 'checkmark-circle',  color: c.green,  bg: c.tintGreen },
  };
}

export function RecordCardView({ type, detail }: RecordData) {
  const { c } = useTheme();
  const cfg = _icons(c)[type] || _icons(c).default;
  return (
    <View style={[styles.card, { backgroundColor: cfg.bg, borderColor: c.separator }]}>
      <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
      <Text maxFontSizeMultiplier={1.3} style={[styles.text, { color: c.labelPrimary }]}>
        {detail}
      </Text>
      <Ionicons name="checkmark-circle" size={14} color={c.green} />
    </View>
  );
}

export const RecordCardSpec: CardSpec<RecordData> = {
  type: 'record',
  label: '记录确认',
  match({ query_lower, toolsUsed }) {
    if (toolsUsed.has('health_record')) return 20;
    if (/记录|打卡|吃了|喝了|喝水|服药|补剂.*吃|刚吃|刚喝|体重是|血压是|洗鼻了|喷嚏/.test(query_lower)) return 12;
    return null;
  },
  build({ query_lower }) {
    let type = 'default';
    if (/喝水|喝了.*水/.test(query_lower)) type = 'water';
    else if (/补剂|服药/.test(query_lower)) type = 'supplement';
    else if (/吃了|早餐|午餐|晚餐|加餐/.test(query_lower)) type = 'diet';
    else if (/体重/.test(query_lower)) type = 'weight';
    else if (/血压/.test(query_lower)) type = 'blood_pressure';
    else if (/喷嚏|洗鼻|鼻炎/.test(query_lower)) type = 'rhinitis';
    else if (/跑|运动|锻炼|训练/.test(query_lower)) type = 'exercise';
    return { type, detail: '已记录' };
  },
  render: (d) => <RecordCardView {...d} />,
};

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: radii.md, padding: 10, marginVertical: 4,
    borderWidth: StyleSheet.hairlineWidth,
  },
  text: { fontSize: 13, flex: 1 } as TextStyle,
});
