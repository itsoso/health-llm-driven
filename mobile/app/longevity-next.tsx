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

import {
  getCausalNotes,
  getNextData,
  pickCausalHighlight,
  topNextData,
  type NextDataSuggestion,
} from '../services/longevityHome';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import LongevityNextCard from '../components/home/LongevityNextCard';

export default function LongevityNextScreen() {
  const router = useRouter();
  const qc = useQueryClient();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const nextQuery = useQuery({
    queryKey: ['longevity', 'next-data'],
    queryFn: getNextData,
    staleTime: 5 * 60 * 1000,
  });
  const causalQuery = useQuery({
    queryKey: ['longevity', 'causal-notes'],
    queryFn: getCausalNotes,
    staleTime: 5 * 60 * 1000,
  });

  const top = topNextData(nextQuery.data);
  const causal = pickCausalHighlight(causalQuery.data);
  const suggestions = nextQuery.data?.suggestions ?? [];
  const isLoading = nextQuery.isLoading || causalQuery.isLoading;
  const refreshing = nextQuery.isRefetching || causalQuery.isRefetching;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['longevity'] });
  };
  const openSuggestion = (item?: NextDataSuggestion | null) => {
    router.push((item?.route || '/medical-exams') as any);
  };

  return (
    <>
      <Stack.Screen options={{ title: '抗衰下一步', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={c.brand} />}
        >
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>Longevity Plan</Text>
            <Text style={styles.title}>抗衰下一步</Text>
            <Text style={styles.subtitle}>
              优先补最能提升判断力的数据,并回看哪些行动和指标改善相关。
            </Text>
          </View>

          {isLoading ? (
            <View style={styles.loading}>
              <ActivityIndicator color={c.brand} />
            </View>
          ) : top || causal ? (
            <LongevityNextCard next={top} causal={causal} onPress={() => openSuggestion(top)} />
          ) : (
            <View style={styles.emptyCard}>
              <Ionicons name="leaf-outline" size={28} color={c.labelTertiary} />
              <Text style={styles.emptyTitle}>暂时没有新的抗衰建议</Text>
              <Text style={styles.emptySub}>
                先补齐体检、睡眠、训练或饮食记录,系统会重新计算下一步信息增益。
              </Text>
            </View>
          )}

          {suggestions.length > 0 ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>按优先级补数据</Text>
              {suggestions
                .slice()
                .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
                .map(item => (
                  <TouchableOpacity
                    key={`${item.item}-${item.unlocks}`}
                    style={styles.suggestionRow}
                    onPress={() => openSuggestion(item)}
                    activeOpacity={0.72}
                  >
                    <View style={styles.rankBubble}>
                      <Text style={styles.rankText}>{item.priority ?? 0}</Text>
                    </View>
                    <View style={styles.suggestionTextWrap}>
                      <Text style={styles.suggestionTitle}>{item.item}</Text>
                      <Text style={styles.suggestionSub} numberOfLines={2}>
                        解锁 {item.unlocks}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
                  </TouchableOpacity>
                ))}
            </View>
          ) : null}

          {causal ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>最近的相关变化</Text>
              <Text style={styles.causalText}>{causal.text}</Text>
              <Text style={styles.boundary}>相关非因果。用于安排下一步验证,不直接宣称治疗效果。</Text>
            </View>
          ) : null}

          <View style={styles.actionRow}>
            <TouchableOpacity style={styles.primaryBtn} onPress={() => openSuggestion(top)}>
              <Ionicons name="navigate-outline" size={16} color="#fff" />
              <Text style={styles.primaryText}>{top?.route ? '去完成下一步' : '补齐体检数据'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={() => router.push('/my-progress' as any)}>
              <Text style={styles.secondaryText}>查看结果追踪</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    </>
  );
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
    emptyCard: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.lg,
      alignItems: 'center',
      gap: 8,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      marginBottom: spacing.md,
    },
    emptyTitle: { color: c.labelPrimary, fontSize: 16, fontWeight: '900' },
    emptySub: { color: c.labelTertiary, fontSize: 13, lineHeight: 19, textAlign: 'center' },
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.md,
      marginBottom: spacing.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    cardTitle: { color: c.labelPrimary, fontSize: 16, fontWeight: '900', marginBottom: spacing.sm },
    suggestionRow: {
      minHeight: 58,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
      paddingVertical: 10,
    },
    rankBubble: {
      minWidth: 32,
      height: 32,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.brandLight,
    },
    rankText: { color: c.brand, fontSize: 12, fontWeight: '900' },
    suggestionTextWrap: { flex: 1, minWidth: 0 },
    suggestionTitle: { color: c.labelPrimary, fontSize: 15, fontWeight: '800' },
    suggestionSub: { color: c.labelTertiary, fontSize: 12, lineHeight: 17, marginTop: 2 },
    causalText: { color: c.labelPrimary, fontSize: 14, lineHeight: 20, fontWeight: '700' },
    boundary: { color: c.labelTertiary, fontSize: 12, lineHeight: 18, marginTop: spacing.sm },
    actionRow: { gap: spacing.sm, marginTop: spacing.xs },
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
  });
}
