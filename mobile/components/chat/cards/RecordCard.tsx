import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaRadii, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

interface RecordData {
  type: string;
  detail: string;
}

// 每类记录的 accent + tint = 「是哪类记录」的装饰色码 (饮水蓝/补剂紫/饮食橙/运动粉…),
// 非「好坏」临床语义, 故保留 Reva 亮色调色板字面量 (= legacy color/tint 值) → 无视觉回归.
const RECORD_ICONS: Record<string, { icon: string; color: string; bg: string }> = {
  water:           { icon: 'water',             color: '#2A6FDB', bg: '#E4ECF8' },
  supplement:      { icon: 'medical',           color: '#7C5CBF', bg: '#EDE7F6' },
  diet:            { icon: 'restaurant',        color: '#C97A2E', bg: '#F6E9DA' },
  exercise:        { icon: 'fitness',           color: '#C2487A', bg: '#F7E4EC' },
  weight:          { icon: 'scale',             color: C.green500, bg: C.green50 },
  blood_pressure:  { icon: 'heart',             color: '#D5503A', bg: '#F7E4E0' },
  rhinitis:        { icon: 'water',             color: '#2F9E8F', bg: '#E0EFEC' },
  checkin:         { icon: 'checkbox',          color: C.green500, bg: C.green50 },
  medication:      { icon: 'flask',             color: '#7C5CBF', bg: '#EDE7F6' },
  default:         { icon: 'checkmark-circle',  color: C.green500, bg: C.green50 },
};

// 防御闸: 后端若漏把原始 JSON 当 detail (历史 bug: tool result 无 message 字段时
// fallback 倒出整段 {"record_date":...}), 这里兜底成 "已记录", 绝不把 JSON 渲染给用户.
function safeDetail(detail: string): string {
  const trimmed = (detail || '').trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) return '已记录';
  return trimmed || '已记录';
}

export function RecordCardView({ type, detail }: RecordData) {
  const cfg = RECORD_ICONS[type] || RECORD_ICONS.default;
  return (
    <View style={[styles.card, { backgroundColor: cfg.bg, borderColor: C.line }]}>
      <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
      <Text maxFontSizeMultiplier={1.3} style={styles.text}>
        {safeDetail(detail)}
      </Text>
      <Ionicons name="checkmark-circle" size={14} color={C.green500} />
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
    borderRadius: revaRadii.md, padding: 10, marginVertical: 4,
    borderWidth: StyleSheet.hairlineWidth,
  },
  text: { fontFamily: revaFonts.sans, fontSize: 13, flex: 1, color: C.ink1 } as TextStyle,
});
