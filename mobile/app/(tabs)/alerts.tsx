import React, { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { getSafetyReport, explainAlert, type SafetyAlert } from '@/services/safety';

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  critical: { color: '#FF3B30', bg: '#FFF0F0', icon: 'alert-circle' },
  high:     { color: '#FF9500', bg: '#FFF8F0', icon: 'alert-circle-outline' },
  medium:   { color: '#FFCC00', bg: '#FFFDF0', icon: 'warning-outline' },
  low:      { color: '#007AFF', bg: '#F0F7FF', icon: 'information-circle-outline' },
  info:     { color: '#8E8E93', bg: '#F5F5F7', icon: 'information-outline' },
};

export default function AlertsScreen() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['safety'],
    queryFn: getSafetyReport,
  });

  const alerts = (data?.alerts || []).sort((a, b) => {
    const order = ['critical', 'high', 'medium', 'low', 'info'];
    return order.indexOf(a.severity) - order.indexOf(b.severity);
  });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {alerts.length === 0 ? (
        <EmptyState onRefresh={refetch} refreshing={isRefetching} />
      ) : (
        <FlatList
          data={alerts}
          keyExtractor={(item, idx) => `${item.rule_id}-${idx}`}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor="#007AFF"
            />
          }
          ListHeaderComponent={
            <Text style={styles.header}>
              {alerts.length} 条告警 | {data?.rules_evaluated ?? 0} 条规则已评估
            </Text>
          }
          renderItem={({ item }) => <AlertItem alert={item} />}
        />
      )}
    </SafeAreaView>
  );
}

function EmptyState({
  onRefresh,
  refreshing,
}: {
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <FlatList
      data={[]}
      renderItem={() => null}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#007AFF" />
      }
      ListEmptyComponent={
        <View style={styles.empty}>
          <View style={styles.emptyCircle}>
            <Ionicons name="checkmark-circle" size={64} color="#34C759" />
          </View>
          <Text style={styles.emptyTitle}>所有指标正常</Text>
          <Text style={styles.emptySubtitle}>没有发现需要关注的健康告警</Text>
        </View>
      }
    />
  );
}

function AlertItem({ alert }: { alert: SafetyAlert }) {
  const [expanded, setExpanded] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);

  const cfg = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;

  const handleExplain = async () => {
    if (explanation) return;
    setExplaining(true);
    try {
      const result = await explainAlert(alert.rule_id, alert.message);
      setExplanation(result.explanation);
    } catch {
      setExplanation('无法获取解读，请稍后重试');
    } finally {
      setExplaining(false);
    }
  };

  return (
    <TouchableOpacity
      style={[styles.alertCard, { borderLeftColor: cfg.color }]}
      onPress={() => setExpanded(!expanded)}
      activeOpacity={0.7}
    >
      <View style={styles.alertHeader}>
        <Ionicons name={cfg.icon} size={20} color={cfg.color} />
        <View style={styles.alertTitleWrap}>
          <Text style={styles.alertTitle}>{alert.title}</Text>
          <Text style={styles.alertCategory}>{alert.category}</Text>
        </View>
        <View style={[styles.severityBadge, { backgroundColor: cfg.bg }]}>
          <Text style={[styles.severityText, { color: cfg.color }]}>
            {alert.severity}
          </Text>
        </View>
      </View>
      <Text style={styles.alertMessage}>{alert.message}</Text>
      {alert.action && (
        <Text style={styles.alertAction}>{alert.action}</Text>
      )}
      {expanded && (
        <View style={styles.expandedSection}>
          <TouchableOpacity style={styles.explainBtn} onPress={handleExplain}>
            {explaining ? (
              <ActivityIndicator size="small" color="#007AFF" />
            ) : (
              <>
                <Ionicons name="sparkles" size={16} color="#007AFF" />
                <Text style={styles.explainBtnText}>AI 解读</Text>
              </>
            )}
          </TouchableOpacity>
          {explanation && (
            <Text style={styles.explanationText}>{explanation}</Text>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#FDFBF7' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 16 },
  header: {
    fontSize: 13,
    color: '#8E8E93',
    marginBottom: 12,
    fontWeight: '500',
  },
  alertCard: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderLeftWidth: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  alertHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 8,
  },
  alertTitleWrap: { flex: 1 },
  alertTitle: { fontSize: 15, fontWeight: '600', color: '#1C1C1E' },
  alertCategory: { fontSize: 11, color: '#8E8E93', marginTop: 2 },
  severityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  severityText: { fontSize: 11, fontWeight: '600', textTransform: 'uppercase' },
  alertMessage: { fontSize: 14, color: '#3C3C43', lineHeight: 20 },
  alertAction: {
    fontSize: 13,
    color: '#007AFF',
    marginTop: 8,
    fontWeight: '500',
  },
  expandedSection: { marginTop: 12, paddingTop: 12, borderTopWidth: 0.5, borderTopColor: '#E5E5EA' },
  explainBtn: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  explainBtnText: { fontSize: 14, color: '#007AFF', fontWeight: '500' },
  explanationText: {
    fontSize: 14,
    color: '#3C3C43',
    lineHeight: 20,
    marginTop: 10,
    backgroundColor: '#F5F5F7',
    padding: 12,
    borderRadius: 10,
  },
  empty: { alignItems: 'center', paddingTop: 120 },
  emptyCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#F0FFF4',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
  },
  emptyTitle: { fontSize: 20, fontWeight: '700', color: '#1C1C1E' },
  emptySubtitle: { fontSize: 14, color: '#8E8E93', marginTop: 4 },
});
