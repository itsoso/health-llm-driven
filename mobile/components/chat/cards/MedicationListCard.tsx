/**
 * MedicationListCard — 「在用药物」结构化卡(汇总卡族第三张,复元 Reva 设计语言)。
 *
 * 后端经 ```reva-ui fence 内联下发(与 diet/sleep/metric_table 同通道):
 *   {"type":"medication_list","v":1,"data":{...}}
 * → ChatBubble extractRevaUiBlocks(utils/revaUiBlocks.ts 认这个 type)→ renderCard → 本卡。
 * **v 是整数 1**,parser 校验 v===1(diet 上线即坏的教训)。
 *
 * 结构:壳 + 2 行头走 **StatusSummary scaffold**(statusSummary.tsx);本卡只保留领域主体 ——
 * 逐条药物(药名 / 剂量·频次·时点 / 分类·用途 标签)。视觉与 diet/sleep 卡同语言。
 *
 * **R4**:本卡只如实呈现用户自己的用药记录 —— 不提建议、不提醒服药、不评价方案。
 * 契约里除 name 外全部可能缺失,缺什么就不渲染那一格(绝不显示 'null'/'undefined',绝不补写)。
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaFonts, revaRadii, revaSemantic } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import { StatusSummaryShell, fmtNum, pickText } from './statusSummary';

interface Medication {
  name: string;
  /** 剂量 · 频次 · 时点 —— 已过滤缺失项,可能为空数组(则不渲染该行)。 */
  meta: string[];
  /** 分类 / 用途 弱化标签 —— 已过滤缺失项。 */
  tags: string[];
  // 刻意**没有** hasSafetyAlert:后端的 safety_alerts 是**用户级**的(服务端按整个用药方案
  // 跑 PGx/DDI/DSI, 把同一份挂到每个条目)→ 逐药徽标会把一条 dsi.ppi_b12 归因到无关的
  // 铝碳酸镁 = 编造因果。安全信号只在**卡级**呈现(见下方 alertCount)。
}

/**
 * 一条用药记录 → 渲染模型。`name` 是唯一必需字段:缺失 → 丢弃该条(无名之药不可呈现)。
 * 其余字段逐个 pickText,缺失即不进数组 → 渲染时该格自然消失。
 */
function parseMedications(raw: unknown): Medication[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): Medication | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      const name = pickText(r.name);
      if (!name) return null;
      const meta = [r.dosage, r.frequency, r.timing_label]
        .map(pickText)
        .filter((v): v is string => Boolean(v));
      const tags = [r.category, r.purpose]
        .map(pickText)
        .filter((v): v is string => Boolean(v));
      return { name, meta, tags };
    })
    .filter((m): m is Medication => m != null);
}

export function MedicationListCardView({ data }: { data?: unknown }) {
  const d = (data && typeof data === 'object') ? (data as Record<string, any>) : {};
  const meds = parseMedications(d.medications);

  // total 缺失时退到实际渲染条数(可直接观察到的事实,非编造);两者皆无 → 不显示计数。
  const totalText = fmtNum(d.total) ?? (meds.length > 0 ? String(meds.length) : null);
  // 卡级安全信号(**非逐药**):safety_alert_count 是该用户用药安全告警的**条数**,
  // 不是"有告警的药品数" —— 服务端按整个方案跑规则, 无法归因到具体某味药。
  // 措辞必须是「N 条用药安全提示」而非「N 条药有提示」(后者=逐药归因=编造因果)。
  const alertCount = fmtNum(d.safety_alert_count);
  const hasAlertCount = alertCount != null && Number(alertCount) > 0;
  const subtitleParts = [
    totalText ? `共 ${totalText} 条` : null,
    hasAlertCount ? `${alertCount} 条用药安全提示` : null,
  ].filter((p): p is string => Boolean(p));

  return (
    <StatusSummaryShell
      icon="medkit-outline"
      title="在用药物"
      subtitle={subtitleParts.length > 0 ? subtitleParts.join(' · ') : undefined}
    >
      {meds.length > 0 ? (
        <View style={styles.list}>
          {meds.map((m, i) => (
            <View key={i} style={[styles.medRow, i < meds.length - 1 ? styles.rowDivider : null]}>
              <View style={styles.nameRow}>
                <Text maxFontSizeMultiplier={1.25} style={styles.medName}>{m.name}</Text>
              </View>

              {m.meta.length > 0 ? (
                <Text maxFontSizeMultiplier={1.2} style={styles.medMeta}>{m.meta.join(' · ')}</Text>
              ) : null}

              {m.tags.length > 0 ? (
                <View style={styles.tagRow}>
                  {m.tags.map((t, ti) => (
                    <View key={ti} style={styles.tag}>
                      <Text maxFontSizeMultiplier={1.1} style={styles.tagText} numberOfLines={1}>{t}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}

      {/* 卡级安全提示条(加层不减层:有告警时绝不让清单看起来"没事")。
          刻意**不逐药**标记 —— 告警是用户级的, 指不到具体某味药。正文留给安全面板/散文,
          此处只给存在性 + 条数, 不把告警二次改写成弱化版。 */}
      {hasAlertCount ? (
        <View
          style={styles.alertChip}
          accessible
          accessibilityRole="text"
          accessibilityLabel={`你有 ${alertCount} 条用药安全提示，详见安全告警`}
        >
          <Ionicons name="alert-circle" size={12} color={revaSemantic.caution.fg} />
          <Text maxFontSizeMultiplier={1.1} style={styles.alertChipText}>
            {`${alertCount} 条用药安全提示 · 详见安全告警`}
          </Text>
        </View>
      ) : null}
    </StatusSummaryShell>
  );
}

export const MedicationListCardSpec: CardSpec = {
  type: 'medication_list',
  label: '在用药物',
  match() {
    return null; // 仅接受后端下发 (reva-ui fence), 不本地关键词触发
  },
  build() {
    return null;
  },
  render: (data) => <MedicationListCardView data={data} />,
};

// 领域专属样式:逐条药物列表(壳/头样式在 statusSummary.tsx)。
const styles = StyleSheet.create({
  list: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  medRow: { paddingVertical: 9, gap: 3 },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 6,
  },
  medName: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    lineHeight: 18,
  } as TextStyle,
  alertChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: revaRadii.xs,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: revaSemantic.caution.bg,
  },
  alertChipText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.2,
    color: revaSemantic.caution.fg,
    lineHeight: 14,
  } as TextStyle,
  medMeta: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    color: C.ink2,
    lineHeight: 16,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 4,
    marginTop: 1,
  },
  tag: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: revaRadii.xs,
    backgroundColor: C.paper2,
  },
  tagText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '600',
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
});
