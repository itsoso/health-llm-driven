import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, shadows, spacing } from '../../constants/theme';
import type { AgentAgenda, AgentAgendaItem, AgentAgendaSection } from '../../services/agentAgenda';

interface Props {
  agenda?: AgentAgenda;
  onOpenItem: (item: AgentAgendaItem) => void;
}

const SECTION_META: Record<AgentAgendaSection['key'], { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  watching: { icon: 'scan-outline', color: colors.brand },
  waiting: { icon: 'hourglass-outline', color: '#FF9F0A' },
  missing_data: { icon: 'cloud-upload-outline', color: '#FF453A' },
};

export default function AgentAgendaPanel({ agenda, onOpenItem }: Props) {
  const [collapsed, setCollapsed] = useState(false);

  if (!agenda || agenda.sections.length === 0) return null;

  const toggle = () => {
    Haptics.selectionAsync();
    setCollapsed(v => !v);
  };

  // 计算总条数供 collapsed 态展示
  const totalItems = agenda.sections.reduce((sum, s) => sum + (s.items?.length || 0), 0);

  return (
    <View style={styles.panel}>
      <Pressable onPress={toggle} style={styles.header} accessibilityRole="button" accessibilityLabel={collapsed ? '展开 Agent 议程' : '收起 Agent 议程'}>
        <View style={styles.headerLeft}>
          <Ionicons name="pulse-outline" size={15} color={colors.brand} />
          <Text style={txt.header}>Agent 议程</Text>
          {collapsed && <Text style={txt.countBadge}>{totalItems}</Text>}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={txt.date}>{agenda.date.slice(5)}</Text>
          <Ionicons
            name={collapsed ? 'chevron-down' : 'chevron-up'}
            size={16}
            color={colors.labelTertiary}
          />
        </View>
      </Pressable>

      {!collapsed && agenda.sections.slice(0, 3).map(section => {
        const meta = SECTION_META[section.key];
        return (
          <View key={section.key} style={styles.section}>
            <View style={styles.sectionHeader}>
              <Ionicons name={meta.icon} size={13} color={meta.color} />
              <Text style={[txt.sectionTitle, { color: meta.color }]}>{section.title}</Text>
            </View>
            {section.items.slice(0, 2).map(item => (
              <Pressable
                key={item.id}
                style={({ pressed }) => [styles.row, pressed && item.route && styles.rowPressed]}
                onPress={() => item.route ? onOpenItem(item) : undefined}
                disabled={!item.route}
                accessibilityRole={item.route ? 'button' : 'text'}
                accessibilityLabel={item.title}
              >
                <View style={[styles.dot, { backgroundColor: toneColor(item.tone) }]} />
                <View style={styles.rowText}>
                  <Text style={txt.itemTitle} numberOfLines={1}>{item.title}</Text>
                  {item.subtitle ? <Text style={txt.itemSubtitle} numberOfLines={1}>{item.subtitle}</Text> : null}
                </View>
                {item.route ? <Ionicons name="chevron-forward" size={14} color={colors.labelTertiary} /> : null}
              </Pressable>
            ))}
          </View>
        );
      })}
    </View>
  );
}

function toneColor(tone: AgentAgendaItem['tone']): string {
  if (tone === 'good') return '#0A8F8F';
  if (tone === 'bad') return '#FF453A';
  if (tone === 'warn') return '#FF9F0A';
  return colors.labelTertiary;
}

const styles = StyleSheet.create({
  panel: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: 10,
    ...shadows.subtle,
  },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  section: { gap: 5 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  row: {
    minHeight: 42,
    borderRadius: radii.sm,
    backgroundColor: colors.bgPrimary,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  rowPressed: { opacity: 0.82 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  rowText: { flex: 1 },
});

const txt = {
  header: { fontSize: 14, fontWeight: '800', color: colors.labelPrimary } as TextStyle,
  date: { fontSize: 11, color: colors.labelTertiary, fontWeight: '600' } as TextStyle,
  sectionTitle: { fontSize: 11, fontWeight: '800' } as TextStyle,
  itemTitle: { fontSize: 13, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  itemSubtitle: { fontSize: 11, color: colors.labelSecondary, marginTop: 1 } as TextStyle,
  countBadge: {
    fontSize: 10, fontWeight: '700', color: colors.labelSecondary,
    backgroundColor: colors.fill, paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 8, overflow: 'hidden',
  } as TextStyle,
};
