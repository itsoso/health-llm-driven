/**
 * 症状录入 sheet (全屏 modal, 项目惯例)
 *
 * 入口:
 *   - Home 顶部"记症状"图标
 *   - Record tab 的 SymptomCard "+ 记症状" 按钮
 *   - 或 voice-chat ?intent=journal (绕过本页, LLM 自动调 health_record tool)
 *
 * 流程: 选部位 + (选)描述 + (选)严重度 → 保存. 或点麦克风跳 voice-chat journal.
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, ScrollView,
  TextStyle, Alert, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { BODY_PARTS, BodyPart, createSymptom } from '../services/symptoms';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../constants/revaTheme';
import { emitClientEvent } from '../services/clientEvents';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createSymptomAgentContext } from '../utils/agentContext';
import { todayStr } from '../utils/dietDate';

const SEVERITY_LEVELS = [
  { value: 1, label: '轻微' },
  { value: 3, label: '偏轻' },
  { value: 5, label: '中等' },
  { value: 7, label: '偏重' },
  { value: 9, label: '很重' },
];

export default function SymptomRecordScreen() {
  const [bodyPart, setBodyPart] = useState<BodyPart | null>(null);
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const canSave = bodyPart !== null && description.trim().length > 0;
  const today = todayStr();

  const onSave = async () => {
    if (!canSave || saving) return;
    setSaving(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      await createSymptom({
        body_part: bodyPart!,
        description: description.trim(),
        severity: severity ?? undefined,
        source: 'manual',
      });
      emitClientEvent('quick_record_logged', { kind: 'symptom', body_part: bodyPart, severity, source: 'manual' });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.back();
    } catch (e: any) {
      Alert.alert('保存失败', e?.message || '请稍后再试');
    } finally {
      setSaving(false);
    }
  };

  const goVoice = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    // 跳 voice-chat journal 模式, 让 LLM 自动抽字段 + 调 health_record(symptom)
    router.replace('/voice-chat?intent=journal');
  };

  const onVoice = () => {
    // router.replace 会丢掉本页已填内容; 填了再切语音先确认.
    if (bodyPart !== null || description.trim().length > 0) {
      Alert.alert('切换到语音记录?', '当前已填写的内容不会保留。', [
        { text: '取消', style: 'cancel' },
        { text: '切换', style: 'destructive', onPress: goVoice },
      ]);
      return;
    }
    goVoice();
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={{ padding: 6 }}>
          <Ionicons name="close" size={26} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>记症状</Text>
        <TouchableOpacity
          onPress={onVoice}
          hitSlop={10}
          style={{ padding: 6 }}
          accessibilityLabel="语音记录"
        >
          <Ionicons name="mic-outline" size={24} color={C.green500} />
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={txt.sectionTitle}>哪里不舒服?</Text>
          <View style={styles.grid}>
            {BODY_PARTS.map(p => {
              const selected = bodyPart === p.value;
              return (
                <TouchableOpacity
                  key={p.value}
                  style={[styles.partChip, selected && { borderColor: C.green500, backgroundColor: C.green50 }]}
                  onPress={() => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    setBodyPart(p.value);
                  }}
                  activeOpacity={0.7}
                >
                  <Text style={{ fontSize: 22 }}>{p.emoji}</Text>
                  <Text style={[txt.partLabel, selected && { color: C.green500, fontWeight: '600' }]}>{p.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={[txt.sectionTitle, { marginTop: revaSpacing.s5 }]}>具体描述</Text>
          <TextInput
            style={styles.input}
            value={description}
            onChangeText={setDescription}
            placeholder="如:眼睛痒 / 右膝钝痛 / 嗓子有痰"
            placeholderTextColor={C.ink3}
            multiline
            maxLength={200}
          />

          <Text style={[txt.sectionTitle, { marginTop: revaSpacing.s5 }]}>严重度(可选)</Text>
          <View style={styles.severityRow}>
            {SEVERITY_LEVELS.map(s => {
              const selected = severity === s.value;
              return (
                <TouchableOpacity
                  key={s.value}
                  style={[styles.sevChip, selected && { backgroundColor: C.green500, borderColor: C.green500 }]}
                  onPress={() => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                    setSeverity(selected ? null : s.value);
                  }}
                >
                  <Text style={[txt.sevLabel, selected && { color: '#fff', fontWeight: '700' }]}>{s.label}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <AgentFeedbackLink
            label="跟小巴复盘这个症状"
            accessibilityLabel="跟小巴复盘这个症状"
            prompt="请基于我正在记录的症状, 帮我复盘可能诱因、需要补充的问题、居家观察和记录建议，并明确哪些情况需要尽快就医。不要给出确定诊断。"
            context={createSymptomAgentContext({
              date: today,
              bodyPart,
              description,
              severity,
              source: 'manual',
            })}
            badge="症状记录"
            style={styles.agentLink}
          />

          <TouchableOpacity
            style={[styles.saveCta, (!canSave || saving) && styles.saveCtaDisabled]}
            onPress={onSave}
            disabled={!canSave || saving}
            activeOpacity={0.8}
          >
            {saving
              ? <ActivityIndicator size="small" color="#fff" />
              : <>
                  <Ionicons name="checkmark" size={22} color="#fff" />
                  <Text style={txt.saveCtaText}>保存</Text>
                </>}
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / r-md / 描述文字走 sans。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: revaSpacing.s4, paddingVertical: revaSpacing.s3,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line,
  },
  scroll: { padding: revaSpacing.s4, paddingBottom: 60 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s2, marginTop: revaSpacing.s3 },
  partChip: {
    width: '23%', aspectRatio: 1, alignItems: 'center', justifyContent: 'center',
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    borderWidth: 1.5, borderColor: C.line, gap: 4,
  },
  input: {
    marginTop: revaSpacing.s3, padding: revaSpacing.s3,
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line,
    color: C.ink1, fontSize: 15, fontFamily: revaFonts.sans, minHeight: 80,
    textAlignVertical: 'top',
  },
  severityRow: {
    flexDirection: 'row', gap: revaSpacing.s2, marginTop: revaSpacing.s3,
  },
  sevChip: {
    flex: 1, paddingVertical: 12, borderRadius: revaRadii.md,
    borderWidth: 1.5, borderColor: C.line,
    alignItems: 'center', backgroundColor: C.surface,
  },
  saveCta: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginTop: revaSpacing.s5 * 1.5, paddingVertical: 16,
    backgroundColor: C.green500, borderRadius: revaRadii.md, ...revaShadows.sm,
  },
  saveCtaDisabled: { backgroundColor: C.ink4, shadowOpacity: 0 },
  agentLink: { marginTop: revaSpacing.s5 },
});

// 文字走 Manrope/ink(本页无密集数字)。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1 } as TextStyle,
  sectionTitle: { fontFamily: revaFonts.sans, fontSize: 15, fontWeight: '600', color: C.ink1 } as TextStyle,
  partLabel: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, textAlign: 'center' } as TextStyle,
  sevLabel: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1 } as TextStyle,
  saveCtaText: { fontFamily: revaFonts.sans, fontSize: 16, color: '#fff', fontWeight: '700' } as TextStyle,
};
