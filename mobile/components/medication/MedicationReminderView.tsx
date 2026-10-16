import React from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { revaColors as C, revaRadii as R } from '../../constants/revaTheme';
import type { MedicationReminderContext } from '../../services/medicationReminderLanding';

export interface MedicationReminderViewProps {
  context: MedicationReminderContext | null;
  loading: boolean;
  busy: boolean;
  error: string | null;
  message: string | null;
  onBack: () => void;
  onManage: () => void;
  onRetry: () => void;
  onConfirmDate: () => void;
  onTaken: () => void;
  onSkipped: () => void;
  onSelectTime?: (time: string) => void;
}

const reasons: Record<string, string> = {
  date_confirmation_required: '这条提醒没有明确日期。请先核对今天的日期，再查看今天这一剂的记录。',
  time_required: '这条提醒缺少用药时间，请到用药管理中核对。',
  timezone_mismatch: '提醒时区与当前账户时区不一致，请先核对提醒设置。',
  inactive: '这项用药已不在使用中，请到用药管理中核对。',
  invalid_medication_name: '这项记录的药品名称需要核对，暂不能直接打卡。',
  dose_missing: '这项记录尚未填写剂量，请先核对用药档案。',
  schedule_changed: '这项用药的提醒时间已变更，请先核对当前安排。',
  future_occurrence: '这次提醒的时间尚未到，暂不能记录服用情况。',
  outside_course: '这次提醒不在当前记录的用药日期范围内，请先核对。',
  already_recorded: '这次提醒已有记录。',
};

export default function MedicationReminderView(p: MedicationReminderViewProps) {
  const c = p.context;
  const canAct = !!c?.actionable && !c.log && !c.requires_date_confirmation && !p.loading && !p.error;
  const confirmation = !!c?.requires_date_confirmation && !c.log && !p.error;
  const slots = c?.time === null && p.onSelectTime && !p.error && !c.log
    ? [...new Set((c.medication.reminder_times || []).filter(time => /^([01]\d|2[0-3]):[0-5]\d$/.test(time)))] : [];
  const status = c?.log ? (c.log.status === 'taken' ? '已记录 · 已服用' : c.log.status === 'skipped' ? '已记录 · 本次未服用' : '已有记录 · 请核对')
    : c?.requires_date_confirmation ? '提醒日期待确认' : canAct ? '待记录' : '需要核对';

  return (
    <SafeAreaView style={s.safe} edges={['top', 'bottom']}>
      <View style={s.header}>
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="返回" onPress={p.onBack} style={s.back}>
          <Ionicons name="chevron-back" size={26} color={C.ink1} />
        </TouchableOpacity>
        <Text style={s.title}>用药提醒</Text>
        <View style={s.headerSpacer} />
      </View>
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.content}>
          {p.loading ? <View style={s.loading} accessibilityRole="progressbar" accessibilityLabel="正在核对本次提醒">
            <ActivityIndicator color={C.green600} /><Text style={s.secondary}>正在核对本次提醒…</Text>
          </View> : <>
            {c && <>
              <View style={s.hero}>
                <Text style={s.eyebrow}>本次提醒</Text>
                <Text style={s.time}>{c.time || '时间待核对'}</Text>
                <View style={s.dateRow}><Text style={s.date}>{c.requires_date_confirmation ? c.today_date : c.date}</Text>
                  {c.requires_date_confirmation && <Text style={s.date}>今天 · 待确认</Text>}</View>
                <Text style={s.timezone}>{c.timezone}</Text>
                <View style={s.chip}><Text style={s.chipText}>{status}</Text></View>
              </View>
              <View style={s.card}>
                <View style={s.medicationHeading}><View style={s.icon}><Ionicons name="medical-outline" size={23} color={C.green700} /></View>
                  <Text style={s.name}>{c.medication.name}</Text></View>
                <View style={s.detailRow}><Text style={s.detailLabel}>记录剂量</Text><Text style={s.detailValue}>{c.medication.dosage || '尚未填写'}</Text></View>
                {!!c.medication.frequency && <View style={s.detailRow}><Text style={s.detailLabel}>用药频次</Text><Text style={s.detailValue}>{c.medication.frequency}</Text></View>}
                {!!c.medication.timing_label && <View style={s.detailRow}><Text style={s.detailLabel}>用药时间</Text><Text style={s.detailValue}>{c.medication.timing_label}</Text></View>}
                <Text style={s.source}>以上信息来自你的用药档案</Text>
              </View>
              {slots.length > 0 && <View style={s.card}><Text style={s.noticeTitle}>选择要查看的提醒时间</Text>
                <View style={s.dateRow}>{slots.map(time => <TouchableOpacity key={time} accessibilityRole="button" accessibilityLabel={`查看 ${time} 这次提醒`} disabled={p.busy} accessibilityState={{ disabled: p.busy }} onPress={() => p.onSelectTime?.(time)} style={s.slot}><Text style={s.manageText}>{time}</Text></TouchableOpacity>)}</View>
              </View>}
              {c.medication.safety_alerts?.map((alert, index) => <View key={`${alert.rule_id}-${index}`} style={s.notice}>
                <Text style={s.noticeTitle}>{alert.title}</Text><Text style={s.body}>{alert.message}</Text>
              </View>)}
              {!c.log && !canAct && !p.error && <View style={s.notice}><Text style={s.body}>{reasons[c.reason || ''] || '暂时无法核对这次提醒，请重新核对或查看用药管理。'}</Text></View>}
            </>}
            {p.error && <View style={s.notice} accessibilityLiveRegion="polite"><Text style={s.noticeTitle}>暂未完成核对</Text><Text style={s.body}>{p.error}</Text></View>}
            {!c && !p.error && <View style={s.card}><Text style={s.noticeTitle}>暂时无法打开这次提醒</Text><Text style={s.body}>请重新核对，或到用药管理中查看当前安排。</Text></View>}
            {!!p.message && <Text style={s.message} accessibilityLiveRegion="polite">{p.message}</Text>}
            {confirmation && <TouchableOpacity accessibilityRole="button" accessibilityLabel="查看今天这次提醒" disabled={p.busy} accessibilityState={{ disabled: p.busy }} onPress={p.onConfirmDate} style={[s.primary, p.busy && s.disabled]}>
              <Text style={s.primaryText}>查看今天这次提醒</Text></TouchableOpacity>}
            {canAct && <View style={s.actions}>
              <TouchableOpacity accessibilityRole="button" accessibilityLabel="确认已服用" accessibilityState={{ disabled: p.busy, busy: p.busy }} disabled={p.busy} onPress={p.onTaken} style={[s.primary, p.busy && s.disabled]}>
                {p.busy && <ActivityIndicator color={C.greenOn} />}<Text style={s.primaryText}>{p.busy ? '正在保存记录…' : '确认已服用'}</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityRole="button" accessibilityLabel="记录本次未服用" accessibilityState={{ disabled: p.busy }} disabled={p.busy} onPress={p.onSkipped} style={[s.secondaryButton, p.busy && s.disabled]}><Text style={s.secondaryButtonText}>记录本次未服用</Text></TouchableOpacity>
            </View>}
            {(p.error || (!canAct && !c?.log)) && <TouchableOpacity accessibilityRole="button" accessibilityLabel="重新核对" disabled={p.busy} accessibilityState={{ disabled: p.busy }} onPress={p.onRetry} style={s.secondaryButton}><Text style={s.secondaryButtonText}>重新核对</Text></TouchableOpacity>}
          </>}
          <Text style={s.footnote}>仅记录实际服用情况，不调整用药方案</Text>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel="查看用药管理" onPress={p.onManage} style={s.manage}>
            <Text style={s.manageText}>查看用药管理</Text><Ionicons name="chevron-forward" size={18} color={C.green700} />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8 },
  back: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  headerSpacer: { width: 44 }, title: { flex: 1, textAlign: 'center', fontSize: 20, fontWeight: '700', color: C.ink1 },
  scroll: { flexGrow: 1, padding: 20, paddingBottom: 32 },
  content: { width: '100%', maxWidth: 640, alignSelf: 'center', gap: 16 },
  hero: { backgroundColor: C.green50, borderRadius: R.xl, padding: 24, gap: 8 },
  eyebrow: { fontSize: 14, color: C.green700, fontWeight: '600' },
  time: { fontSize: 46, fontWeight: '600', color: C.green700, fontVariant: ['tabular-nums'] },
  dateRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, date: { fontSize: 16, color: C.ink1 },
  timezone: { fontSize: 13, color: C.ink2 },
  chip: { alignSelf: 'flex-start', backgroundColor: C.surface, borderRadius: R.pill, paddingHorizontal: 12, paddingVertical: 7, marginTop: 8 },
  chipText: { fontSize: 13, color: C.green700, fontWeight: '600' },
  card: { backgroundColor: C.surface, borderRadius: R.xl, padding: 20, gap: 16 },
  medicationHeading: { flexDirection: 'row', gap: 12, alignItems: 'flex-start', marginBottom: 4 },
  icon: { backgroundColor: C.green50, padding: 10, borderRadius: R.md },
  name: { flex: 1, flexShrink: 1, fontSize: 22, lineHeight: 32, fontWeight: '600', color: C.ink1 },
  detailRow: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 16, rowGap: 4 },
  detailLabel: { fontSize: 15, color: C.ink2, minWidth: 68 },
  detailValue: { flexGrow: 1, flexShrink: 1, fontSize: 16, color: C.ink1, fontWeight: '500' },
  source: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line, paddingTop: 14, color: C.ink2, fontSize: 12 },
  notice: { borderRadius: R.lg, padding: 18, backgroundColor: C.paper2, gap: 8 },
  noticeTitle: { fontSize: 16, fontWeight: '600', color: C.ink1 }, body: { fontSize: 15, lineHeight: 24, color: C.ink2 },
  actions: { gap: 10 },
  slot: { minHeight: 44, minWidth: 72, padding: 12, borderRadius: R.md, backgroundColor: C.green50, alignItems: 'center', justifyContent: 'center' },
  primary: { backgroundColor: C.green600, minHeight: 56, padding: 16, borderRadius: R.lg, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 },
  primaryText: { color: C.greenOn, fontSize: 17, fontWeight: '600', flexShrink: 1, textAlign: 'center' },
  secondaryButton: { minHeight: 52, padding: 14, borderWidth: 1, borderColor: C.lineStrong, borderRadius: R.lg, alignItems: 'center', justifyContent: 'center' },
  secondaryButtonText: { color: C.ink2, fontSize: 16, textAlign: 'center' }, disabled: { opacity: 0.5 },
  footnote: { color: C.ink2, fontSize: 12, lineHeight: 20, textAlign: 'center', marginTop: 4 },
  manage: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
  manageText: { color: C.green700, fontSize: 14 },
  loading: { minHeight: 180, justifyContent: 'center', alignItems: 'center', gap: 12 },
  secondary: { color: C.ink2, fontSize: 15 }, message: { color: C.green700, fontSize: 15, lineHeight: 23 },
});
