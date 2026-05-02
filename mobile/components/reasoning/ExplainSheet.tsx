/**
 * Task 3: ExplainSheet — bottom drawer 展示一条 alert/finding 的 reasoning trace.
 *
 * 内容: summary / rule / twin 证据 / 记忆关联 / 置信度 note.
 * 数据源: useReasoningExplain hook → 后端 /reasoning-trace/{safety|specialist}/{audit_id}.
 *
 * 可见时才发起请求 (enabled=visible), 关闭后 React Query 按 staleTime 缓存.
 */
import React from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  ActivityIndicator,
} from 'react-native';
import { useReasoningExplain } from '../../hooks/useReasoningExplain';
import type { ExplainResponse } from '../../services/reasoningTrace';

type Props =
  | { visible: boolean; onClose: () => void; source: 'safety'; auditId: number; ruleId: string }
  | { visible: boolean; onClose: () => void; source: 'specialist'; auditId: number; specialist: string };

export function ExplainSheet(props: Props) {
  const q = useReasoningExplain(
    props.source === 'safety'
      ? {
          source: 'safety',
          auditId: props.auditId,
          ruleId: props.ruleId,
          enabled: props.visible,
        }
      : {
          source: 'specialist',
          auditId: props.auditId,
          specialist: props.specialist,
          enabled: props.visible,
        },
  );

  return (
    <Modal
      visible={props.visible}
      transparent
      animationType="slide"
      onRequestClose={props.onClose}
    >
      <Pressable style={styles.backdrop} onPress={props.onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handle} />
          <Text style={styles.title}>为什么?</Text>

          {q.isLoading && <ActivityIndicator style={{ marginTop: 20 }} />}
          {q.isError && (
            <Text style={styles.err}>
              加载失败: {(q.error as Error)?.message || '未知错误'}
            </Text>
          )}
          {q.data && <Body data={q.data} />}

          <Pressable onPress={props.onClose} style={styles.close}>
            <Text style={styles.closeText}>关闭</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function Body({ data }: { data: ExplainResponse }) {
  return (
    <ScrollView
      style={{ maxHeight: 480 }}
      contentContainerStyle={{ paddingBottom: 12 }}
    >
      <Text style={styles.summary}>{data.summary}</Text>

      {data.rule && (
        <Section title="规则">
          <Text style={styles.kv}>
            {data.rule.name} · {data.rule.category}
          </Text>
          {data.rule.threshold && (
            <Text style={styles.hint}>{data.rule.threshold}</Text>
          )}
        </Section>
      )}

      {data.specialist && (
        <Section title="专家">
          <Text style={styles.kv}>
            {data.specialist}
            {data.kind ? ` · ${data.kind}` : ''}
          </Text>
        </Section>
      )}

      <Section title={`Twin 证据 (${data.twin_evidence.length})`}>
        {data.twin_evidence.length === 0 ? (
          <Text style={styles.hint}>数据不足</Text>
        ) : (
          data.twin_evidence.map((e, i) => (
            <Text key={`${e.partition}.${e.field}.${i}`} style={styles.kv}>
              {e.partition}.{e.field} = {String(e.value)}{'  '}
              <Text style={styles.hint}>({e.source})</Text>
            </Text>
          ))
        )}
      </Section>

      <Section title={`记忆关联 (${data.related_facts.length})`}>
        {data.related_facts.length === 0 ? (
          <Text style={styles.hint}>基于确定性规则, 无记忆关联</Text>
        ) : (
          data.related_facts.map((f) => (
            <Text key={f.id} style={styles.kv}>
              • {f.preview}{'  '}
              <Text style={styles.hint}>[{f.tier}]</Text>
            </Text>
          ))
        )}
      </Section>

      <Text style={styles.footer}>{data.confidence_note}</Text>
    </ScrollView>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ marginTop: 16 }}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.35)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 20,
    paddingBottom: 32,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D1D5DB',
    marginBottom: 12,
  },
  title: { fontSize: 20, fontWeight: '600', marginBottom: 8 },
  summary: { fontSize: 16, color: '#111827' },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6B7280',
    marginBottom: 6,
  },
  kv: { fontSize: 14, color: '#111827', marginVertical: 2 },
  hint: { color: '#6B7280', fontSize: 12 },
  footer: { marginTop: 16, color: '#9CA3AF', fontSize: 12 },
  err: { color: '#B91C1C', marginTop: 12 },
  close: { alignSelf: 'center', marginTop: 16, padding: 8 },
  closeText: { color: '#4F46E5', fontSize: 15 },
});
