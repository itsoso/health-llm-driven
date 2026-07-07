import React from 'react';
import { ActivityIndicator, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import type { TodayBriefingRow } from '../../services/todayBriefingOverview';

export default function TodayBriefingOverview({
  rows,
  loading = false,
}: {
  rows: TodayBriefingRow[];
  loading?: boolean;
}) {
  if (!rows.length) return null;

  return (
    <View style={styles.card} testID="today-briefing-overview">
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={txt.overline}>今日简报</Text>
          <Text style={txt.title}>环境、规划与昨日回顾</Text>
        </View>
        {loading ? <ActivityIndicator size="small" color={C.green600} /> : null}
      </View>

      <View style={styles.rows}>
        {rows.map(row => (
          <View key={row.id} style={styles.row} testID={`today-briefing-row-${row.id}`}>
            <View style={styles.iconWrap}>
              <Ionicons name={row.icon as any} size={15} color={C.green600} />
            </View>
            <View style={styles.copy}>
              <View style={styles.copyTop}>
                <Text style={txt.label} numberOfLines={1}>{row.label}</Text>
                <Text style={txt.value} numberOfLines={1}>{row.value}</Text>
              </View>
              {row.detail ? (
                <Text style={txt.detail} numberOfLines={2}>{row.detail}</Text>
              ) : null}
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: revaSpacing.s4,
    gap: revaSpacing.s3,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
  },
  headerText: {
    flex: 1,
    minWidth: 0,
  },
  rows: {
    gap: revaSpacing.s3,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s3,
  },
  iconWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
    marginTop: 1,
  },
  copy: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  copyTop: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: revaSpacing.s2,
  },
});

const txt = {
  overline: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.green700,
  } as TextStyle,
  title: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 16,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  label: {
    width: 64,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.ink3,
  } as TextStyle,
  value: {
    flex: 1,
    minWidth: 0,
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  detail: {
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    lineHeight: 18,
    color: C.ink2,
  } as TextStyle,
};
