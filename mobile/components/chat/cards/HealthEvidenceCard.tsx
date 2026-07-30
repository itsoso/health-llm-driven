import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type {
  CardSpec,
  HealthEvidenceAuthoritySource,
  HealthEvidenceCardData,
  HealthEvidenceContinuationPayload,
  HealthEvidenceParentReference,
  HealthEvidenceProjectionItem,
} from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

interface DisplayItem {
  label: string;
  meta?: string;
}

interface FollowUpPrompt {
  discriminatorId: string;
  question: string;
  choices: string[];
}

const CATEGORY_LABELS: Record<string, string> = {
  symptom: '症状时间线',
  symptoms: '症状时间线',
  active_problem: '当前健康问题',
  active_problems: '当前健康问题',
  medicine: '当前用药类别',
  medicines: '当前用药类别',
  medication: '当前用药类别',
  medications: '当前用药类别',
  allergy: '过敏史',
  allergies: '过敏史',
  chronic_condition: '慢性病背景',
  chronic_conditions: '慢性病背景',
  conditions: '健康问题',
  lab: '检查与化验',
  labs: '检查与化验',
  genetic: '基因信息',
  genetics: '基因信息',
  wearable: '可穿戴趋势',
  wearables: '可穿戴趋势',
  diet: '饮食记录',
};

const SOURCE_KIND_LABELS: Record<string, string> = {
  guideline: '临床指南',
  clinical_guideline: '临床指南',
  official_guidance: '官方指南',
  regulator: '监管机构',
  drug_label: '药品说明书',
  label: '药品说明书',
  systematic_review: '系统综述',
  meta_analysis: '荟萃分析',
  research: '研究证据',
  database: '权威数据库',
  clinical_reference: '临床参考',
};

function textValue(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized || undefined;
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function listValue(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  return value == null ? [] : [value];
}

function firstText(
  record: object,
  keys: readonly string[],
): string | undefined {
  const values = record as Record<string, unknown>;
  for (const key of keys) {
    const value = textValue(values[key]);
    if (value) return value;
  }
  return undefined;
}

function dedupeItems(items: DisplayItem[], limit: number): DisplayItem[] {
  const seen = new Set<string>();
  const result: DisplayItem[] = [];
  for (const item of items) {
    const key = `${item.label}\u0000${item.meta ?? ''}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
    if (result.length >= limit) break;
  }
  return result;
}

function projectionItem(value: unknown): DisplayItem | undefined {
  const direct = textValue(value);
  if (direct) return { label: direct };
  const record = recordValue(value) as HealthEvidenceProjectionItem | undefined;
  if (!record) return undefined;
  const label = firstText(record, [
    'label',
    'question',
    'prompt',
    'message',
    'title',
    'summary',
  ]);
  if (label) return { label };

  const category = firstText(record, ['category']);
  const state = firstText(record, ['state'])?.toLowerCase();
  if (!category || !state) return undefined;
  const categoryLabel = CATEGORY_LABELS[category.toLowerCase()] || category;
  if (state === 'failed') return { label: `${categoryLabel}暂时读取失败` };
  if (state === 'absent') return { label: `缺少${categoryLabel}` };
  return undefined;
}

function isExplicitRedFlag(value: unknown): boolean {
  const record = recordValue(value);
  if (!record) return false;
  if (record.is_red_flag === true) return true;
  const marker = firstText(record, ['priority', 'urgency', 'severity'])?.toLowerCase();
  return ['red_flag', 'urgent', 'emergency', 'critical'].includes(marker ?? '');
}

function readDetectedRedFlags(data: HealthEvidenceCardData): DisplayItem[] {
  const explicit = [
    ...listValue(data.detected_red_flags),
    ...listValue(data.red_flags),
  ];
  return dedupeItems(
    explicit.map(projectionItem).filter((item): item is DisplayItem => Boolean(item)),
    4,
  );
}

function readSafetyPrecautions(data: HealthEvidenceCardData): DisplayItem[] {
  return dedupeItems(
    [
      ...listValue(data.safety_precautions),
      // Backward compatibility: older servers mislabeled conditional
      // precautions as ``urgent_red_flags``. Never present them as detected.
      ...listValue(data.urgent_red_flags),
    ]
      .map(projectionItem)
      .filter((item): item is DisplayItem => Boolean(item)),
    4,
  );
}

function readPendingRedFlags(data: HealthEvidenceCardData): DisplayItem[] {
  return dedupeItems(
    listValue(data.missing_discriminators)
      .filter(isExplicitRedFlag)
      .map(projectionItem)
      .filter((item): item is DisplayItem => Boolean(item)),
    4,
  );
}

function sourceKindLabel(value: unknown): string | undefined {
  const kind = textValue(value);
  if (!kind) return undefined;
  return SOURCE_KIND_LABELS[kind.toLowerCase()] || kind.replace(/_/g, ' ');
}

function sourceItem(value: unknown): DisplayItem | undefined {
  const direct = textValue(value);
  if (direct) return { label: direct };
  const record = recordValue(value) as HealthEvidenceAuthoritySource | undefined;
  if (!record) return undefined;
  const label = firstText(record, [
    'title',
    'display_name',
    'source_name',
    'name',
  ]);
  if (!label) return undefined;

  const organization = firstText(record, ['organization', 'publisher']);
  const sourceKind = sourceKindLabel(record.source_kind ?? record.kind);
  const evidenceLevel = textValue(record.evidence_level);
  const metaParts = [organization, sourceKind, evidenceLevel ? `${evidenceLevel.toUpperCase()}级` : undefined]
    .filter((part): part is string => Boolean(part) && part !== label);

  return {
    label,
    meta: metaParts.length ? metaParts.join(' · ') : undefined,
  };
}

function readSources(data: HealthEvidenceCardData): DisplayItem[] {
  return dedupeItems(
    [
      ...listValue(data.authority_sources),
      ...listValue(data.sources),
    ]
      .map(sourceItem)
      .filter((item): item is DisplayItem => Boolean(item)),
    4,
  );
}

function categoryItem(value: unknown): DisplayItem | undefined {
  const direct = textValue(value);
  if (direct) return { label: CATEGORY_LABELS[direct.toLowerCase()] || direct };
  const record = recordValue(value);
  if (!record) return undefined;
  const label = firstText(record, ['label', 'title', 'name']);
  if (label) return { label };
  const category = firstText(record, ['category']);
  if (!category) return undefined;
  return { label: CATEGORY_LABELS[category.toLowerCase()] || category };
}

function readCategories(data: HealthEvidenceCardData): DisplayItem[] {
  return dedupeItems(
    listValue(data.context_categories_used)
      .map(categoryItem)
      .filter((item): item is DisplayItem => Boolean(item)),
    6,
  );
}

function readFollowUps(data: HealthEvidenceCardData): FollowUpPrompt[] {
  const prompts: FollowUpPrompt[] = [];
  const seen = new Set<string>();
  for (const value of listValue(data.missing_discriminators)) {
    const record = recordValue(value);
    const discriminatorId = record ? firstText(record, ['id']) : undefined;
    const question = record ? firstText(record, ['question']) : undefined;
    if (!record || !discriminatorId || !question || seen.has(discriminatorId)) continue;
    const choices = dedupeItems(
      listValue(record.choices)
        .map(textValue)
        .filter((choice): choice is string => Boolean(choice))
        .map((label) => ({ label })),
      4,
    ).map((item) => item.label);
    if (!choices.length) continue;
    seen.add(discriminatorId);
    prompts.push({ discriminatorId, question, choices });
    if (prompts.length >= 4) break;
  }
  return prompts;
}

function projectTextList(value: unknown): string[] {
  return listValue(value)
    .map(textValue)
    .filter((item): item is string => Boolean(item));
}

function projectRecords(
  value: unknown,
  textKeys: readonly string[],
  booleanKeys: readonly string[] = [],
  listKeys: readonly string[] = [],
): Record<string, unknown>[] {
  return listValue(value)
    .map(recordValue)
    .filter((item): item is Record<string, unknown> => Boolean(item))
    .map((item) => {
      const projected: Record<string, unknown> = {};
      for (const key of textKeys) {
        const text = textValue(item[key]);
        if (text) projected[key] = text;
      }
      for (const key of booleanKeys) {
        if (typeof item[key] === 'boolean') projected[key] = item[key];
      }
      for (const key of listKeys) {
        const values = projectTextList(item[key]);
        if (values.length) projected[key] = values;
      }
      return projected;
    })
    .filter((item) => Object.keys(item).length > 0);
}

/**
 * Project the backend public contract again at the Mobile network boundary.
 * Unknown/private/raw fields never enter card state or restored history.
 */
export function projectHealthEvidenceCardData(value: unknown): HealthEvidenceCardData {
  const source = recordValue(value);
  if (!source) return {};
  const projected: Record<string, unknown> = {};
  for (const key of ['version', 'risk_level', 'sufficiency', 'verifier_verdict'] as const) {
    const text = textValue(source[key]);
    if (text) projected[key] = text;
  }
  if (typeof source.truncated === 'boolean') projected.truncated = source.truncated;

  const intent = recordValue(source.intent);
  if (intent) {
    const publicIntent: Record<string, unknown> = {};
    for (const key of ['version', 'intent_id', 'intent', 'domain', 'risk_level'] as const) {
      const text = textValue(intent[key]);
      if (text) publicIntent[key] = text;
    }
    const discriminatorIds = projectTextList(intent.mandatory_discriminator_ids);
    if (discriminatorIds.length) {
      publicIntent.mandatory_discriminator_ids = discriminatorIds;
    }
    for (const key of ['requires_personal_context', 'requires_authority'] as const) {
      if (typeof intent[key] === 'boolean') publicIntent[key] = intent[key];
    }
    if (Object.keys(publicIntent).length) projected.intent = publicIntent;
  }

  const categories = listValue(source.context_categories_used)
    .map((item): unknown => {
      const direct = textValue(item);
      if (direct) return direct;
      return projectRecords([item], ['category', 'label'])[0];
    })
    .filter((item) => item != null);
  if (categories.length) projected.context_categories_used = categories;

  for (const key of ['evidence_refs', 'authority_evidence_refs'] as const) {
    const refs = projectTextList(source[key]);
    if (Array.isArray(source[key]) || refs.length) projected[key] = refs;
  }

  const sources = projectRecords(
    source.authority_sources,
    [
      'source_id',
      'source',
      'title',
      'display_name',
      'name',
      'source_name',
      'organization',
      'publisher',
      'source_kind',
      'kind',
      'evidence_level',
      'version',
      'authority_tier',
    ],
  );
  if (Array.isArray(source.authority_sources) || sources.length) {
    projected.authority_sources = sources;
  }
  const sourceAliases = projectRecords(
    source.sources,
    [
      'source_id',
      'source',
      'title',
      'display_name',
      'name',
      'source_name',
      'organization',
      'publisher',
      'source_kind',
      'kind',
      'evidence_level',
      'version',
      'authority_tier',
    ],
  );
  if (Array.isArray(source.sources) || sourceAliases.length) {
    projected.sources = sourceAliases;
  }

  const missing = projectRecords(
    source.missing_discriminators,
    ['id', 'question', 'label', 'priority', 'urgency', 'severity'],
    ['is_red_flag'],
    ['choices'],
  );
  if (Array.isArray(source.missing_discriminators) || missing.length) {
    projected.missing_discriminators = missing;
  }
  for (const key of [
    'red_flags',
    'urgent_red_flags',
    'detected_red_flags',
    'safety_precautions',
  ] as const) {
    const flags = projectRecords(
      source[key],
      ['id', 'label', 'priority', 'urgency', 'severity'],
      ['is_red_flag'],
    );
    if (Array.isArray(source[key]) || flags.length) projected[key] = flags;
  }

  const limitations = projectTextList(source.limitations);
  if (Array.isArray(source.limitations) || limitations.length) {
    projected.limitations = limitations;
  }
  const gaps = projectRecords(source.gaps, ['category', 'state']);
  if (Array.isArray(source.gaps) || gaps.length) projected.gaps = gaps;
  const conflicts = projectRecords(source.conflicts, ['category']);
  if (Array.isArray(source.conflicts) || conflicts.length) projected.conflicts = conflicts;

  return projected as HealthEvidenceCardData;
}

function parentIntentId(data: HealthEvidenceCardData): string | undefined {
  const intent = recordValue(data.intent);
  return intent ? firstText(intent, ['intent_id']) : undefined;
}

function normalizeContinuationAnswer(value: string): 'yes' | 'no' | 'unknown' {
  switch (value.trim().toLowerCase()) {
    case 'yes':
    case '有':
      return 'yes';
    case 'no':
    case '没有':
      return 'no';
    case 'unknown':
    case '不确定':
      return 'unknown';
    default:
      return 'unknown';
  }
}

function continuationContext(
  prompts: FollowUpPrompt[],
  answers: Record<string, string>,
  intentId: string,
  parent: HealthEvidenceParentReference,
): string {
  const payload: HealthEvidenceContinuationPayload = {
    version: 'health-evidence-continuation.v1',
    parent_intent_id: intentId,
    parent_message_id: parent.messageRef as number,
    ...(parent.turnRef ? { parent_turn_id: parent.turnRef } : {}),
    answers: prompts.map((prompt) => ({
      discriminator_id: prompt.discriminatorId,
      answer: normalizeContinuationAnswer(answers[prompt.discriminatorId]),
    })),
  };
  return JSON.stringify({ health_evidence_continuation: payload });
}

function readLimitations(data: HealthEvidenceCardData): DisplayItem[] {
  const statusItems: DisplayItem[] = [];
  const sufficiency = textValue(data.sufficiency)?.toLowerCase();
  if (sufficiency === 'clarify') {
    statusItems.push({ label: '仍需补充关键信息' });
  } else if (sufficiency === 'safe_fallback') {
    statusItems.push({ label: '证据不足，当前回答已安全降级' });
  }
  const verdict = textValue(data.verifier_verdict)?.toLowerCase();
  if (verdict === 'repair') {
    statusItems.push({ label: '回答已根据安全校验修正' });
  } else if (verdict === 'block') {
    statusItems.push({ label: '原回答未通过安全校验' });
  }
  if (data.truncated === true) {
    statusItems.push({ label: '本轮仅展示与问题最相关的个人数据类别' });
  }

  const explicit = [
    ...listValue(data.limitations),
    ...listValue(data.gaps),
    ...listValue(data.missing_discriminators).filter((item) => !isExplicitRedFlag(item)),
  ];
  const conflicts = listValue(data.conflicts)
    .map((value): DisplayItem | undefined => {
      const record = recordValue(value);
      const category = record ? firstText(record, ['category']) : undefined;
      if (!category) return undefined;
      const categoryLabel = CATEGORY_LABELS[category.toLowerCase()] || category;
      return { label: `${categoryLabel}存在冲突记录` };
    })
    .filter((item): item is DisplayItem => Boolean(item));
  return dedupeItems([
    ...statusItems,
    ...explicit.map(projectionItem).filter((item): item is DisplayItem => Boolean(item)),
    ...conflicts,
  ], 6);
}

function evidenceRefCount(value: unknown): number {
  if (!Array.isArray(value)) return 0;
  return value.filter((item) => (
    Boolean(textValue(item))
    || Boolean(firstText(recordValue(item) ?? {}, ['ref', 'claim_id', 'doc_id']))
  )).length;
}

function riskPresentation(riskLevel: unknown): {
  badge: string;
  color: string;
  background: string;
} {
  switch (textValue(riskLevel)?.toLowerCase()) {
    case 'emergency':
      return {
        badge: '紧急',
        color: revaSemantic.risk.fg,
        background: revaSemantic.risk.bg,
      };
    case 'high':
      return {
        badge: '高风险',
        color: revaSemantic.risk.fg,
        background: revaSemantic.risk.bg,
      };
    case 'medium':
      return {
        badge: '需留意',
        color: revaSemantic.caution.fg,
        background: revaSemantic.caution.bg,
      };
    case 'low':
      return {
        badge: '低风险',
        color: revaSemantic.info.fg,
        background: revaSemantic.info.bg,
      };
    default:
      return {
        badge: '证据',
        color: revaSemantic.info.fg,
        background: C.surface,
      };
  }
}

function SectionTitle({
  icon,
  color,
  children,
}: {
  icon: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.sectionTitle}>
      <Ionicons name={icon as any} size={12} color={color} />
      <Text maxFontSizeMultiplier={1.3} style={[styles.sectionTitleText, { color }]}>
        {children}
      </Text>
    </View>
  );
}

function EvidenceItems({
  items,
  icon,
  color,
}: {
  items: DisplayItem[];
  icon: string;
  color: string;
}) {
  return (
    <View style={styles.items}>
      {items.map((item, index) => (
        <View key={`${item.label}-${item.meta ?? ''}-${index}`} style={styles.item}>
          <Ionicons name={icon as any} size={12} color={color} />
          <View style={styles.itemText}>
            <Text maxFontSizeMultiplier={1.3} style={styles.itemLabel}>
              {item.label}
            </Text>
            {item.meta ? (
              <Text maxFontSizeMultiplier={1.3} style={styles.itemMeta}>
                {item.meta}
              </Text>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

export function HealthEvidenceCardView({
  data,
  onSendSuggestedPrompt,
  healthEvidenceParent,
}: {
  data: HealthEvidenceCardData;
  onSendSuggestedPrompt?: (prompt: string, extraContext?: string) => void;
  healthEvidenceParent?: HealthEvidenceParentReference;
}) {
  const safeData = recordValue(data) ?? {};
  const projection = safeData as HealthEvidenceCardData;
  const redFlags = readDetectedRedFlags(projection);
  const safetyPrecautions = readSafetyPrecautions(projection);
  const pendingRedFlags = readPendingRedFlags(projection);
  const followUps = readFollowUps(projection);
  const sources = readSources(projection);
  const categories = readCategories(projection);
  const limitations = readLimitations(projection);
  const authorityRefCount = evidenceRefCount(projection.authority_evidence_refs);
  const authorityProjectionDeclared = Array.isArray(projection.authority_evidence_refs);
  const risk = riskPresentation(projection.risk_level);
  const intentId = parentIntentId(projection);
  const parent = healthEvidenceParent ?? {};
  const hasParentRef = typeof parent.messageRef === 'number';
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  const [submitted, setSubmitted] = React.useState(false);
  const promptIdentity = followUps
    .map((prompt) => `${prompt.discriminatorId}:${prompt.choices.join('|')}`)
    .join('\u0000');
  React.useEffect(() => {
    setAnswers({});
    setSubmitted(false);
  }, [promptIdentity, intentId, parent.messageRef, parent.turnRef]);
  const allAnswered = followUps.length > 0 && followUps.every(
    (prompt) => Boolean(answers[prompt.discriminatorId]),
  );
  const canCollect = Boolean(
    onSendSuggestedPrompt && intentId && hasParentRef && !submitted,
  );
  const canSubmit = canCollect && allAnswered;
  const hasContent = (
    redFlags.length > 0
    || safetyPrecautions.length > 0
    || pendingRedFlags.length > 0
    || followUps.length > 0
    || sources.length > 0
    || categories.length > 0
    || limitations.length > 0
    || authorityRefCount > 0
    || authorityProjectionDeclared
  );

  return (
    <CardShell
      icon="shield-checkmark-outline"
      iconColor={risk.color}
      title="本轮健康依据"
      badge={risk.badge}
      badgeColor={risk.color}
      bg={risk.background}
    >
      {redFlags.length > 0 ? (
        <View style={[styles.section, styles.redFlagSection]}>
          <SectionTitle icon="warning-outline" color={revaSemantic.risk.fg}>
            红旗提示 · 优先处理
          </SectionTitle>
          <EvidenceItems
            items={redFlags}
            icon="alert-circle-outline"
            color={revaSemantic.risk.fg}
          />
        </View>
      ) : null}

      {safetyPrecautions.length > 0 ? (
        <View style={[styles.section, styles.pendingFlagSection]}>
          <SectionTitle icon="shield-outline" color={revaSemantic.caution.fg}>
            安全边界 · 出现即就医
          </SectionTitle>
          <EvidenceItems
            items={safetyPrecautions}
            icon="information-circle-outline"
            color={revaSemantic.caution.fg}
          />
        </View>
      ) : null}

      {pendingRedFlags.length > 0 ? (
        <View style={[styles.section, styles.pendingFlagSection]}>
          <SectionTitle icon="help-buoy-outline" color={revaSemantic.caution.fg}>
            待排除的警示征象
          </SectionTitle>
          <EvidenceItems
            items={pendingRedFlags}
            icon="help-circle-outline"
            color={revaSemantic.caution.fg}
          />
        </View>
      ) : null}

      {followUps.length > 0 ? (
        <View style={styles.section}>
          <SectionTitle icon="chatbubble-ellipses-outline" color={C.green500}>
            免输入追问
          </SectionTitle>
          <View style={styles.followUps}>
            {followUps.map((followUp) => (
              <View key={followUp.question} style={styles.followUp}>
                <Text maxFontSizeMultiplier={1.3} style={styles.followUpQuestion}>
                  {followUp.question}
                </Text>
                <View style={styles.choiceRow}>
                  {followUp.choices.map((choice) => {
                    const accessibilityLabel = `${followUp.question}：${choice}`;
                    const selected = answers[followUp.discriminatorId] === choice;
                    return (
                      <Pressable
                        key={choice}
                        accessibilityRole="button"
                        accessibilityLabel={accessibilityLabel}
                        accessibilityState={{ disabled: !canCollect, selected }}
                        disabled={!canCollect}
                        onPress={() => {
                          setAnswers((current) => ({
                            ...current,
                            [followUp.discriminatorId]: choice,
                          }));
                        }}
                        style={({ pressed }) => [
                          styles.choiceButton,
                          selected && styles.choiceButtonSelected,
                          !canCollect && styles.choiceButtonDisabled,
                          pressed && canCollect && styles.choiceButtonPressed,
                        ]}
                      >
                        <Text maxFontSizeMultiplier={1.3} style={styles.choiceText}>
                          {choice}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            ))}
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="提交本轮追问回答"
              accessibilityState={{ disabled: !canSubmit }}
              disabled={!canSubmit}
              onPress={() => {
                if (!canSubmit || !intentId || !onSendSuggestedPrompt) return;
                const summary = `我已完成本轮 ${followUps.length} 项安全追问，请根据结构化回答继续分析。`;
                onSendSuggestedPrompt(
                  summary,
                  continuationContext(followUps, answers, intentId, parent),
                );
                setSubmitted(true);
              }}
              style={({ pressed }) => [
                styles.submitButton,
                !canSubmit && styles.submitButtonDisabled,
                pressed && canSubmit && styles.choiceButtonPressed,
              ]}
            >
              <Text maxFontSizeMultiplier={1.3} style={styles.submitButtonText}>
                {submitted ? '已提交' : '提交以上回答'}
              </Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {sources.length > 0 || authorityRefCount > 0 || authorityProjectionDeclared ? (
        <View style={styles.section}>
          <SectionTitle icon="library-outline" color={C.blue500}>
            权威来源
          </SectionTitle>
          {sources.length > 0 ? (
            <EvidenceItems
              items={sources}
              icon="document-text-outline"
              color={C.blue500}
            />
          ) : authorityRefCount > 0 ? (
            <Text maxFontSizeMultiplier={1.3} style={styles.fallbackText}>
              系统已使用 {authorityRefCount} 条审定证据，来源详情暂不可用
            </Text>
          ) : (
            <Text maxFontSizeMultiplier={1.3} style={styles.fallbackText}>
              本轮没有可用的审定权威证据
            </Text>
          )}
        </View>
      ) : null}

      {categories.length > 0 ? (
        <View style={styles.section}>
          <SectionTitle icon="person-circle-outline" color={C.green500}>
            已用个人数据
          </SectionTitle>
          <View style={styles.chips}>
            {categories.map((item, index) => (
              <View key={`${item.label}-${index}`} style={styles.chip}>
                <Text maxFontSizeMultiplier={1.3} style={styles.chipText}>
                  {item.label}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {limitations.length > 0 ? (
        <View style={styles.section}>
          <SectionTitle icon="help-circle-outline" color={revaSemantic.caution.fg}>
            限制与待确认
          </SectionTitle>
          <EvidenceItems
            items={limitations}
            icon="ellipse-outline"
            color={revaSemantic.caution.fg}
          />
        </View>
      ) : null}

      {!hasContent ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.emptyText}>
          本轮暂无可展示的结构化证据详情
        </Text>
      ) : null}
    </CardShell>
  );
}

export const HealthEvidenceCardSpec: CardSpec<HealthEvidenceCardData> = {
  type: 'health_evidence',
  label: '健康证据与限制',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data, options) => (
    <HealthEvidenceCardView
      data={data}
      onSendSuggestedPrompt={options?.onSendSuggestedPrompt}
      healthEvidenceParent={options?.healthEvidenceParent}
    />
  ),
};

const styles = StyleSheet.create({
  section: {
    marginTop: 10,
    gap: 7,
  },
  redFlagSection: {
    marginTop: 0,
    padding: 9,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.risk.line,
    backgroundColor: C.surface,
  },
  pendingFlagSection: {
    marginTop: 0,
    padding: 9,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: C.surface,
  },
  sectionTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  sectionTitleText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
  } as TextStyle,
  items: {
    gap: 6,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  itemText: {
    flex: 1,
    gap: 1,
  },
  itemLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink1,
  } as TextStyle,
  itemMeta: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    lineHeight: 14,
    color: C.ink3,
  } as TextStyle,
  fallbackText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    lineHeight: 15,
    color: C.ink3,
  } as TextStyle,
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  followUps: {
    gap: 9,
  },
  followUp: {
    gap: 7,
    padding: 9,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.surface,
  },
  followUpQuestion: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 16,
    color: C.ink1,
  } as TextStyle,
  choiceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  choiceButton: {
    minHeight: 44,
    minWidth: 56,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green300,
    backgroundColor: C.green50,
  },
  choiceButtonPressed: {
    opacity: 0.78,
  },
  choiceButtonSelected: {
    borderColor: C.green700,
    backgroundColor: C.green100,
  },
  choiceButtonDisabled: {
    borderColor: C.line,
    backgroundColor: C.paper2,
    opacity: 0.7,
  },
  choiceText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.green700,
  } as TextStyle,
  submitButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green500,
  },
  submitButtonDisabled: {
    backgroundColor: C.paper2,
  },
  submitButtonText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.surface,
  } as TextStyle,
  chip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    backgroundColor: C.surface,
  },
  chipText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.green700,
  } as TextStyle,
  emptyText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
  } as TextStyle,
});
