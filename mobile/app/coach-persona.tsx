/**
 * /coach-persona —— Coach Persona 选择 (Phase 3 P3-1).
 *
 * 三档单选, 实时 PATCH 后端. 不影响 specialist 逻辑, 只切 LLM 合成语气.
 */

import React from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../services/api';
import { useTheme } from '../hooks/useTheme';

type Persona = 'strict_coach' | 'gentle_advisor' | 'data_driven';

const OPTIONS: Array<{
  key: Persona;
  title: string;
  desc: string;
  example: string;
  icon: string;
}> = [
  {
    key: 'strict_coach',
    title: '严厉教练',
    desc: '直接命令式, 数字驱动, 不允许借口',
    example: '今天必须减量训练. 周三 RHR 已经 70, 再冲就过载.',
    icon: 'flame-outline',
  },
  {
    key: 'gentle_advisor',
    title: '温和顾问',
    desc: '共情解释, 给可选方案, 让你自己决定 (默认)',
    example: '看起来周三训练强度可以稍微调一下, 你可以选减量或换轻强度.',
    icon: 'leaf-outline',
  },
  {
    key: 'data_driven',
    title: '数据派',
    desc: '每条建议带具体数字阈值, 没废话',
    example: '把训练强度从 zone3 (155-165bpm) 降到 zone1 (115-130bpm), 30 分钟.',
    icon: 'analytics-outline',
  },
];

export default function CoachPersonaScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<{ coach_persona: Persona }>({
    queryKey: ['coach-persona'],
    queryFn: async () => {
      const res = await api.get('/users/me/coach-persona');
      return res.data;
    },
  });

  const mutation = useMutation({
    mutationFn: async (persona: Persona) => {
      const res = await api.patch('/users/me/coach-persona', { coach_persona: persona });
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['coach-persona'] });
    },
    onError: (err: any) => {
      Alert.alert('保存失败', err?.response?.data?.detail || err?.message || '请重试');
    },
  });

  const current = data?.coach_persona ?? 'gentle_advisor';

  return (
    <>
      <Stack.Screen options={{ title: 'AI 教练风格', headerBackTitle: '返回' }} />
      <ScrollView style={[styles.container, { backgroundColor: c.bgPrimary }]} contentContainerStyle={styles.content}>
        <Text style={[styles.intro, { color: c.labelSecondary }]}>
          切换 AI 给你建议时的语气. 不影响数据分析的准确度, 只影响"怎么跟你说".
        </Text>
        {isLoading && <ActivityIndicator />}
        {!isLoading && OPTIONS.map(opt => {
          const selected = opt.key === current;
          return (
            <TouchableOpacity
              key={opt.key}
              style={[
                styles.card,
                {
                  backgroundColor: c.bgCard,
                  borderColor: selected ? c.brand : c.separator,
                  borderWidth: selected ? 2 : 1,
                },
              ]}
              disabled={mutation.isPending}
              onPress={() => mutation.mutate(opt.key)}
            >
              <View style={styles.cardHeader}>
                <Ionicons name={opt.icon as any} size={20} color={selected ? c.brand : c.labelTertiary} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>{opt.title}</Text>
                {selected && <Ionicons name="checkmark-circle" size={20} color={c.brand} />}
              </View>
              <Text style={[styles.cardDesc, { color: c.labelSecondary }]}>{opt.desc}</Text>
              <View style={[styles.exampleBox, { backgroundColor: c.bgPrimary }]}>
                <Text style={[styles.exampleLabel, { color: c.labelTertiary }]}>示例</Text>
                <Text style={[styles.exampleText, { color: c.labelSecondary }]}>{opt.example}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
        <Text style={[styles.note, { color: c.labelTertiary }]}>
          切换立即生效. 下一条 AI 回复就会按新风格.
        </Text>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: 16, paddingBottom: 48, gap: 12 },
  intro: { fontSize: 13, lineHeight: 20, marginBottom: 8 },
  card: {
    borderRadius: 12,
    padding: 16,
    gap: 10,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardTitle: { flex: 1, fontSize: 16, fontWeight: '600' },
  cardDesc: { fontSize: 13, lineHeight: 19 },
  exampleBox: {
    borderRadius: 8,
    padding: 10,
    marginTop: 4,
    gap: 4,
  },
  exampleLabel: { fontSize: 10, fontWeight: '600' },
  exampleText: { fontSize: 13, lineHeight: 19, fontStyle: 'italic' },
  note: { fontSize: 11, textAlign: 'center', marginTop: 8 },
});
