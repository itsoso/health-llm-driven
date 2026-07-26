/**
 * Task 3: ExplainSheet — bottom drawer 展示一条 alert/finding 的 reasoning trace.
 *
 * 内容: summary / rule / twin 证据 / 记忆关联 / 置信度 note.
 * 数据源: useReasoningExplain hook → 后端 /reasoning-trace/{safety|specialist}/{audit_id}.
 *
 * 可见时才发起请求 (enabled=visible), 关闭后 React Query 按 staleTime 缓存.
 */
import React, { useEffect, useMemo } from 'react';
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
import { emitClientEvent } from '../../services/clientEvents';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

type Props =
  | { visible: boolean; onClose: () => void; source: 'safety'; auditId: number; ruleId: string }
  | { visible: boolean; onClose: () => void; source: 'specialist'; auditId: number; specialist: string };

export function ExplainSheet(props: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const reference = props.source === 'safety' ? props.ruleId : props.specialist;
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

  // Task 9: 抽屉每次打开发一条 client event, 观察期看板算点击率
  useEffect(() => {
    if (props.visible) {
      emitClientEvent('reasoning_sheet_opened', {
        source: props.source,
        audit_id: props.auditId,
        ref: reference,
      });
    }
  }, [
    props.visible,
    props.source,
    props.auditId,
    reference,
  ]);

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
          {q.data && <Body data={q.data} styles={styles} />}

          <Pressable onPress={props.onClose} style={styles.close}>
            <Text style={styles.closeText}>关闭</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function Body({ data, styles }: { data: ExplainResponse; styles: ReturnType<typeof createStyles> }) {
  return (
    <ScrollView
      style={{ maxHeight: 480 }}
      contentContainerStyle={{ paddingBottom: 12 }}
    >
      <Text style={styles.summary}>{data.summary}</Text>

      {data.rule && (
        <Section title="规则" styles={styles}>
          <Text style={styles.kv}>
            {data.rule.name} · {data.rule.category}
          </Text>
          {data.rule.threshold && (
            <Text style={styles.hint}>{data.rule.threshold}</Text>
          )}
        </Section>
      )}

      {data.specialist && (
        <Section title="专家" styles={styles}>
          <Text style={styles.kv}>
            {data.specialist}
            {data.kind ? ` · ${data.kind}` : ''}
          </Text>
        </Section>
      )}

      <Section title={`Twin 证据 (${data.twin_evidence.length})`} styles={styles}>
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

      <Section title={`记忆关联 (${data.related_facts.length})`} styles={styles}>
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
  styles,
}: {
  title: string;
  children: React.ReactNode;
  styles: ReturnType<typeof createStyles>;
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
});

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.35)',
      justifyContent: 'flex-end',
    },
    sheet: {
      backgroundColor: c.bgCard,
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
      backgroundColor: c.separator,
      marginBottom: 12,
    },
    title: { fontSize: 20, fontWeight: '600' as const, marginBottom: 8, color: c.labelPrimary },
    summary: { fontSize: 16, color: c.labelPrimary },
    sectionTitle: {
      fontSize: 13,
      fontWeight: '600' as const,
      color: c.labelSecondary,
      marginBottom: 6,
    },
    kv: { fontSize: 14, color: c.labelPrimary, marginVertical: 2 },
    hint: { color: c.labelTertiary, fontSize: 12 },
    footer: { marginTop: 16, color: c.labelTertiary, fontSize: 12 },
    err: { color: c.red, marginTop: 12 },
    close: { alignSelf: 'center', marginTop: 16, padding: 8 },
    closeText: { color: c.brand, fontSize: 15 },
  });
}
