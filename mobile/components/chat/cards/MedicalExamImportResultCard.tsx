import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { pushChatWithContext } from '../../../utils/agentContext';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

export interface MedicalExamImportResultCardData {
  exam_id: number;
  exam_date?: string | null;
  exam_type?: string | null;
  hospital_name?: string | null;
  items_count?: number | null;
  abnormal_count?: number | null;
  conclusions_count?: number | null;
  conclusion?: string | null;
  source: 'pdf' | 'image' | 'text' | string;
  review_required?: boolean;
  safety_note?: string;
}

function sourceLabel(source: string): string {
  if (source === 'pdf') return 'PDF';
  if (source === 'image') return '图片 OCR';
  if (source === 'text') return '文字';
  return source;
}

export function MedicalExamImportResultCardView(data: MedicalExamImportResultCardData) {
  const router = useRouter();
  const itemsCount = data.items_count ?? 0;
  const abnormalCount = data.abnormal_count ?? 0;
  const safetyNote = data.safety_note ?? 'OCR/AI 解析结果需要复核后再用于判断。';

  return (
    <CardShell
      icon="document-text"
      iconColor={C.green500}
      title="体检报告已导入"
      badge={abnormalCount > 0 ? `${abnormalCount} 项异常` : '待复核'}
      badgeColor={abnormalCount > 0 ? revaSemantic.risk.fg : C.green500}
      bg={C.green50}
    >
      <View style={styles.metaRow}>
        <Metric label="来源" value={sourceLabel(String(data.source))} />
        <Metric label="指标" value={`${itemsCount} 项指标`} />
        <Metric label="异常" value={`${abnormalCount} 项异常`} risk={abnormalCount > 0} />
      </View>

      {(data.exam_date || data.hospital_name) ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.detail} numberOfLines={2}>
          {[data.exam_date, data.hospital_name].filter(Boolean).join(' · ')}
        </Text>
      ) : null}

      {data.conclusion ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.conclusion} numberOfLines={2}>
          {data.conclusion}
        </Text>
      ) : null}

      {data.review_required !== false ? (
        <View style={styles.warning}>
          <Ionicons name="alert-circle-outline" size={13} color={revaSemantic.caution.fg} />
          <Text maxFontSizeMultiplier={1.3} style={styles.warningText}>
            {safetyNote}
          </Text>
        </View>
      ) : null}

      <View style={styles.actionRow}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="查看体检记录"
          style={({ pressed }) => [styles.secondaryAction, pressed && styles.pressed]}
          onPress={() => router.push('/medical-exams' as any)}
        >
          <Text style={styles.secondaryActionText}>查看体检记录</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="让 Reva 解读这次导入"
          style={({ pressed }) => [styles.primaryAction, pressed && styles.pressed]}
          onPress={() => pushChatWithContext(router, {
            prompt: '请基于我刚导入的体检报告，解释异常/关键指标、需要复核的地方，以及接下来 30 天最重要的健康行动。',
            context: {
              from: 'chat/medical_exam_import_result_card',
              import_result: {
                exam_id: data.exam_id,
                exam_date: data.exam_date ?? null,
                exam_type: data.exam_type ?? null,
                hospital_name: data.hospital_name ?? null,
                items_count: data.items_count ?? null,
                abnormal_count: data.abnormal_count ?? null,
                conclusions_count: data.conclusions_count ?? null,
                conclusion: data.conclusion ?? null,
                source: data.source,
                review_required: data.review_required ?? true,
              },
              safety_boundary: safetyNote,
            },
            badge: '体检导入结果',
            newChat: false,
          })}
        >
          <Text style={styles.primaryActionText}>让 Reva 解读</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

function Metric({ label, value, risk }: { label: string; value: string; risk?: boolean }) {
  return (
    <View style={styles.metric}>
      <Text maxFontSizeMultiplier={1.2} style={styles.metricLabel}>{label}</Text>
      <Text maxFontSizeMultiplier={1.2} style={[styles.metricValue, risk && styles.metricRisk]}>{value}</Text>
    </View>
  );
}

export const MedicalExamImportResultCardSpec: CardSpec<MedicalExamImportResultCardData> = {
  type: 'medical_exam_import_result',
  label: '体检导入结果',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <MedicalExamImportResultCardView {...data} />,
};

const styles = StyleSheet.create({
  metaRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  metric: {
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    minWidth: 68,
  },
  metricLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink3 } as TextStyle,
  metricValue: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '800', color: C.ink1 } as TextStyle,
  metricRisk: { color: revaSemantic.risk.fg },
  detail: { marginTop: 8, fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2 } as TextStyle,
  conclusion: { marginTop: 6, fontFamily: revaFonts.sans, fontSize: 12, color: C.ink1, lineHeight: 17 } as TextStyle,
  warning: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
    marginTop: 8,
    padding: 8,
    borderRadius: revaRadii.md,
    backgroundColor: revaSemantic.caution.bg,
  },
  warningText: { flex: 1, fontFamily: revaFonts.sans, fontSize: 11, color: revaSemantic.caution.fg, lineHeight: 16 } as TextStyle,
  actionRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  primaryAction: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 9,
    borderRadius: revaRadii.md,
    backgroundColor: C.green500,
  },
  primaryActionText: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '800', color: '#fff' } as TextStyle,
  secondaryAction: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 9,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green500,
    backgroundColor: C.surface,
  },
  secondaryActionText: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '800', color: C.green500 } as TextStyle,
  pressed: { opacity: 0.72 },
});
