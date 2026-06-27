import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import { revaColors as C, revaFonts, revaRadii } from '../../../constants/revaTheme';

interface AgendaActionData {
  id?: string | null;
  title?: string | null;
  subtitle?: string | null;
  scheduled_for?: string | null;
  source?: { object_type?: string; object_id?: number | string; slot?: string } | null;
  deep_link?: string | null;
}

export function AgendaActionCardView({
  title,
  subtitle,
  scheduled_for,
}: AgendaActionData) {
  return (
    <CardShell icon="sparkles" iconColor={C.green500} title="今日运行时行动" badge={scheduled_for ?? undefined} badgeColor={C.green500}>
      <View style={styles.row}>
        <View style={styles.marker}>
          <Ionicons name="arrow-forward" size={13} color={C.greenOn} />
        </View>
        <View style={styles.copy}>
          <Text maxFontSizeMultiplier={1.25} style={styles.title} numberOfLines={2}>
            {title || '补齐今天记录'}
          </Text>
          {subtitle ? (
            <Text maxFontSizeMultiplier={1.2} style={styles.subtitle} numberOfLines={2}>
              {subtitle}
            </Text>
          ) : null}
        </View>
      </View>
    </CardShell>
  );
}

export const AgendaActionCardSpec: CardSpec<AgendaActionData> = {
  type: 'agenda_action',
  label: '今日运行时行动',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <AgendaActionCardView {...data} />,
};

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  marker: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green500,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, minWidth: 0 },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '800',
    color: C.ink1,
  },
  subtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12.5,
    lineHeight: 17,
    color: C.ink2,
    marginTop: 3,
  },
});
