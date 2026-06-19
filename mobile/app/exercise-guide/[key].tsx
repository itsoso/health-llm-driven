/**
 * /exercise-guide/[key] —— 动作图文指导 (C2, P2 · proactive-planning PRD §3.C).
 *
 * 分解步骤 + 常见错误 + 伤病红线(降级就医)+ 安全提示。hedged 教练内容,不开方不出因果。
 * injury_red_lines 是安全表面 —— 必须最醒目(红块,「出现以下情况立即停止并就医」),不埋。
 */
import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';

import { revaColors as C, revaRadii } from '../../constants/revaTheme';
import { Card, Icon, SectionLabel } from '../../components/reva/RevaKit';
import { useExerciseGuide } from '../../hooks/useFitness';

const RED = '#D5503A';
const RED_BG = '#FBE8E4';
const RED_LINE = '#F3CDC4';

export default function ExerciseGuideScreen() {
  const router = useRouter();
  const { key } = useLocalSearchParams<{ key: string }>();
  const exerciseKey = typeof key === 'string' && key.length > 0 ? key : null;

  const { data, isLoading, isError, refetch } = useExerciseGuide(exerciseKey);

  const Header = ({ title }: { title: string }) => (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={styles.back}>
        <Ionicons name="chevron-back" size={26} color={C.ink1} />
      </TouchableOpacity>
      <Text style={styles.headerTitle} numberOfLines={1}>
        {title}
      </Text>
      <View style={styles.back} />
    </View>
  );

  if (!exerciseKey) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        <Header title="动作指导" />
        <View style={styles.center}>
          <Icon name="alert-triangle" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>无效的动作</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        <Header title="动作指导" />
        <View style={styles.center}>
          <ActivityIndicator color={C.green500} />
        </View>
      </SafeAreaView>
    );
  }

  if (isError || !data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        <Header title="动作指导" />
        <View style={styles.center}>
          <Icon name="alert-triangle" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>暂时拉不到这个动作的指导</Text>
          <Text style={styles.emptySub}>请检查网络后重试</Text>
          <Pressable style={styles.retryBtn} onPress={() => refetch()}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const steps = Array.isArray(data.steps) ? data.steps : [];
  const mistakes = Array.isArray(data.common_mistakes) ? data.common_mistakes : [];
  const redLines = Array.isArray(data.injury_red_lines) ? data.injury_red_lines : [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <Header title={data.name || '动作指导'} />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>{data.name}</Text>

        {/* 分解步骤(编号) */}
        {steps.length > 0 ? (
          <>
            <SectionLabel>分解步骤</SectionLabel>
            <Card pad={0}>
              {steps.map((s, i) => (
                <View
                  key={i}
                  style={[styles.stepRow, i === steps.length - 1 && { borderBottomWidth: 0 }]}
                >
                  <View style={styles.stepNum}>
                    <Text style={styles.stepNumText}>{i + 1}</Text>
                  </View>
                  <Text style={styles.stepText}>{s}</Text>
                </View>
              ))}
            </Card>
          </>
        ) : null}

        {/* 常见错误(warning 调) */}
        {mistakes.length > 0 ? (
          <>
            <SectionLabel>常见错误</SectionLabel>
            <Card pad={14}>
              {mistakes.map((m, i) => (
                <View key={i} style={styles.bulletRow}>
                  <View style={styles.bulletDot} />
                  <Text style={styles.bulletText}>{m}</Text>
                </View>
              ))}
            </Card>
          </>
        ) : null}

        {/* 伤病红线 —— 安全表面,最醒目的红块 */}
        {redLines.length > 0 ? (
          <View style={styles.redCard}>
            <View style={styles.redHead}>
              <Ionicons name="warning" size={20} color={RED} />
              <Text style={styles.redTitle}>出现以下情况立即停止并就医</Text>
            </View>
            {redLines.map((r, i) => (
              <View key={i} style={styles.redRow}>
                <Text style={styles.redBullet}>•</Text>
                <Text style={styles.redText}>{r}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {/* 安全提示 footer(hedged) */}
        {data.safety_note ? (
          <Text style={styles.safetyNote}>{data.safety_note}</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  back: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '700', color: C.ink1 },
  content: { paddingHorizontal: 16, paddingTop: 4, paddingBottom: 32 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 8 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: C.ink1, marginTop: 4 },
  emptySub: { fontSize: 13.5, color: C.ink3, textAlign: 'center' },
  retryBtn: {
    marginTop: 8,
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 22,
    paddingVertical: 10,
  },
  retryText: { color: C.greenOn, fontSize: 14, fontWeight: '700' },

  title: { fontSize: 24, fontWeight: '800', letterSpacing: -0.4, color: C.ink1, marginBottom: 18 },

  stepRow: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  stepNum: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepNumText: { fontFamily: 'IBMPlexMono', fontWeight: '600', fontSize: 13, color: C.green600 },
  stepText: { flex: 1, fontSize: 15, color: C.ink1, lineHeight: 22, paddingTop: 2 },

  bulletRow: { flexDirection: 'row', gap: 9, alignItems: 'flex-start', paddingVertical: 5 },
  bulletDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#C98A1E',
    marginTop: 8,
  },
  bulletText: { flex: 1, fontSize: 14, color: C.ink2, lineHeight: 21 },

  redCard: {
    marginTop: 18,
    backgroundColor: RED_BG,
    borderWidth: 1.5,
    borderColor: RED_LINE,
    borderRadius: revaRadii.lg,
    padding: 16,
  },
  redHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  redTitle: { flex: 1, fontSize: 15, fontWeight: '800', color: RED },
  redRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', paddingVertical: 4 },
  redBullet: { fontSize: 15, color: RED, lineHeight: 21 },
  redText: { flex: 1, fontSize: 14, color: '#8E2F22', lineHeight: 21, fontWeight: '500' },

  safetyNote: {
    fontSize: 12,
    color: C.ink3,
    lineHeight: 18,
    marginTop: 18,
    paddingHorizontal: 4,
  },
});
