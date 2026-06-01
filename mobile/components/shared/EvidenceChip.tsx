/**
 * EvidenceChip —— 行内证据等级胶囊 (2026-05-12 review #1).
 *
 * 在卡片列表 row 里露出 evidence_level 让用户一眼分辨"强证据可执行"vs
 * "需医生介入". 详情页用大 chip, 列表用 compact 这版.
 *
 * 2026-06-01: 4 档颜色从硬编码 hex 改走 semanticColors (useTheme().s), 自动暗色适配.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme, type SemanticTone } from '../../hooks/useTheme';

interface Props {
  level?: 'high' | 'medium' | 'low' | 'medical_grade' | string | null;
}

const CONF: Record<string, { tone: SemanticTone; label: string }> = {
  high: { tone: 'success', label: '强证据' },
  medium: { tone: 'warning', label: '中等' },
  low: { tone: 'neutral', label: '弱证据' },
  medical_grade: { tone: 'danger', label: '需医生' },
};

export default function EvidenceChip({ level }: Props) {
  const { s } = useTheme();
  if (!level || !CONF[level]) return null;
  const conf = CONF[level];
  const tone = s[conf.tone];
  return (
    <View style={[styles.chip, { backgroundColor: tone.bg }]}>
      <Text style={[styles.text, { color: tone.fg }]}>{conf.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 },
  text: { fontSize: 9, fontWeight: '700' },
});
