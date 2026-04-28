import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '../../../constants/theme';
import type { CardSpec } from './types';

interface RecordData {
  type: string;
  detail: string;
}

const ICONS: Record<string, { icon: string; color: string; bg: string }> = {
  water:           { icon: 'water',             color: '#64D2FF', bg: '#F0FAFF' },
  supplement:      { icon: 'medical',           color: '#AF52DE', bg: '#FAF5FF' },
  diet:            { icon: 'restaurant',        color: '#FF6723', bg: '#FFF7F0' },
  exercise:        { icon: 'fitness',           color: '#FF375F', bg: '#FFF5F7' },
  weight:          { icon: 'scale',             color: '#0A8F8F', bg: '#F0FFFD' },
  blood_pressure:  { icon: 'heart',             color: '#FF453A', bg: '#FFF5F5' },
  rhinitis:        { icon: 'water',             color: '#5AC8FA', bg: '#F0F9FF' },
  checkin:         { icon: 'checkbox',          color: '#30D158', bg: '#F0FFF4' },
  medication:      { icon: 'flask',             color: '#BF5AF2', bg: '#FAF5FF' },
  default:         { icon: 'checkmark-circle',  color: '#30D158', bg: '#F0FFF4' },
};

export function RecordCardView({ type, detail }: RecordData) {
  const cfg = ICONS[type] || ICONS.default;
  return (
    <View style={[styles.card, { backgroundColor: cfg.bg }]}>
      <Ionicons name={cfg.icon as any} size={16} color={cfg.color} />
      <Text style={txt.text}>{detail}</Text>
      <Ionicons name="checkmark-circle" size={14} color="#30D158" />
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
    // 记录类卡片数据由后端 handleDoneEvent 或 tool_result 决定, 这里给一个 fallback
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
  },
});

const txt = {
  text: { fontSize: 13, color: colors.labelPrimary, flex: 1 } as TextStyle,
};
