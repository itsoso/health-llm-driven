import React, { useMemo, useState } from 'react';
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { invalidateRecordMutation, queryKeys } from '../applib/queryKeys';
import { radii, spacing } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import {
  getLatestBodyMeasurements,
  parseOptionalMeasurement,
  saveBodyMeasurements,
} from '../services/bodyMeasurements';
import { createBodyMetricsAgentContext } from '../utils/agentContext';

function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function BodyMeasurementsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ focus?: string }>();
  const qc = useQueryClient();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const [weightInput, setWeightInput] = useState('');
  const [waistInput, setWaistInput] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  const latestQuery = useQuery({
    queryKey: ['body-measurements', 'latest'],
    queryFn: getLatestBodyMeasurements,
    staleTime: 60_000,
  });

  const latest = latestQuery.data;
  const intro = params.focus === 'morning'
    ? '同一时间测量更利于看趋势。'
    : '体重和腰围一起看，比 BMI 更接近代谢风险。';
  const draftWeightKg = parseOptionalMeasurement(weightInput);
  const draftWaistCm = parseOptionalMeasurement(waistInput);
  const validDraftWeightKg = Number.isNaN(draftWeightKg) ? null : draftWeightKg;
  const validDraftWaistCm = Number.isNaN(draftWaistCm) ? null : draftWaistCm;

  const onSave = async () => {
    const weightKg = parseOptionalMeasurement(weightInput);
    const waistCm = parseOptionalMeasurement(waistInput);
    if (Number.isNaN(weightKg) || Number.isNaN(waistCm)) {
      Alert.alert('格式不正确', '请输入数字，例如 77.8 或 90.5。');
      return;
    }
    if (weightKg == null && waistCm == null) {
      Alert.alert('还没有数据', '至少填写体重或腰围其中一项。');
      return;
    }
    if (weightKg != null && (weightKg < 20 || weightKg > 300)) {
      Alert.alert('体重范围异常', '请确认体重是否在 20-300 kg 之间。');
      return;
    }
    if (waistCm != null && (waistCm <= 30 || waistCm >= 200)) {
      Alert.alert('腰围范围异常', '请确认腰围是否在 30-200 cm 之间。');
      return;
    }

    setSaving(true);
    try {
      await saveBodyMeasurements({
        recordDate: today(),
        weightKg,
        waistCm,
        notes: notes.trim() || undefined,
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setWeightInput('');
      setWaistInput('');
      setNotes('');
      await Promise.all([
        latestQuery.refetch(),
        invalidateRecordMutation(qc),
        qc.invalidateQueries({ queryKey: ['daily-plan', 'me'] }),
        qc.invalidateQueries({ queryKey: ['trajectory', 'me'] }),
        qc.invalidateQueries({ queryKey: ['twin', 'me'] }),
        qc.invalidateQueries({ queryKey: queryKeys.dashboard }),
      ]);
      Alert.alert('已记录', '体重和腰围会进入代谢健康轨迹。');
    } catch (e: any) {
      Alert.alert('保存失败', e?.response?.data?.detail || e?.message || '请稍后重试。');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <View style={styles.header}>
            <Pressable onPress={() => router.back()} hitSlop={10} accessibilityRole="button" accessibilityLabel="返回">
              <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
            </Pressable>
            <View style={styles.headerText}>
              <Text style={styles.title}>体重和腰围</Text>
              <Text style={styles.subtitle}>{intro}</Text>
            </View>
          </View>

          <View style={styles.latestRow}>
            <LatestTile
              label="最近体重"
              value={latest?.weight?.weight != null ? latest.weight.weight.toFixed(1) : '--'}
              unit="kg"
              date={latest?.weight?.record_date}
              color={c.brand}
            />
            <LatestTile
              label="最近腰围"
              value={latest?.waist?.waist_cm != null ? latest.waist.waist_cm.toFixed(1) : '--'}
              unit="cm"
              date={latest?.waist?.record_date}
              color={c.orange}
            />
          </View>

          <AgentFeedbackLink
            label="跟 Agent 看体重腰围趋势"
            accessibilityLabel="跟 Agent 看体重腰围趋势"
            prompt="请基于我的体重和腰围记录, 复盘趋势和代谢风险, 结合今天饮食和运动给出调整建议。请说明我接下来还应该记录哪些数据。"
            context={createBodyMetricsAgentContext({
              date: today(),
              latestWeightKg: latest?.weight?.weight ?? null,
              latestWeightDate: latest?.weight?.record_date ?? null,
              latestWaistCm: latest?.waist?.waist_cm ?? null,
              latestWaistDate: latest?.waist?.record_date ?? null,
              draft: {
                weightKg: validDraftWeightKg,
                waistCm: validDraftWaistCm,
                notes: notes.trim() || null,
              },
            })}
            badge="体重和腰围"
          />

          <View style={styles.formCard}>
            <Field
              label="体重"
              unit="kg"
              value={weightInput}
              onChangeText={setWeightInput}
              placeholder={latest?.weight?.weight != null ? latest.weight.weight.toFixed(1) : '例如 77.8'}
              accessibilityLabel="体重 kg"
            />
            <Field
              label="腰围"
              unit="cm"
              value={waistInput}
              onChangeText={setWaistInput}
              placeholder={latest?.waist?.waist_cm != null ? latest.waist.waist_cm.toFixed(1) : '例如 90.5'}
              accessibilityLabel="腰围 cm"
            />
            <TextInput
              value={notes}
              onChangeText={setNotes}
              placeholder="备注：空腹、运动后、旅行中..."
              placeholderTextColor={c.labelTertiary}
              style={styles.notesInput}
              multiline
              accessibilityLabel="备注"
            />
            <Pressable
              onPress={onSave}
              disabled={saving}
              accessibilityRole="button"
              accessibilityLabel="保存体重和腰围"
              style={({ pressed }) => [
                styles.saveBtn,
                { opacity: pressed || saving ? 0.78 : 1 },
              ]}
            >
              <Text style={styles.saveText}>{saving ? '保存中' : '保存记录'}</Text>
            </Pressable>
          </View>

          <View style={styles.automationCard}>
            <View style={styles.autoHeader}>
              <Ionicons name="git-network-outline" size={17} color={c.brand} />
              <Text style={styles.autoTitle}>自动化优先级</Text>
            </View>
            <AutomationRow title="1. 系统健康库" body="优先读取系统健康库；体重、腰围都先落到设备原生健康数据源。" />
            <AutomationRow title="2. 设备原生同步" body="智能体脂秤或智能软尺先同步到系统健康库，App 只做授权读取和去重。" />
            <AutomationRow title="3. 手动兜底" body="设备断链时只填一个数字，保存后进入 Twin、每日计划和轨迹复盘。" />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function LatestTile({
  label,
  value,
  unit,
  date,
  color,
}: {
  label: string;
  value: string;
  unit: string;
  date?: string;
  color: string;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.latestTile}>
      <Text style={styles.latestLabel}>{label}</Text>
      <Text style={[styles.latestValue, { color }]}>{value}<Text style={styles.latestUnit}> {unit}</Text></Text>
      <Text style={styles.latestDate}>{date ?? '暂无记录'}</Text>
    </View>
  );
}

function Field({
  label,
  unit,
  value,
  onChangeText,
  placeholder,
  accessibilityLabel,
}: {
  label: string;
  unit: string;
  value: string;
  onChangeText: (text: string) => void;
  placeholder: string;
  accessibilityLabel: string;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.fieldRow}>
      <View style={styles.fieldText}>
        <Text style={styles.fieldLabel}>{label}</Text>
        <Text style={styles.fieldHint}>{unit}</Text>
      </View>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={c.labelTertiary}
        keyboardType="decimal-pad"
        returnKeyType="done"
        style={styles.input}
        accessibilityLabel={accessibilityLabel}
      />
    </View>
  );
}

function AutomationRow({ title, body }: { title: string; body: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.autoRow}>
      <Text style={styles.autoRowTitle}>{title}</Text>
      <Text style={styles.autoBody}>{body}</Text>
    </View>
  );
}

function createStyles(c: ReturnType<typeof useTheme>['c']) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    flex: { flex: 1 },
    content: { padding: spacing.lg, gap: spacing.md, paddingBottom: 34 },
    header: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
    headerText: { flex: 1, gap: 3 },
    title: { fontSize: 24, fontWeight: '800', color: c.labelPrimary },
    subtitle: { fontSize: 13, lineHeight: 18, color: c.labelSecondary },
    latestRow: { flexDirection: 'row', gap: spacing.sm },
    latestTile: {
      flex: 1,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: 5,
    },
    latestLabel: { fontSize: 12, fontWeight: '600', color: c.labelSecondary },
    latestValue: { fontSize: 24, fontWeight: '800' },
    latestUnit: { fontSize: 12, fontWeight: '700', color: c.labelTertiary },
    latestDate: { fontSize: 11, color: c.labelTertiary },
    formCard: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: spacing.sm,
    },
    fieldRow: {
      flexDirection: 'row',
      alignItems: 'center',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.md,
      padding: spacing.sm,
      gap: spacing.sm,
    },
    fieldText: { width: 74, gap: 2 },
    fieldLabel: { fontSize: 14, fontWeight: '700', color: c.labelPrimary },
    fieldHint: { fontSize: 11, color: c.labelTertiary },
    input: {
      flex: 1,
      minHeight: 44,
      borderRadius: radii.sm,
      backgroundColor: c.fill,
      paddingHorizontal: spacing.md,
      fontSize: 20,
      fontWeight: '700',
      color: c.labelPrimary,
      textAlign: 'right',
    },
    notesInput: {
      minHeight: 54,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.md,
      padding: spacing.sm,
      fontSize: 14,
      color: c.labelPrimary,
      textAlignVertical: 'top',
    },
    saveBtn: {
      minHeight: 48,
      borderRadius: radii.full,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.brand,
    },
    saveText: { color: '#fff', fontSize: 16, fontWeight: '800' },
    automationCard: {
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      borderRadius: radii.lg,
      backgroundColor: c.bgCard,
      padding: spacing.md,
      gap: spacing.sm,
    },
    autoHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
    autoTitle: { fontSize: 16, fontWeight: '800', color: c.labelPrimary },
    autoRow: { gap: 3 },
    autoRowTitle: { fontSize: 13, fontWeight: '700', color: c.labelPrimary },
    autoBody: { fontSize: 12, lineHeight: 17, color: c.labelSecondary },
  });
}
