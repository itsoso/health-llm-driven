/**
 * MetricTableCard — rank1 GenUI-first 的 metric_table 卡片 (Reva 设计语言)。
 *
 * 后端在 ```reva-ui fence 内下发 {"type":"metric_table","v":1,...},
 * revaUiBlocks 解析成 descriptor → 本卡渲染。仅接受后端下发 (match/build 恒 null)。
 *
 * 视觉:surface 卡面 + hairline 边 + 软阴影;首列为标签(左对齐 sans),
 * 其余列为数值(右对齐 mono + tabular-nums);行间发丝分隔;标题/脚注走 muted。
 * 数据 ≤12 行,纯 View 渲染 (无 FlatList,无滚动抖动)。
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaRadii, revaShadows, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import { parseMetricTable, type MetricTableData } from '../../../utils/metricTable';

export function MetricTableCardView(props: MetricTableData) {
  // 防御性重解析:descriptor.data 通常已规范化,但 SSE 直发路径可能带原始块。
  const data = parseMetricTable(props);
  if (!data) return <View />;
  const { title, columns, rows, footnote } = data;

  return (
    <View style={styles.card}>
      {title ? (
        <View style={styles.header}>
          <Ionicons name="grid-outline" size={14} color={C.green500} />
          <Text maxFontSizeMultiplier={1.3} style={styles.title} numberOfLines={2}>
            {title}
          </Text>
        </View>
      ) : null}

      <View style={styles.table}>
        <View style={[styles.row, styles.headRow]}>
          {columns.map((col, ci) => (
            <Text
              key={col.key}
              maxFontSizeMultiplier={1.2}
              numberOfLines={2}
              style={[styles.headCell, ci === 0 ? styles.firstCell : styles.numCell]}
            >
              {col.label}
            </Text>
          ))}
        </View>

        {rows.map((row, ri) => (
          <View
            key={ri}
            style={[styles.row, ri < rows.length - 1 ? styles.rowDivider : null]}
          >
            {columns.map((col, ci) => (
              <Text
                key={col.key}
                maxFontSizeMultiplier={1.3}
                numberOfLines={2}
                style={[
                  ci === 0 ? styles.labelCell : styles.valueCell,
                  ci === 0 ? styles.firstCell : styles.numCell,
                ]}
              >
                {row[col.key] || '—'}
              </Text>
            ))}
          </View>
        ))}
      </View>

      {footnote ? (
        <Text maxFontSizeMultiplier={1.2} style={styles.footnote}>
          {footnote}
        </Text>
      ) : null}
    </View>
  );
}

export const MetricTableCardSpec: CardSpec<MetricTableData> = {
  type: 'metric_table',
  label: '指标表格',
  match() {
    return null; // 仅接受后端下发 (reva-ui fence),不本地关键词触发
  },
  build() {
    return null;
  },
  render: (data) => <MetricTableCardView {...data} />,
};

const styles = StyleSheet.create({
  card: {
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginVertical: 6,
    minWidth: 240,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 8,
  },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '600',
    color: C.ink2,
    flexShrink: 1,
  } as TextStyle,
  table: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 7,
    gap: 8,
  },
  headRow: {
    paddingTop: 8,
    paddingBottom: 6,
  },
  rowDivider: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  firstCell: {
    flex: 1.4,
    textAlign: 'left',
  },
  numCell: {
    flex: 1,
    textAlign: 'right',
  },
  headCell: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
    color: C.ink3,
  } as TextStyle,
  labelCell: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '500',
    color: C.ink1,
  } as TextStyle,
  valueCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '500',
    color: C.ink1,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  footnote: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink3,
  } as TextStyle,
});
