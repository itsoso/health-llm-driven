import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { StatusBar } from 'expo-status-bar';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  buildDailyArtifactBasisChatRoute,
  createDailyArtifactChatContext,
  parseDailyArtifactDetailPayload,
} from '../../utils/dailyArtifactNavigation';
import { getDailyArtifactDetail } from '../../services/dailyArtifact';
import { stateVariableLabel } from '../../services/trajectoryDisplay';
import { formatHealthActionTitle } from '../../utils/actionCopy';
import {
  revaColors as C,
  revaRadii,
  revaShadows,
} from '../../constants/revaTheme';
import type { AgentContextPayload } from '../../utils/agentContext';

type DetailEvidence = {
  kind?: string | null;
  label?: string | null;
  summary?: string | null;
  source?: string | null;
  confidence?: string | number | null;
};

export default function DailyArtifactDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ artifact?: string; date?: string; actionId?: string }>();
  const routePayload = useMemo(() => parseDailyArtifactDetailPayload(params.artifact), [params.artifact]);
  const [recoveredPayload, setRecoveredPayload] = useState<AgentContextPayload | null>(null);
  const [recovering, setRecovering] = useState(false);
  const payload = routePayload ?? recoveredPayload;

  useEffect(() => {
    if (routePayload) return;
    const date = stringParam(params.date);
    if (!date) return;
    let cancelled = false;
    setRecovering(true);
    getDailyArtifactDetail({ date, actionId: stringParam(params.actionId) })
      .then((artifact) => {
        if (cancelled) return;
        setRecoveredPayload(artifact ? createDailyArtifactChatContext(artifact, 'explain_basis') : null);
      })
      .catch(() => {
        if (!cancelled) setRecoveredPayload(null);
      })
      .finally(() => {
        if (!cancelled) setRecovering(false);
      });
    return () => {
      cancelled = true;
    };
  }, [params.actionId, params.date, routePayload]);

  if (!payload) {
    if (recovering) {
      return (
        <SafeAreaView style={styles.safe} edges={['top']}>
          <StatusBar style="dark" />
          <View style={styles.empty}>
            <ActivityIndicator color={C.green600} />
            <Text style={styles.emptyTitle}>今日行动解读</Text>
            <Text style={styles.emptyText}>正在恢复这条行动的决策依据。</Text>
          </View>
        </SafeAreaView>
      );
    }
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <StatusBar style="dark" />
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>今日行动解读</Text>
          <Text style={styles.emptyText}>这条行动的上下文已过期,回到今日后可以重新生成。</Text>
          <Pressable
            style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}
            onPress={() => router.push('/' as never)}
            accessibilityRole="button"
            accessibilityLabel="回到今日"
          >
            <Text style={styles.primaryButtonText}>回到今日</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const action = objectValue(payload.top_action);
  const state = objectValue(payload.state);
  const evidence = arrayValue(payload.evidence)
    .map(item => objectValue(item) as DetailEvidence | null)
    .filter((item): item is DetailEvidence => Boolean(item?.summary));
  const rawTitle = stringValue(action?.title) || stringValue(state?.summary) || '今天这条行动';
  const title = formatHealthActionTitle(rawTitle);
  const whyNow = stringValue(action?.why_now);
  const doNow = stringValue(action?.do_now);
  const confidence = stringValue(action?.confidence) || stringValue(payload.confidence);
  const priority = stringValue(action?.priority_tier);
  const verificationSignals = uniqueValues([
    metricLabel(stringValue(action?.verification_signal)),
    metricLabel(stringValue(action?.target_state_variable)),
  ]);
  const safetyBoundary = stringValue(payload.safety_boundary);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.nav}>
          <Pressable
            style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
            onPress={() => router.back()}
            accessibilityRole="button"
            accessibilityLabel="返回"
          >
            <Ionicons name="chevron-back" size={22} color={C.ink1} />
          </Pressable>
          <View style={styles.navTitleBlock}>
            <Text style={styles.navEyebrow}>小巴生成</Text>
            <Text style={styles.navTitle}>今日行动解读</Text>
          </View>
        </View>

        <View style={styles.hero}>
          <View style={styles.heroMeta}>
            <Text style={styles.heroKicker}>{stringValue(state?.label) || '今日最重要行动'}</Text>
            <View style={styles.metaPills}>
              {priority ? <MetaPill label={priority} /> : null}
              {confidence ? <MetaPill label={confidenceLabel(confidence)} /> : null}
            </View>
          </View>
          <Text style={styles.title}>{title}</Text>
          {stringValue(state?.summary) ? (
            <Text style={styles.summary}>{stringValue(state?.summary)}</Text>
          ) : null}
        </View>

        <Section title="为什么现在" icon="sparkles-outline">
          <Text style={styles.bodyText}>{whyNow || '小巴还没有给出足够明确的触发原因。'}</Text>
        </Section>

        <Section title="现在怎么做" icon="play-circle-outline">
          <Text style={styles.bodyText}>{doNow || '先和小巴确认执行步骤,避免把建议误当作已确认计划。'}</Text>
        </Section>

        <Section title="依据来自哪里" icon="git-branch-outline">
          {evidence.length > 0 ? (
            <View style={styles.evidenceList}>
              {evidence.map((item, index) => (
                <View key={`${item.kind ?? item.label ?? 'evidence'}-${index}`} style={styles.evidenceRow}>
                  <View style={styles.evidenceDot} />
                  <View style={styles.evidenceCopy}>
                    <Text style={styles.evidenceLabel}>{evidenceLabel(item.label)}</Text>
                    <Text style={styles.evidenceSummary}>{item.summary}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <Text style={styles.bodyText}>这次生成没有附带可展示依据,建议先追问小巴。</Text>
          )}
        </Section>

        <Section title="后续验证" icon="checkmark-done-outline">
          {verificationSignals.length > 0 ? (
            <View style={styles.signalRow}>
              {verificationSignals.map(signal => <SignalPill key={signal} label={signal} />)}
            </View>
          ) : (
            <Text style={styles.bodyText}>暂无明确验证指标。</Text>
          )}
          <Text style={styles.hintText}>执行后用这些信号回看,避免只凭感觉判断是否有效。</Text>
        </Section>

        {safetyBoundary ? (
          <View style={styles.boundary}>
            <Ionicons name="shield-checkmark-outline" size={18} color={C.green600} />
            <Text style={styles.boundaryText}>{safetyBoundary}</Text>
          </View>
        ) : null}

        <Pressable
          style={({ pressed }) => [styles.chatButton, pressed && styles.pressed]}
          onPress={() => router.push(buildDailyArtifactBasisChatRoute(payload as AgentContextPayload) as never)}
          accessibilityRole="button"
          accessibilityLabel="继续和小巴讨论今日行动"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={18} color={C.greenOn} />
          <Text style={styles.chatButtonText}>继续问小巴</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <Ionicons name={icon} size={16} color={C.green600} />
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function MetaPill({ label }: { label: string }) {
  return (
    <View style={styles.metaPill}>
      <Text style={styles.metaPillText}>{label}</Text>
    </View>
  );
}

function SignalPill({ label }: { label: string }) {
  return (
    <View style={styles.signalPill}>
      <Text style={styles.signalText}>{label}</Text>
    </View>
  );
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function stringParam(value: unknown): string | null {
  const raw = Array.isArray(value) ? value[0] : value;
  return typeof raw === 'string' && raw.trim() ? raw.trim() : null;
}

function uniqueValues(values: (string | null)[]): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

function confidenceLabel(value: string): string {
  switch (value) {
    case 'high': return '高可信';
    case 'medium': return '中可信';
    case 'low': return '待补数';
    default: return value;
  }
}

function evidenceLabel(value?: string | null): string {
  switch ((value || '').toLowerCase()) {
    case 'why now': return '触发证据';
    case 'verification': return '验证方式';
    case 'trajectory': return '轨迹信号';
    default: return value || '依据';
  }
}

// 单一真相源:services/trajectoryDisplay.ts 的 stateVariableLabel(缺映射原样返回)。
function metricLabel(value: string | null): string | null {
  return stateVariableLabel(value);
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  content: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 34,
    gap: 14,
  },
  nav: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  navTitleBlock: { flex: 1 },
  navEyebrow: { fontSize: 11, fontWeight: '800', color: C.green600 },
  navTitle: { marginTop: 2, fontSize: 20, fontWeight: '900', color: C.ink1 },
  hero: {
    borderRadius: revaRadii.xl,
    backgroundColor: C.focusBg,
    padding: 18,
    gap: 10,
    ...revaShadows.focus,
  },
  heroMeta: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  heroKicker: { flex: 1, fontSize: 12, fontWeight: '900', color: C.green100 },
  metaPills: { flexDirection: 'row', gap: 6 },
  metaPill: {
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4,
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  metaPillText: { fontSize: 11, fontWeight: '800', color: C.green50 },
  title: { fontSize: 24, lineHeight: 31, fontWeight: '900', color: C.greenOn },
  summary: { fontSize: 14, lineHeight: 21, color: C.green50 },
  section: {
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 16,
    gap: 10,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  sectionTitle: { fontSize: 15, fontWeight: '900', color: C.ink1 },
  bodyText: { fontSize: 14, lineHeight: 22, color: C.ink1 },
  evidenceList: { gap: 10 },
  evidenceRow: { flexDirection: 'row', gap: 9 },
  evidenceDot: {
    marginTop: 7,
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: C.green500,
  },
  evidenceCopy: { flex: 1, minWidth: 0 },
  evidenceLabel: { fontSize: 12, fontWeight: '900', color: C.ink1 },
  evidenceSummary: { marginTop: 2, fontSize: 13, lineHeight: 19, color: C.ink2 },
  signalRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  signalPill: {
    borderRadius: 999,
    paddingHorizontal: 11,
    paddingVertical: 7,
    backgroundColor: C.green50,
    borderWidth: 1,
    borderColor: C.green100,
  },
  signalText: { fontSize: 13, fontWeight: '900', color: C.green700 },
  hintText: { fontSize: 12, lineHeight: 18, color: C.ink3 },
  boundary: {
    flexDirection: 'row',
    gap: 9,
    alignItems: 'flex-start',
    borderRadius: revaRadii.lg,
    backgroundColor: C.green50,
    borderWidth: 1,
    borderColor: C.green100,
    padding: 14,
  },
  boundaryText: { flex: 1, fontSize: 12.5, lineHeight: 18, color: C.ink2 },
  chatButton: {
    height: 52,
    borderRadius: 26,
    backgroundColor: C.green600,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  chatButtonText: { fontSize: 16, fontWeight: '900', color: C.greenOn },
  empty: {
    flex: 1,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 14,
  },
  emptyTitle: { fontSize: 22, fontWeight: '900', color: C.ink1 },
  emptyText: { textAlign: 'center', fontSize: 14, lineHeight: 21, color: C.ink2 },
  primaryButton: {
    height: 48,
    borderRadius: 24,
    backgroundColor: C.green600,
    paddingHorizontal: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonText: { fontSize: 15, fontWeight: '900', color: C.greenOn },
  pressed: { opacity: 0.82 },
});
