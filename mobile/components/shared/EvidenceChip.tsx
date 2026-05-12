/**
 * EvidenceChip —— 行内证据等级胶囊 (2026-05-12 review #1).
 *
 * 在卡片列表 row 里露出 evidence_level 让用户一眼分辨"强证据可执行"vs
 * "需医生介入". 详情页用大 chip, 列表用 compact 这版.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

interface Props {
  level?: 'high' | 'medium' | 'low' | 'medical_grade' | string | null;
}

const CONF: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: '#D1FAE5', text: '#065F46', label: '强证据' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '中等' },
  low: { bg: '#F1F5F9', text: '#475569', label: '弱证据' },
  medical_grade: { bg: '#FEE2E2', text: '#991B1B', label: '需医生' },
};

export default function EvidenceChip({ level }: Props) {
  if (!level || !CONF[level]) return null;
  const c = CONF[level];
  return (
    <View style={[styles.chip, { backgroundColor: c.bg }]}>
      <Text style={[styles.text, { color: c.text }]}>{c.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  text: { fontSize: 9, fontWeight: '700' },
});
