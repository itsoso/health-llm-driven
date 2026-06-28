import React from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  connectionHealthDisplay,
  fetchDataConnections,
  revokeDataConnection,
  type DataConnection,
} from '../services/dataConnections';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

function providerIcon(connection: DataConnection): keyof typeof Ionicons.glyphMap {
  const text = `${connection.provider} ${connection.provider_type}`.toLowerCase();
  if (text.includes('garmin') || text.includes('wearable') || text.includes('healthkit')) return 'watch-outline';
  if (text.includes('fhir') || text.includes('report') || text.includes('lab')) return 'document-text-outline';
  if (text.includes('device')) return 'hardware-chip-outline';
  return 'link-outline';
}

function statusTone(severity: string, c: ColorPalette) {
  if (severity === 'ok') {
    return { color: c.green, bg: c.tintGreen };
  }
  if (severity === 'blocked') {
    return { color: c.labelTertiary, bg: c.fill };
  }
  return { color: c.orange, bg: c.tintOrange };
}

function formatSync(connection: DataConnection): string {
  if (connection.sync_error) return connection.sync_error;
  if (connection.last_success_at) return `最近成功 ${connection.last_success_at.slice(0, 10)}`;
  if (connection.last_attempt_at) return `最近尝试 ${connection.last_attempt_at.slice(0, 10)}`;
  return '等待首次同步';
}

function ConnectionCard({
  connection,
  onRevoke,
  isRevoking,
}: {
  connection: DataConnection;
  onRevoke: (connection: DataConnection) => void;
  isRevoking: boolean;
}) {
  const { c } = useTheme();
  const styles = createStyles(c);
  const display = connectionHealthDisplay(connection);
  const tone = statusTone(display.health.severity, c);
  const canRevoke = connection.connection_status !== 'revoked';

  return (
    <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.cardHeader}>
        <View style={[styles.iconWrap, { backgroundColor: c.brandLight }]}>
          <Ionicons name={providerIcon(connection)} size={18} color={c.brand} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={[styles.name, { color: c.labelPrimary }]} numberOfLines={1}>
            {connection.display_name}
          </Text>
          <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1}>
            {connection.provider_type} · token {connection.token_status}
          </Text>
        </View>
        <View style={[styles.statusPill, { backgroundColor: tone.bg }]}>
          <Text style={[styles.statusText, { color: tone.color }]}>{display.label}</Text>
        </View>
      </View>

      <View style={styles.scopeRow}>
        {connection.scopes.slice(0, 5).map((scope) => (
          <View key={scope} style={[styles.scopeChip, { backgroundColor: c.fill }]}>
            <Text style={[styles.scopeText, { color: c.labelSecondary }]}>{scope}</Text>
          </View>
        ))}
      </View>

      <Text style={[styles.line, { color: c.labelSecondary }]}>{formatSync(connection)}</Text>
      <Text style={[styles.line, { color: c.labelSecondary }]}>{display.description}</Text>
      <View style={styles.healthMetaRow}>
        <View style={[styles.healthChip, { backgroundColor: c.fill }]}>
          <Ionicons
            name={display.health.can_use_cached_data ? 'file-tray-full-outline' : 'ban-outline'}
            size={13}
            color={display.health.can_use_cached_data ? c.green : c.labelTertiary}
          />
          <Text
            style={[
              styles.healthChipText,
              { color: display.health.can_use_cached_data ? c.green : c.labelTertiary },
            ]}
          >
            {display.cacheLabel}
          </Text>
        </View>
        {display.health.needs_reconnect ? (
          <View style={[styles.healthChip, { backgroundColor: c.tintOrange }]}>
            <Ionicons name="refresh-circle-outline" size={13} color={c.orange} />
            <Text style={[styles.healthChipText, { color: c.orange }]}>{display.actionLabel}</Text>
          </View>
        ) : null}
      </View>
      {connection.policy ? (
        <Text style={[styles.line, { color: c.labelTertiary }]}>
          降级: {connection.policy.degraded_behavior ?? 'read_only'} · 最小化: {connection.policy.data_minimization ?? 'scoped_fields_only'}
        </Text>
      ) : null}

      {canRevoke ? (
        <TouchableOpacity
          style={[styles.revokeButton, { borderColor: c.separator }]}
          onPress={() => onRevoke(connection)}
          disabled={isRevoking}
          accessibilityRole="button"
        >
          <Ionicons name="close-circle-outline" size={16} color={c.red} />
          <Text style={[styles.revokeText, { color: c.red }]}>{isRevoking ? '撤权中' : '撤权'}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export default function DataConnectionsScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = createStyles(c);
  const qc = useQueryClient();

  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ['data-connections'],
    queryFn: fetchDataConnections,
    staleTime: 120_000,
  });
  const revokeMutation = useMutation({
    mutationFn: revokeDataConnection,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['data-connections'] }),
  });

  const onRevoke = (connection: DataConnection) => {
    Alert.alert(
      '撤销连接授权',
      `撤销后 ${connection.display_name} 的同步和外部授权会停止。`,
      [
        { text: '取消', style: 'cancel' },
        { text: '撤权', style: 'destructive', onPress: () => revokeMutation.mutate(connection.id) },
      ],
    );
  };

  const connections = data?.connections ?? [];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={[styles.title, { color: c.labelPrimary }]}>数据连接与授权</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} />}
      >
        {isLoading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={c.labelTertiary} />
        ) : error ? (
          <Text style={[styles.empty, { color: c.labelTertiary }]}>加载失败,下拉重试</Text>
        ) : connections.length === 0 ? (
          <View style={[styles.emptyCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <Ionicons name="key-outline" size={22} color={c.labelTertiary} />
            <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>暂无统一连接</Text>
            <Text style={[styles.emptyText, { color: c.labelTertiary }]}>
              Garmin、HealthKit、报告/FHIR 导入会逐步纳入这里,用于查看 scope、同步状态、授权和撤权。
            </Text>
          </View>
        ) : (
          <>
            <Text style={[styles.hint, { color: c.labelTertiary }]}>
              这里只展示连接状态、授权范围和来源追踪,不显示或保存原始 token。
            </Text>
            {connections.map((connection) => (
              <ConnectionCard
                key={connection.id}
                connection={connection}
                onRevoke={onRevoke}
                isRevoking={revokeMutation.isPending && revokeMutation.variables === connection.id}
              />
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) =>
  StyleSheet.create({
    safe: { flex: 1 },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    title: { fontSize: 17, fontWeight: '700' },
    content: { padding: spacing.lg, paddingBottom: 110, gap: spacing.md },
    hint: { fontSize: 12, lineHeight: 18 },
    card: { borderRadius: radii.lg, borderWidth: StyleSheet.hairlineWidth, padding: spacing.md, gap: 10 },
    cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    iconWrap: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
    name: { fontSize: 15, fontWeight: '800' },
    sub: { fontSize: 12, fontWeight: '500' },
    statusPill: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
    statusText: { fontSize: 11, fontWeight: '700' },
    scopeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    scopeChip: { borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 },
    scopeText: { fontSize: 11, fontWeight: '600' },
    line: { fontSize: 12, lineHeight: 17 },
    healthMetaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    healthChip: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 4,
    },
    healthChipText: { fontSize: 11, fontWeight: '700' },
    revokeButton: {
      alignSelf: 'flex-start',
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    revokeText: { fontSize: 12, fontWeight: '700' },
    empty: { fontSize: 14, textAlign: 'center', marginTop: 40, lineHeight: 20, paddingHorizontal: spacing.lg },
    emptyCard: {
      borderWidth: StyleSheet.hairlineWidth,
      borderRadius: radii.lg,
      padding: spacing.lg,
      alignItems: 'center',
      gap: 8,
    },
    emptyTitle: { fontSize: 15, fontWeight: '700' },
    emptyText: { fontSize: 13, lineHeight: 20, textAlign: 'center' },
  });
