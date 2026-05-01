import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, spacing } from '../../constants/theme';
import type { AgentAgenda, AgentAgendaItem, AgentAgendaSection } from '../../services/agentAgenda';
import DashboardCard, { CardCountBadge } from './DashboardCard';

interface Props {
  agenda?: AgentAgenda;
  onOpenItem: (item: AgentAgendaItem) => void;
}

const SECTION_META: Record<AgentAgendaSection['key'], { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  watching: { icon: 'scan-outline', color: colors.brand },
  waiting: { icon: 'hourglass-outline', color: '#FF9F0A' },
  missing_data: { icon: 'cloud-upload-outline', color: '#FF453A' },
};

function toneColor(tone: AgentAgendaItem['tone']): string {
  if (tone === 'good') return '#0A8F8F';
  if (tone === 'bad')  return '#FF453A';
  if (tone === 'warn') return '#FF9F0A';
  return colors.labelTertiary;
}

export default function AgentAgendaPanel({ agenda, onOpenItem }: Props) {
  if (!agenda || agenda.sections.length === 0) return null;

  const totalItems = agenda.sections.reduce((sum, s) => sum + (s.items?.length || 0), 0);

  return (
    <DashboardCard
      icon="pulse-outline"
      iconTint={colors.brandLight}
      iconColor={colors.brand}
      kicker={agenda.date.slice(5)}
      kickerColor={colors.labelTertiary}
      title="Agent 议程"
      collapsible
      defaultCollapsed
      trailing={<CardCountBadge value={totalItems} />}
      accessibilityLabel="Agent 议程"
    >
      {agenda.sections.slice(0, 3).map(section => {
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
    </DashboardCard>
  );
}

const styles = StyleSheet.create({
  section: { gap: 6 },
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
  sectionTitle: { fontSize: 11, fontWeight: '800' } as TextStyle,
  itemTitle: { fontSize: 13, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  itemSubtitle: { fontSize: 11, color: colors.labelSecondary, marginTop: 1 } as TextStyle,
};
