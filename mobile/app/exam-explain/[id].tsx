/**
 * /exam-explain/[id] —— 体检异常解释包 (review #2, 2026-05-12).
 *
 * 命中"用户痛点是体检异常,不是基因好奇" — 把单次 exam 的所有异常项 + 基因
 * 关联 + 趋势 + LLM actions + 复查建议聚合一页.
 */

import React from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import { fetchExamExplain, type ExamExplain, type ExplainAction } from '@/services/examExplain';
import { spacing, radii } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';
import MarkdownText from '@/components/shared/MarkdownText';

const EVIDENCE_CONF: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: '#D1FAE5', text: '#065F46', label: '强证据' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '中等证据' },
  low: { bg: '#F1F5F9', text: '#475569', label: '弱证据' },
  medical_grade: { bg: '#FEE2E2', text: '#991B1B', label: '需医生介入' },
};

const CATEGORY_CONF: Record<string, { icon: keyof typeof Ionicons.glyphMap; label: string; color: string }> = {
  diet: { icon: 'restaurant-outline', label: '饮食', color: '#FF6723' },
  supplement: { icon: 'medkit-outline', label: '补剂', color: '#BF5AF2' },
  follow_up: { icon: 'flask-outline', label: '复查', color: '#0A8F8F' },
  lifestyle: { icon: 'leaf-outline', label: '生活方式', color: '#30D158' },
  see_doctor: { icon: 'people-outline', label: '看医生', color: '#FF453A' },
};

const ABNORMAL_BG: Record<string, string> = {
  high: '#FEE2E2',
  low: '#DBEAFE',
  abnormal: '#FEF3C7',
};
const ABNORMAL_TEXT: Record<string, string> = {
  high: '#991B1B',
  low: '#1E40AF',
  abnormal: '#92400E',
};

export default function ExamExplainScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const examId = Number(id);
  const router = useRouter();
  const { c } = useTheme();

  const { data, isLoading, error } = useQuery<ExamExplain>({
    queryKey: ['exam-explain', examId],
    queryFn: () => fetchExamExplain(examId),
    enabled: Number.isFinite(examId),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.bgPrimary }]}>
        <ActivityIndicator color={c.brand} />
        <Text style={{ color: c.labelTertiary, marginTop: 8, fontSize: 12 }}>解读中…</Text>
      </SafeAreaView>
    );
  }
  if (error || !data) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.bgPrimary }]}>
        <Ionicons name="warning-outline" size={32} color={c.amber} />
        <Text style={{ color: c.labelPrimary, fontSize: 16, marginTop: 8 }}>加载失败</Text>
        <Text style={{ color: c.labelTertiary, fontSize: 12, marginTop: 4 }}>
          {String(error ?? '体检不存在')}
        </Text>
      </SafeAreaView>
    );
  }

  const expl = data.explanation;
  const needDoctor = !!(expl?.see_doctor_specialty);

  return (
    <>
      <Stack.Screen options={{ title: 'AI 体检解读', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView contentContainerStyle={styles.scroll}>
          {/* Hero */}
          <View style={[styles.hero, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <View style={styles.heroChips}>
              <View style={[styles.chip, { backgroundColor: c.tintBlue }]}>
                <Text style={[styles.chipText, { color: c.blue }]}>
                  {data.exam.exam_type || '综合体检'}
                </Text>
              </View>
              <View style={[styles.chip, { backgroundColor: c.bgPrimary, borderColor: c.separator, borderWidth: 1 }]}>
                <Text style={[styles.chipText, { color: c.labelTertiary }]}>{data.exam.exam_date}</Text>
              </View>
            </View>
            <Text style={[styles.heroTitle, { color: c.labelPrimary }]}>
              {data.abnormal_items.length} 项异常
              {data.user_gene_hits.length > 0 && (
                <Text style={[styles.heroSub, { color: c.labelTertiary }]}>
                  {' '}· 已结合 {data.user_gene_hits.length} 个基因
                </Text>
              )}
            </Text>
          </View>

          {/* Summary */}
          {expl?.summary && (
            <View style={[styles.card, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
              <View style={styles.cardHead}>
                <Ionicons name="sparkles" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.brand }]}>AI 解读</Text>
              </View>
              <MarkdownText>{expl.summary}</MarkdownText>
              {needDoctor && (
                <View style={[styles.docBanner, { backgroundColor: '#FEE2E2', borderColor: '#991B1B' }]}>
                  <Ionicons name="medkit" size={14} color="#991B1B" />
                  <Text style={[styles.docBannerText, { color: '#991B1B' }]}>
                    建议看{expl.see_doctor_specialty}
                  </Text>
                </View>
              )}
            </View>
          )}

          {/* Abnormal items */}
          {data.abnormal_items.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="alert-circle-outline" size={14} color={c.amber} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>异常项</Text>
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  {data.abnormal_items.length}
                </Text>
              </View>
              {data.abnormal_items.map((it, i) => {
                const lvl = (it.is_abnormal || 'abnormal').toLowerCase();
                return (
                  <View key={`${it.item_name}-${i}`} style={[styles.itemRow, { borderTopColor: c.separator }]}>
                    <View style={{ flex: 1 }}>
                      <Text style={[styles.itemName, { color: c.labelPrimary }]}>{it.item_name}</Text>
                      <Text style={[styles.itemMeta, { color: c.labelTertiary }]}>
                        {it.value ?? it.value_text ?? '—'}
                        {it.unit ? ` ${it.unit}` : ''}
                        {it.reference_range ? ` · 参考 ${it.reference_range}` : ''}
                      </Text>
                      {it.gene_links.length > 0 && (
                        <View style={styles.geneLinkRow}>
                          {it.gene_links.map(g => (
                            <View key={g} style={[styles.geneChip, { backgroundColor: c.tintTeal }]}>
                              <Text style={[styles.geneChipText, { color: c.teal }]}>🧬 {g}</Text>
                            </View>
                          ))}
                        </View>
                      )}
                    </View>
                    <View style={[styles.abnormalBadge, { backgroundColor: ABNORMAL_BG[lvl] || c.tintAmber }]}>
                      <Text style={[styles.abnormalBadgeText, { color: ABNORMAL_TEXT[lvl] || c.amber }]}>
                        {lvl === 'high' ? '↑ 偏高' : lvl === 'low' ? '↓ 偏低' : '异常'}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* Actions */}
          {expl && expl.actions.length > 0 && (
            <View style={styles.section}>
              <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>建议行动</Text>
              {expl.actions.map((a, i) => (
                <ActionCard key={i} action={a} c={c} />
              ))}
            </View>
          )}

          {/* Trends preview */}
          {Object.keys(data.trends).length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="trending-up" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>历史趋势</Text>
              </View>
              {Object.entries(data.trends).slice(0, 5).map(([name, points]) => (
                <View key={name} style={[styles.trendRow, { borderTopColor: c.separator }]}>
                  <Text style={[styles.trendName, { color: c.labelPrimary }]} numberOfLines={1}>{name}</Text>
                  <Text style={[styles.trendData, { color: c.labelSecondary }]}>
                    {points.slice(-4).map(p => `${p.date.slice(5)} ${p.value ?? p.value_text ?? '—'}`).join(' → ')}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* Related cards */}
          {data.related_cards.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="link-outline" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>已生成的行动卡</Text>
              </View>
              {data.related_cards.map(rc => (
                <TouchableOpacity
                  key={rc.id}
                  style={[styles.relatedCard, { backgroundColor: c.bgPrimary }]}
                  onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(rc.id) } })}
                >
                  <Text style={[styles.relatedTitle, { color: c.labelPrimary }]} numberOfLines={2}>{rc.title}</Text>
                  <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* Recheck reminder */}
          {expl && expl.recheck_window_days > 0 && (
            <View style={[styles.recheckCard, { backgroundColor: c.tintBlue }]}>
              <Ionicons name="calendar-outline" size={16} color={c.blue} />
              <Text style={[styles.recheckText, { color: c.blue }]}>
                建议 {expl.recheck_window_days} 天后复查
              </Text>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function ActionCard({ action, c }: { action: ExplainAction; c: any }) {
  const cat = CATEGORY_CONF[action.category] ?? CATEGORY_CONF.lifestyle;
  const ev = EVIDENCE_CONF[action.evidence_level] ?? EVIDENCE_CONF.medium;
  return (
    <View style={[styles.actionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.actionHead}>
        <View style={[styles.catDot, { backgroundColor: cat.color + '22' }]}>
          <Ionicons name={cat.icon} size={14} color={cat.color} />
        </View>
        <Text style={[styles.actionCat, { color: cat.color }]}>{cat.label}</Text>
        <View style={[styles.evidenceChip, { backgroundColor: ev.bg }]}>
          <Text style={[styles.evidenceChipText, { color: ev.text }]}>{ev.label}</Text>
        </View>
      </View>
      <Text style={[styles.actionTitle, { color: c.labelPrimary }]}>{action.title}</Text>
      {!!action.rationale && (
        <Text style={[styles.actionRationale, { color: c.labelSecondary }]}>{action.rationale}</Text>
      )}
      {(action.metric_key || action.suggested_days) && (
        <Text style={[styles.actionMeta, { color: c.labelTertiary }]}>
          {action.metric_key ? `跟踪 ${action.metric_key}` : ''}
          {action.metric_key && action.suggested_days ? ' · ' : ''}
          {action.suggested_days ? `${action.suggested_days} 天` : ''}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  hero: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radii.lg, padding: spacing.md, gap: 8 },
  heroChips: { flexDirection: 'row', gap: 6 },
  chip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  chipText: { fontSize: 11, fontWeight: '600' },
  heroTitle: { fontSize: 20, fontWeight: '700' },
  heroSub: { fontSize: 13, fontWeight: '400' },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radii.lg, padding: spacing.md, gap: 6 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardTitle: { fontSize: 14, fontWeight: '600', flex: 1 },
  cardMeta: { fontSize: 12, fontWeight: '500' },
  docBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 6, marginTop: 6,
  },
  docBannerText: { fontSize: 13, fontWeight: '600', flex: 1 },
  itemRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth,
  },
  itemName: { fontSize: 14, fontWeight: '600' },
  itemMeta: { fontSize: 11, marginTop: 2, fontFamily: 'Courier' },
  geneLinkRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 4 },
  geneChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  geneChipText: { fontSize: 10, fontWeight: '600' },
  abnormalBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  abnormalBadgeText: { fontSize: 11, fontWeight: '700' },
  section: { gap: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  actionCard: {
    borderWidth: StyleSheet.hairlineWidth, borderRadius: radii.md, padding: spacing.md, gap: 4,
  },
  actionHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  catDot: { width: 22, height: 22, borderRadius: 6, alignItems: 'center', justifyContent: 'center' },
  actionCat: { fontSize: 12, fontWeight: '600', flex: 1 },
  evidenceChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  evidenceChipText: { fontSize: 10, fontWeight: '600' },
  actionTitle: { fontSize: 14, fontWeight: '600', marginTop: 4 },
  actionRationale: { fontSize: 12, lineHeight: 18 },
  actionMeta: { fontSize: 11, marginTop: 2 },
  trendRow: { paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, gap: 2 },
  trendName: { fontSize: 13, fontWeight: '500' },
  trendData: { fontSize: 11, fontFamily: 'Courier' },
  relatedCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: 8, padding: 10, marginTop: 4,
  },
  relatedTitle: { fontSize: 13, fontWeight: '500', flex: 1 },
  recheckCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: radii.md, padding: spacing.md,
  },
  recheckText: { fontSize: 13, fontWeight: '600', flex: 1 },
});
