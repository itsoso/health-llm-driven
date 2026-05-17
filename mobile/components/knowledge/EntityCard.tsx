/**
 * EntityCard — render one system-knowledge entity (gene / snp / nutrient / etc.)
 *
 * Pure presentational, no fetch. Consumed inside ClaimSheet for each neighbor
 * entity returned by /knowledge/claim/{id}. Exported for reuse on future
 * standalone surfaces (e.g. an entity deep-link route).
 */
import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { KnowledgeDocument } from '../../services/systemKnowledge';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

const ENTITY_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  gene: 'git-branch',
  snp: 'flask',
  nutrient: 'leaf',
  supplement: 'medkit',
  biomarker: 'pulse',
  condition: 'medkit-outline',
  drug: 'bandage',
};

const ENTITY_LABEL: Record<string, string> = {
  gene: '基因',
  snp: '位点',
  nutrient: '营养素',
  supplement: '补剂',
  biomarker: '指标',
  condition: '健康状况',
  drug: '药物',
};

const EVIDENCE_LABEL: Record<string, string> = {
  A: 'A级',
  B: 'B级',
  C: 'C级',
  D: 'D级',
};

export function EntityCard({
  entity,
  onPress,
}: {
  entity: KnowledgeDocument;
  onPress?: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const type = entity.entity_type || 'other';
  const iconName = ENTITY_ICON[type] || 'document-text-outline';
  const typeLabel = ENTITY_LABEL[type] || type;
  const evidenceText = entity.evidence_level ? EVIDENCE_LABEL[entity.evidence_level] : null;

  const content = (
    <>
      <View style={styles.iconWrap}>
        <Ionicons name={iconName} size={14} color={c.brand} />
      </View>
      <View style={styles.body}>
        <View style={styles.headRow}>
          <Text style={styles.typeLabel}>{typeLabel}</Text>
          {evidenceText ? (
            <View style={styles.levelChip}>
              <Text style={styles.levelText}>{evidenceText}</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.title} numberOfLines={2}>
          {entity.title || entity.entity_id || entity.doc_id}
        </Text>
        {entity.summary ? (
          <Text style={styles.summary} numberOfLines={3}>
            {entity.summary}
          </Text>
        ) : null}
      </View>
      {onPress ? (
        <Ionicons
          name="chevron-forward"
          size={14}
          color={c.labelTertiary}
          style={styles.chevron}
        />
      ) : null}
    </>
  );

  if (onPress) {
    return (
      <Pressable
        testID={`knowledge-entity-card-${entity.doc_id}`}
        accessibilityRole="button"
        onPress={onPress}
        style={({ pressed }) => [styles.card, pressed && { opacity: 0.72 }]}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View testID={`knowledge-entity-card-${entity.doc_id}`} style={styles.card}>
      {content}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    card: {
      flexDirection: 'row',
      gap: 10,
      paddingVertical: 10,
      paddingHorizontal: 12,
      borderRadius: 10,
      backgroundColor: c.bgPrimary,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    iconWrap: {
      width: 26,
      height: 26,
      borderRadius: 13,
      backgroundColor: c.brandLight,
      alignItems: 'center',
      justifyContent: 'center',
      marginTop: 1,
    },
    body: {
      flex: 1,
    },
    chevron: {
      alignSelf: 'center',
    },
    headRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      marginBottom: 2,
    },
    typeLabel: {
      fontSize: 10,
      color: c.labelTertiary,
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: 0.3,
    },
    levelChip: {
      paddingHorizontal: 6,
      paddingVertical: 1,
      borderRadius: 3,
      backgroundColor: c.brandLight,
    },
    levelText: {
      fontSize: 9,
      color: c.brand,
      fontWeight: '600',
    },
    title: {
      fontSize: 13,
      fontWeight: '600',
      color: c.labelPrimary,
      lineHeight: 17,
    },
    summary: {
      marginTop: 3,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 15,
    },
  });
}
