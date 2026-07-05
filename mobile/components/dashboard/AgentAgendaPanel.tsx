import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { AgentAgenda, AgentAgendaItem, AgentAgendaSection } from '../../services/agentAgenda';
import DashboardCard, { CardCountBadge } from './DashboardCard';

interface Props {
  agenda?: AgentAgenda;
  onOpenItem: (item: AgentAgendaItem) => void;
}

function sectionMeta(key: AgentAgendaSection['key'], c: ColorPalette) {
  switch (key) {
    case 'watching':     return { icon: 'scan-outline' as const,           color: c.brand };
    case 'waiting':      return { icon: 'hourglass-outline' as const,      color: c.amber };
    case 'missing_data': return { icon: 'cloud-upload-outline' as const,   color: c.red };
  }
}

function toneColor(tone: AgentAgendaItem['tone'], c: ColorPalette): string {
  if (tone === 'good') return c.brand;
  if (tone === 'bad')  return c.red;
  if (tone === 'warn') return c.amber;
  return c.labelTertiary;
}

export default function AgentAgendaPanel({ agenda, onOpenItem }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  if (!agenda || agenda.sections.length === 0) return null;

  const totalItems = agenda.sections.reduce((sum, s) => sum + (s.items?.length || 0), 0);

  return (
    <DashboardCard
      icon="pulse-outline"
      kicker={agenda.date.slice(5)}
      title="小巴议程"
      collapsible
      defaultCollapsed
      trailing={<CardCountBadge value={totalItems} />}
      accessibilityLabel="小巴议程"
    >
      {agenda.sections.slice(0, 3).map(section => {
        const meta = sectionMeta(section.key, c);
        return (
          <View key={section.key} style={styles.section}>
            <View style={styles.sectionHeader}>
              <Ionicons name={meta.icon} size={13} color={meta.color} />
              <Text style={[styles.sectionTitle, { color: meta.color }]}>{section.title}</Text>
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
                <View style={[styles.dot, { backgroundColor: toneColor(item.tone, c) }]} />
                <View style={styles.rowText}>
                  <Text style={styles.itemTitle} numberOfLines={1}>{item.title}</Text>
                  {item.subtitle ? <Text style={styles.itemSubtitle} numberOfLines={1}>{item.subtitle}</Text> : null}
                </View>
                {item.route ? <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} /> : null}
              </Pressable>
            ))}
          </View>
        );
      })}
    </DashboardCard>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    section: { gap: 6 },
    sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 5 },
    row: {
      minHeight: 42,
      borderRadius: radii.sm,
      backgroundColor: c.bgPrimary,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingHorizontal: 10,
      paddingVertical: 7,
    },
    rowPressed: { opacity: 0.82 },
    dot: { width: 6, height: 6, borderRadius: 3 },
    rowText: { flex: 1 },
    sectionTitle: { fontSize: 11, fontWeight: '800' } as TextStyle,
    itemTitle: { fontSize: 13, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    itemSubtitle: { fontSize: 11, color: c.labelSecondary, marginTop: 1 } as TextStyle,
  });
}
