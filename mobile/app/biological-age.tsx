import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import api from '../services/api';
import { fetchMyProgress, pickBioAgeWin } from '../services/myProgress';
import { extractPhenoAge } from '../services/twinHelpers';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import BiologicalAgeCard from '../components/home/BiologicalAgeCard';

export default function BiologicalAgeScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const twinQuery = useQuery({
    queryKey: ['twin', 'me'],
    queryFn: async () => {
      const { data } = await api.get('/twin/me');
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const progressQuery = useQuery({
    queryKey: ['my-progress', 90],
    queryFn: () => fetchMyProgress(90),
    staleTime: 2 * 60 * 1000,
  });

  const phenoAge = extractPhenoAge(twinQuery.data);
  const bioAgeWin = pickBioAgeWin(progressQuery.data);
  const refreshing = twinQuery.isRefetching || progressQuery.isRefetching;
  const isLoading = twinQuery.isLoading;
  const claimBoundary = phenoAge.claimBoundary || '这是基于血检的代理指标,不作诊断或治疗结论。';

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['twin', 'me'] });
    qc.invalidateQueries({ queryKey: ['my-progress'] });
  };

  return (
    <>
      <Stack.Screen options={{ title: '生物年龄', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={c.brand} />}
        >
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>PhenoAge</Text>
            <Text style={styles.title}>生物年龄</Text>
            <Text style={styles.subtitle}>
              用完整体检血检估算身体年龄,并跟踪干预后是否真实变年轻。
            </Text>
          </View>

          {isLoading ? (
            <View style={styles.loading}>
              <ActivityIndicator color={c.brand} />
            </View>
          ) : (
            <BiologicalAgeCard
              view={phenoAge}
              win={bioAgeWin}
              isError={Boolean(twinQuery.error)}
              onPress={() => router.push('/medical-exams' as any)}
            />
          )}

          {phenoAge.status === 'ok' && phenoAge.phenotypicAge != null ? (
            <View style={styles.card}>
              <InfoRow label="身体年龄" value={`${phenoAge.phenotypicAge.toFixed(1)} 岁`} c={c} />
              <InfoRow
                label="实足年龄"
                value={phenoAge.chronoAge != null ? `${phenoAge.chronoAge.toFixed(1)} 岁` : '待补全'}
                c={c}
              />
              <InfoRow
                label="年龄差"
                value={phenoAge.deltaYears != null ? formatDelta(phenoAge.deltaYears) : '待补全'}
                c={c}
              />
            </View>
          ) : (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>还差这些血检项</Text>
              <Text style={styles.cardSub}>补齐后才能计算生物年龄,不会用缺失数据硬算。</Text>
              <View style={styles.chipWrap}>
                {phenoAge.missingLabels.map(label => (
                  <View key={label} style={styles.chip}>
                    <Text style={styles.chipText}>{label}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {bioAgeWin ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>最近一次改善</Text>
              <Text style={styles.winText}>
                干预后 {bioAgeWin.baseline} → {bioAgeWin.actual}, 年轻 {bioAgeWin.deltaYears.toFixed(1)} 岁
              </Text>
            </View>
          ) : null}

          <View style={styles.actionRow}>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => router.push('/medical-exams' as any)}>
              <Ionicons name="document-text-outline" size={16} color="#fff" />
              <Text style={styles.primaryText}>查看化验记录</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={() => router.push('/import' as any)}>
              <Text style={styles.secondaryText}>导入体检报告</Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.boundary}>{claimBoundary}</Text>
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function InfoRow({ label, value, c }: { label: string; value: string; c: ColorPalette }) {
  return (
    <View style={[stylesStatic.infoRow, { borderBottomColor: c.separator }]}>
      <Text style={[stylesStatic.infoLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[stylesStatic.infoValue, { color: c.labelPrimary }]}>{value}</Text>
    </View>
  );
}

function formatDelta(delta: number): string {
  if (delta <= -0.5) return `年轻 ${Math.abs(delta).toFixed(1)} 岁`;
  if (delta >= 0.5) return `偏老 ${delta.toFixed(1)} 岁`;
  return '与实足相当';
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    content: { padding: spacing.lg, paddingBottom: 120 },
    hero: { marginBottom: spacing.md },
    eyebrow: { color: c.brand, fontSize: 12, fontWeight: '800', letterSpacing: 0 },
    title: { color: c.labelPrimary, fontSize: 28, fontWeight: '900', marginTop: 4 },
    subtitle: { color: c.labelSecondary, fontSize: 14, lineHeight: 20, marginTop: 6 },
    loading: {
      minHeight: 96,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      marginBottom: spacing.md,
    },
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.md,
      marginBottom: spacing.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    cardTitle: { color: c.labelPrimary, fontSize: 16, fontWeight: '800' },
    cardSub: { color: c.labelTertiary, fontSize: 12, lineHeight: 17, marginTop: 4 },
    chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: spacing.md },
    chip: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: c.fill },
    chipText: { color: c.labelSecondary, fontSize: 12, fontWeight: '700' },
    winText: { color: c.labelPrimary, fontSize: 15, fontWeight: '800', marginTop: 8 },
    actionRow: { gap: spacing.sm, marginTop: spacing.xs, marginBottom: spacing.md },
    primaryBtn: {
      minHeight: 46,
      borderRadius: radii.md,
      backgroundColor: c.brand,
      alignItems: 'center',
      justifyContent: 'center',
      flexDirection: 'row',
      gap: 6,
    },
    primaryText: { color: '#fff', fontSize: 15, fontWeight: '800' },
    secondaryBtn: {
      minHeight: 42,
      borderRadius: radii.md,
      backgroundColor: c.fill,
      alignItems: 'center',
      justifyContent: 'center',
    },
    secondaryText: { color: c.labelSecondary, fontSize: 14, fontWeight: '800' },
    boundary: { color: c.labelTertiary, fontSize: 12, lineHeight: 18 },
  });
}

const stylesStatic = StyleSheet.create({
  infoRow: {
    minHeight: 42,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  infoLabel: { fontSize: 13, fontWeight: '700' },
  infoValue: { fontSize: 15, fontWeight: '900' },
});
