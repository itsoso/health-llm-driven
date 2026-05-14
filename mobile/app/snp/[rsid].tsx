/**
 * /snp/[rsid] —— 单 SNP 详情页 (G-W4, 2026-05-12).
 *
 * 后端 GET /genetic/snp/{rsid}:
 *   静态信息 + 基因型释义 + 用户命中 + LLM 个性化 actions (5 类)
 *   + 关联 cards + 同 cluster siblings.
 * actions 可能为 null (LLM 失败) — fallback 仅展示静态信息.
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
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import {
  fetchSnpDetail,
  type SnpDetail,
  CATEGORY_LABELS,
  RISK_COLORS,
} from '@/services/geneticReport';
import { spacing, radii } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';
import { pushChatWithContext } from '@/utils/agentContext';

const ACTION_SECTIONS: Array<{
  key: keyof Pick<
    NonNullable<SnpDetail['actions']>,
    'nutrition_actions' | 'supplement_actions' | 'exercise_actions' | 'lab_to_check' | 'drug_caution'
  >;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  emptyHint: string;
}> = [
  { key: 'nutrition_actions', icon: 'restaurant-outline', title: '饮食', emptyHint: '这条 SNP 没有特别饮食建议' },
  { key: 'supplement_actions', icon: 'medkit-outline', title: '补剂', emptyHint: '不需要额外补剂' },
  { key: 'exercise_actions', icon: 'fitness-outline', title: '运动', emptyHint: '运动方面不影响' },
  { key: 'lab_to_check', icon: 'flask-outline', title: '建议复查', emptyHint: '暂无建议复查项' },
  { key: 'drug_caution', icon: 'warning-outline', title: '药物注意', emptyHint: '无药物相关注意' },
];

export default function SnpDetailScreen() {
  const { rsid } = useLocalSearchParams<{ rsid: string }>();
  const router = useRouter();
  const { c } = useTheme();

  const { data, isLoading, error } = useQuery<SnpDetail>({
    queryKey: ['snp-detail', rsid],
    queryFn: () => fetchSnpDetail(String(rsid)),
    enabled: Boolean(rsid),
    staleTime: 10 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
        <Text style={[styles.loadingText, { color: c.labelTertiary }]}>解读 {rsid}…</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <View style={styles.center}>
        <Ionicons name="warning-outline" size={32} color={c.amber} />
        <Text style={[styles.errorText, { color: c.labelPrimary }]}>SNP 详情加载失败</Text>
        <Text style={[styles.errorSub, { color: c.labelTertiary }]}>{String(error ?? '未知 SNP')}</Text>
      </View>
    );
  }

  const userRisk = data.user.risk_level ? RISK_COLORS[data.user.risk_level] : null;
  const headerTitle = data.gene;

  return (
    <>
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top', 'bottom']}>
        {/* 自定义返回按钮 — _layout 全局 headerShown:false, 不靠 Stack header */}
        <View style={styles.topBar}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
            <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
            <Text style={[styles.backText, { color: c.labelPrimary }]}>返回</Text>
          </TouchableOpacity>
          <Text style={[styles.topTitle, { color: c.labelPrimary }]} numberOfLines={1}>{headerTitle}</Text>
          <View style={{ width: 60 }} />
        </View>
        <ScrollView contentContainerStyle={styles.content}>
          {/* Header card: gene · variant · category */}
          <View style={[styles.headerCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <View style={styles.headerTopRow}>
              <Text style={styles.headerEmoji}>🧬</Text>
              <View style={{ flex: 1 }}>
                <Text style={[styles.headerGene, { color: c.labelPrimary }]}>
                  {data.gene}
                  <Text style={[styles.headerVariant, { color: c.labelTertiary }]}> · {data.variant_name}</Text>
                </Text>
                <Text style={[styles.headerMeta, { color: c.labelTertiary }]}>
                  {data.rsid} · {CATEGORY_LABELS[data.category] ?? data.category}
                </Text>
              </View>
              {userRisk && (
                <View style={[styles.riskBadge, { backgroundColor: userRisk.bg }]}>
                  <Text style={[styles.riskText, { color: userRisk.text }]}>{userRisk.label}</Text>
                </View>
              )}
            </View>
            <Text style={[styles.headerDesc, { color: c.labelSecondary }]}>{data.description}</Text>
          </View>

          {/* User hit block */}
          <View style={[styles.userCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <Text style={[styles.sectionTitle, { color: c.labelTertiary }]}>你的实测</Text>
            {data.user.hit ? (
              <Text style={[styles.userResult, { color: c.labelPrimary }]}>
                基因型 <Text style={styles.mono}>{data.user.genotype}</Text>
                {data.user.result_label ? ` · ${data.user.result_label}` : ''}
              </Text>
            ) : (
              <Text style={[styles.userResult, { color: c.labelTertiary }]}>
                你的报告中没有这条位点 — 下方建议为通用静态信息
              </Text>
            )}
          </View>

          {/* Genotype meanings */}
          {data.genotype_meanings.length > 0 && (
            <View style={[styles.userCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.sectionTitle, { color: c.labelTertiary }]}>基因型释义</Text>
              {data.genotype_meanings.map(g => {
                const isYou = data.user.genotype === g.genotype;
                const gRisk = RISK_COLORS[g.risk] ?? RISK_COLORS.info;
                return (
                  <View
                    key={g.genotype}
                    style={[
                      styles.genotypeRow,
                      { borderColor: c.separator },
                      isYou && { backgroundColor: c.brandLight, borderColor: c.brand },
                    ]}
                  >
                    <Text style={[styles.mono, styles.genotypeKey, { color: c.labelPrimary }]}>
                      {g.display}
                    </Text>
                    <Text style={[styles.genotypeLabel, { color: c.labelSecondary }]}>{g.label}</Text>
                    <View style={[styles.riskMini, { backgroundColor: gRisk.bg }]}>
                      <Text style={[styles.riskMiniText, { color: gRisk.text }]}>{gRisk.label}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* LLM actions */}
          {data.actions ? (
            <>
              <View style={[styles.headlineCard, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
                <View style={styles.agentHead}>
                  <Ionicons name="sparkles" size={16} color={c.brand} />
                  <Text style={[styles.agentTitle, { color: c.brand }]}>对你的解读</Text>
                  {data.actions.confidence && (
                    <Text style={[styles.confidence, { color: c.labelTertiary }]}>
                      证据等级 · {data.actions.confidence}
                    </Text>
                  )}
                </View>
                <Text style={[styles.headlineText, { color: c.labelPrimary }]}>
                  {data.actions.headline}
                </Text>
              </View>

              {ACTION_SECTIONS.map(sec => {
                const list = data.actions?.[sec.key] ?? [];
                if (list.length === 0) return null;
                // 跟 Agent 详细聊本类 — 跳 chat tab 预填问题
                const chatPrompt = `针对我的 ${data.gene} 基因 (${data.user.genotype || data.variant_name}), 在${sec.title}方面, 结合我现在的化验/补剂/运动数据, 能否给我一个未来 30 天的具体执行方案?`;
                // 把用户当前正在看的方案条目结构化打包透传给 LLM, 避免重新猜
                const chatContext = {
                  from: `snp/${data.gene}`,
                  gene: data.gene,
                  genotype: data.user.genotype || data.variant_name || null,
                  section: sec.title,
                  section_key: sec.key,
                  items: list,
                  confidence: data.actions?.confidence || null,
                };
                return (
                  <View
                    key={sec.key}
                    style={[styles.actionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}
                  >
                    <View style={styles.actionHead}>
                      <Ionicons name={sec.icon} size={16} color={c.brand} />
                      <Text style={[styles.actionTitle, { color: c.labelPrimary }]}>{sec.title}</Text>
                    </View>
                    {list.map((line, idx) => (
                      <View key={`${sec.key}-${idx}`} style={styles.actionRow}>
                        <Text style={[styles.bullet, { color: c.brand }]}>·</Text>
                        <Text style={[styles.actionLine, { color: c.labelSecondary }]}>{line}</Text>
                      </View>
                    ))}
                    {/* 2026-05-14: 跟 Agent 详细聊本类 — 让"详细行动"延伸进 chat */}
                    {(sec.key === 'nutrition_actions' || sec.key === 'supplement_actions' || sec.key === 'exercise_actions') && (
                      <TouchableOpacity
                        style={[styles.agentLink, { borderTopColor: c.separator }]}
                        onPress={() => pushChatWithContext(router, {
                          prompt: chatPrompt,
                          context: chatContext,
                          badge: `${data.gene} · ${sec.title}方案 ${list.length} 条`,
                        })}
                      >
                        <Ionicons name="chatbubble-ellipses-outline" size={14} color={c.brand} />
                        <Text style={[styles.agentLinkText, { color: c.brand }]}>
                          跟 Agent 详细聊「{sec.title}」方案
                        </Text>
                        <Ionicons name="chevron-forward" size={14} color={c.brand} style={{ marginLeft: 'auto' }} />
                      </TouchableOpacity>
                    )}
                  </View>
                );
              })}
            </>
          ) : (
            <View style={[styles.fallbackCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Ionicons name="information-circle-outline" size={20} color={c.labelTertiary} />
              <Text style={[styles.fallbackText, { color: c.labelTertiary }]}>
                {data.user.hit
                  ? '个性化解读暂时不可用,稍后再来看看'
                  : '没有测到这条位点,先看上方静态描述'}
              </Text>
            </View>
          )}

          {/* Related cards */}
          {data.related_cards.length > 0 && (
            <View style={[styles.userCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.sectionTitle, { color: c.labelTertiary }]}>
                基于这条基因, 当前生效的建议
              </Text>
              {data.related_cards.map(rc => (
                <TouchableOpacity
                  key={rc.id}
                  style={[styles.relatedRow, { backgroundColor: c.bgPrimary }]}
                  onPress={() => router.push(`/card/${rc.id}` as never)}
                >
                  <Text style={[styles.relatedTitle, { color: c.labelPrimary }]} numberOfLines={2}>
                    {rc.title}
                  </Text>
                  <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
                </TouchableOpacity>
              ))}
            </View>
          )}

          {/* Siblings */}
          {data.siblings.length > 0 && (
            <View style={[styles.userCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.sectionTitle, { color: c.labelTertiary }]}>
                同类位点 ({CATEGORY_LABELS[data.category] ?? data.category})
              </Text>
              <View style={styles.siblingsRow}>
                {data.siblings.map(s => (
                  <TouchableOpacity
                    key={s.rsid}
                    style={[styles.siblingChip, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}
                    onPress={() => router.push(`/snp/${s.rsid}` as never)}
                  >
                    <Text style={[styles.siblingText, { color: c.labelSecondary }]}>{s.gene}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  topBar: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  backBtn: { flexDirection: 'row', alignItems: 'center', minWidth: 60 },
  backText: { fontSize: 16, marginLeft: -2 },
  topTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  loadingText: { fontSize: 13 },
  errorText: { fontSize: 16, fontWeight: '600' },
  errorSub: { fontSize: 12, textAlign: 'center' },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  headerCard: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 8 },
  headerTopRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerEmoji: { fontSize: 22 },
  headerGene: { fontSize: 17, fontWeight: '700' },
  headerVariant: { fontSize: 13, fontWeight: '400' },
  headerMeta: { fontSize: 11, fontFamily: 'Courier', marginTop: 2 },
  headerDesc: { fontSize: 13, lineHeight: 19 },
  riskBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  riskText: { fontSize: 11, fontWeight: '600' },
  userCard: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 8 },
  sectionTitle: { fontSize: 11, fontWeight: '600', letterSpacing: 0.4, textTransform: 'uppercase' },
  userResult: { fontSize: 14, lineHeight: 20 },
  mono: { fontFamily: 'Courier', fontWeight: '600' },
  genotypeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    borderWidth: 1, borderRadius: 8, padding: 8,
  },
  genotypeKey: { fontSize: 14, minWidth: 32 },
  genotypeLabel: { fontSize: 13, flex: 1 },
  riskMini: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  riskMiniText: { fontSize: 10, fontWeight: '600' },
  headlineCard: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 6 },
  agentHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  agentTitle: { fontSize: 13, fontWeight: '600' },
  confidence: { fontSize: 10, marginLeft: 'auto' },
  headlineText: { fontSize: 14, lineHeight: 20, fontWeight: '500' },
  actionCard: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 6 },
  actionHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  actionTitle: { fontSize: 13, fontWeight: '600' },
  actionRow: { flexDirection: 'row', gap: 8, marginVertical: 2 },
  bullet: { fontSize: 16, lineHeight: 22, fontWeight: '700' },
  actionLine: { fontSize: 14, lineHeight: 22, flex: 1 },
  agentLink: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginTop: 8, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth,
  },
  agentLinkText: { fontSize: 13, fontWeight: '500' },
  fallbackCard: {
    borderWidth: 1, borderRadius: radii.md, padding: spacing.md,
    flexDirection: 'row', alignItems: 'center', gap: 8,
  },
  fallbackText: { fontSize: 12, flex: 1 },
  relatedRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: 8, padding: 10,
  },
  relatedTitle: { fontSize: 13, fontWeight: '500', lineHeight: 18, flex: 1 },
  siblingsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  siblingChip: {
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: 14, borderWidth: 1,
  },
  siblingText: { fontSize: 12, fontWeight: '500' },
});
