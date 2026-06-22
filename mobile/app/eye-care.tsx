/**
 * 科学用眼 (20-20-20) 设置屏。
 *
 * 开关 + 活跃时段 + 间隔 + 今日完成计数。纯客户端（无后端端点）。
 * R4：人体工学/护眼提示，不含医疗主张。
 * 这是时间驱动的 P1 近似 —— 不检测屏幕注视（P2/P3 由 Mac/Rokid 接入）。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle, Switch, ScrollView, Modal,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { spacing, radii, shadows } from '../constants/theme';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { useAuth } from '../hooks/useAuth';
import { useEyeBreakReminders } from '../hooks/useEyeBreakReminders';
import { EYE_BREAK_INTERVAL_OPTIONS, type EyeBreakPrefs } from '../services/eyeBreakReminders';
import { loadEyeBreakCount } from '../services/eyeBreakPrefs';

const START_PRESETS = ['07:00', '08:00', '09:00', '10:00', '11:00'];
const END_PRESETS = ['18:00', '19:00', '20:00', '21:00', '22:00', '23:00'];

export default function EyeCareScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { prefs, updatePrefs } = useEyeBreakReminders(isAuthenticated);
  const [editing, setEditing] = useState<null | 'start' | 'end' | 'interval'>(null);
  const [todayCount, setTodayCount] = useState(0);

  useEffect(() => {
    loadEyeBreakCount().then(setTodayCount);
  }, []);

  const setField = (patch: Partial<EyeBreakPrefs>) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    updatePrefs({ ...prefs, ...patch });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>科学用眼</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.card}>
          <View style={styles.row}>
            <Ionicons name="eye-outline" size={18} color={c.labelSecondary} />
            <View style={{ flex: 1 }}>
              <Text style={txt.rowLabel}>20-20-20 护眼提醒</Text>
              <Text style={txt.hintSmall}>开启后按下方时段定时提醒远眺</Text>
            </View>
            <Switch
              value={prefs.enabled}
              onValueChange={(v) => setField({ enabled: v })}
              trackColor={{ false: c.fill, true: c.brand }}
              thumbColor="#fff"
            />
          </View>
        </View>

        <Text style={txt.hintSmall}>
          每隔约 20 分钟，看 20 英尺(6 米)外 20 秒，放松睫状肌。这是基于使用时段的提醒，不会检测你是否真的在看屏幕。
        </Text>

        {prefs.enabled && (
          <>
            <Text style={txt.section}>活跃时段</Text>
            <Text style={txt.hintSmall}>只在此时段内提醒，避免夜间打扰。</Text>
            <View style={styles.card}>
              <PickRow label="开始" value={prefs.windowStart} onPress={() => setEditing('start')} />
              <PickRow label="结束" value={prefs.windowEnd} onPress={() => setEditing('end')} />
              <PickRow label="间隔" value={`${prefs.intervalMinutes} 分钟`} onPress={() => setEditing('interval')} />
            </View>

            <Text style={txt.section}>今日</Text>
            <View style={styles.card}>
              <View style={styles.row}>
                <Ionicons name="checkmark-done-outline" size={18} color={c.labelSecondary} />
                <Text style={txt.rowLabel}>今天完成远眺</Text>
                <Text style={txt.rowValue}>{todayCount} 次</Text>
              </View>
            </View>
            <Text style={txt.hintSmall}>计数仅保存在本机，不上传服务器。</Text>
          </>
        )}
      </ScrollView>

      <PickerModal
        visible={editing !== null}
        title={
          editing === 'start' ? '选择开始时间' :
          editing === 'end' ? '选择结束时间' : '选择间隔'
        }
        options={
          editing === 'interval'
            ? EYE_BREAK_INTERVAL_OPTIONS.map((m) => ({ value: String(m), label: `${m} 分钟` }))
            : (editing === 'start' ? START_PRESETS : END_PRESETS).map((t) => ({ value: t, label: t }))
        }
        current={
          editing === 'start' ? prefs.windowStart :
          editing === 'end' ? prefs.windowEnd :
          String(prefs.intervalMinutes)
        }
        onPick={(v) => {
          if (editing === 'start') setField({ windowStart: v });
          else if (editing === 'end') setField({ windowEnd: v });
          else if (editing === 'interval') setField({ intervalMinutes: Number(v) });
          setEditing(null);
        }}
        onClose={() => setEditing(null)}
      />
    </SafeAreaView>
  );
}

function PickRow({ label, value, onPress }: { label: string; value: string; onPress: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} activeOpacity={0.6}>
      <Text style={txt.rowLabel}>{label}</Text>
      <Text style={txt.rowValue}>{value}</Text>
      <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

function PickerModal({
  visible, title, options, current, onPick, onClose,
}: {
  visible: boolean;
  title: string;
  options: Array<{ value: string; label: string }>;
  current: string;
  onPick: (value: string) => void;
  onClose: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableOpacity style={styles.modalBackdrop} activeOpacity={1} onPress={onClose}>
        <View style={styles.modalCard}>
          <Text style={txt.modalTitle}>{title}</Text>
          <View style={styles.chipGrid}>
            {options.map((opt) => {
              const selected = opt.value === current;
              return (
                <TouchableOpacity
                  key={opt.value}
                  style={[styles.chip, selected && styles.chipSelected]}
                  onPress={() => onPick(opt.value)}
                  activeOpacity={0.7}
                >
                  <Text style={[txt.chipText, selected && txt.chipTextSelected]}>{opt.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
          <TouchableOpacity onPress={onClose} style={styles.modalClose}>
            <Text style={txt.modalCloseText}>取消</Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 60 },
  card: { backgroundColor: c.bgCard, borderRadius: radii.lg, marginBottom: spacing.md, ...shadows.subtle },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingHorizontal: spacing.lg, paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
  },
  modalBackdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'center', alignItems: 'center', padding: spacing.lg,
  },
  modalCard: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, width: '100%', maxWidth: 360,
  },
  chipGrid: {
    flexDirection: 'row', flexWrap: 'wrap', gap: 10,
    marginTop: spacing.md, marginBottom: spacing.md,
  },
  chip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: radii.md, backgroundColor: c.fill },
  chipSelected: { backgroundColor: c.brand },
  modalClose: {
    alignItems: 'center', paddingVertical: 12,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  section: { fontSize: 13, fontWeight: '500', color: c.labelSecondary, marginBottom: spacing.xs, marginTop: spacing.sm, marginLeft: spacing.xs } as TextStyle,
  rowLabel: { fontSize: 15, color: c.labelPrimary, flex: 1 } as TextStyle,
  rowValue: { fontSize: 14, color: c.labelTertiary } as TextStyle,
  hintSmall: { fontSize: 11, color: c.labelTertiary, marginLeft: spacing.xs, marginBottom: spacing.xs, lineHeight: 16 } as TextStyle,
  modalTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, textAlign: 'center' } as TextStyle,
  chipText: { fontSize: 15, color: c.labelPrimary } as TextStyle,
  chipTextSelected: { color: '#fff', fontWeight: '600' } as TextStyle,
  modalCloseText: { fontSize: 15, color: c.labelSecondary } as TextStyle,
});
