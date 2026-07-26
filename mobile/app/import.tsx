/**
 * 统一导入页 /import (Iter 1 Day 3-4)
 *
 * 入口:
 *   - Home 顶部"导入"按钮
 *
 * 流程:
 *   1. 用户点 "选择文件" → DocumentPicker → 按扩展名分发:
 *        .txt           → 基因 raw_data  → POST /genetic/profiles/upload-txt
 *        .pdf (基因报告) → POST /genetic/profiles/upload-pdf
 *        .pdf (体检报告) → POST /medical-exams/import/pdf
 *        .jpg/.png      → POST /medical-exams/import/image
 *      让用户手动选"基因/体检"类型 (.pdf 歧义, 无法靠扩展名猜)
 *   2. 用户点 "拍照" → ImagePicker camera → /medical-exams/import/image
 *   3. 成功: 回显关键数字 (指标数 / 异常数) + 关闭
 *   4. 失败: 弹提示 + 降级路径 (暂时只是提示, v2 加 TextArea fallback)
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextStyle,
  Alert, ActivityIndicator, KeyboardAvoidingView, Platform,
  Modal, TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { uploadMedicalExamPdf, uploadMedicalExamImage, uploadMedicalExamText } from '../services/medicalExams';
import { uploadGeneticTxt, uploadGeneticPdf, pollGeneticProfileStatus } from '../services/geneticData';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createImportResultAgentContext } from '../utils/agentContext';
import { geneticImportStatusView, isTerminalGeneticImportStatus } from '../utils/geneticImportStatus';
import { todayStr } from '../utils/dietDate';

type FileKind = 'genetic_txt' | 'genetic_pdf' | 'medical_pdf' | 'medical_image';

interface UploadResult {
  kind: FileKind;
  message: string;
  detail?: string;
}

export default function ImportScreen() {
  const params = useLocalSearchParams<{ focus?: string }>();
  const isMedicalFocused = params.focus === 'medical';
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const [busy, setBusy] = useState(false);
  const [busyHint, setBusyHint] = useState<string>('AI 正在解析, 请稍候 (10-60 秒)...');
  const [result, setResult] = useState<UploadResult | null>(null);
  const [fallbackOpen, setFallbackOpen] = useState(false);
  const [fallbackText, setFallbackText] = useState('');

  const onPickFile = async () => {
    if (busy) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'text/plain', 'text/*', '*/*'],
        copyToCacheDirectory: true,
      });
      if (picked.canceled || !picked.assets?.[0]) return;
      const asset = picked.assets[0];
      const name = (asset.name || 'file').toLowerCase();
      const ext = name.includes('.') ? name.split('.').pop()! : '';

      if (ext === 'txt') {
        await runUpload('genetic_txt', () => uploadGeneticTxt(asset.uri, { notes: `mobile 上传: ${asset.name}` }));
        return;
      }

      if (ext === 'pdf') {
        if (isMedicalFocused) {
          await runUpload('medical_pdf', () =>
            uploadMedicalExamPdf(asset.uri, asset.name || 'exam.pdf'));
          return;
        }

        // PDF 歧义 — 让用户选 基因 / 体检
        Alert.alert(
          '这份 PDF 是什么报告?',
          '基因检测报告 vs 体检/化验报告 — 解析流程不同.',
          [
            { text: '取消', style: 'cancel' },
            {
              text: '基因检测',
              onPress: () => runUpload('genetic_pdf', () =>
                uploadGeneticPdf(asset.uri, { notes: `mobile 上传: ${asset.name}` })),
            },
            {
              text: '体检/化验',
              onPress: () => runUpload('medical_pdf', () =>
                uploadMedicalExamPdf(asset.uri, asset.name || 'exam.pdf')),
            },
          ],
        );
        return;
      }

      if (['jpg', 'jpeg', 'png', 'heic', 'webp'].includes(ext)) {
        const mime = asset.mimeType || (ext === 'png' ? 'image/png' : 'image/jpeg');
        await runUpload('medical_image', () =>
          uploadMedicalExamImage(asset.uri, asset.name || 'exam.jpg', mime));
        return;
      }

      Alert.alert('不支持的文件类型', `.${ext} 暂不支持. 目前支持 .txt (基因) / .pdf (基因或体检) / .jpg/.png (化验单照片).`);
    } catch (e: any) {
      Alert.alert('选择文件失败', e?.message || '请稍后再试');
    }
  };

  const onTakePhoto = async () => {
    if (busy) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相机权限', '在"设置 → 小巴"中开启相机权限,才能拍摄化验单.');
        return;
      }
      const picked = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        quality: 0.85,
        allowsEditing: false,
      });
      if (picked.canceled || !picked.assets?.[0]) return;
      const asset = picked.assets[0];
      await runUpload('medical_image', () =>
        uploadMedicalExamImage(asset.uri, asset.fileName || 'photo.jpg', asset.mimeType || 'image/jpeg'));
    } catch (e: any) {
      Alert.alert('拍照失败', e?.message || '请稍后再试');
    }
  };

  const onPickFromLibrary = async () => {
    if (busy) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('需要相册权限', '在"设置 → 小巴"中开启"照片"权限,才能选取化验单图片.');
        return;
      }
      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.85,
        allowsEditing: false,
        // 允许 HEIC/PNG/JPEG,后端都支持
      });
      if (picked.canceled || !picked.assets?.[0]) return;
      const asset = picked.assets[0];
      const mime = asset.mimeType || 'image/jpeg';
      await runUpload('medical_image', () =>
        uploadMedicalExamImage(asset.uri, asset.fileName || 'photo.jpg', mime));
    } catch (e: any) {
      Alert.alert('选图失败', e?.message || '请稍后再试');
    }
  };

  async function runUpload<T>(kind: FileKind, fn: () => Promise<T>) {
    setBusy(true);
    setBusyHint(kind === 'genetic_pdf'
      ? '基因 PDF 已上传, AI 后台解析中, 最长 1-3 分钟...'
      : 'AI 正在解析, 请稍候 (10-60 秒)...');
    setResult(null);
    try {
      const data: any = await fn();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      let message = '';
      let detail = '';
      if (kind === 'genetic_txt') {
        const view = geneticImportStatusView({
          id: data.id,
          status: 'done',
          variant_count: data.matched_count ?? 0,
          import_job: data.import_job,
          coverage: data.coverage,
        });
        message = view.detail;
        detail = view.coverageLine || data.message || '';
      } else if (kind === 'genetic_pdf') {
        // PDF 异步 — 立刻回一个 "上传成功" 再轮询真实结果
        const profileId = data.id;
        setBusyHint(`档案 #${profileId} 上传成功, 正在轮询解析进度...`);
        const final = await pollGeneticProfileStatus(profileId, {
          onTick: (s) => {
            const view = geneticImportStatusView(s);
            setBusyHint(`${view.label}: ${view.detail}${view.coverageLine ? '\n' + view.coverageLine : ''}`);
          },
        });
        const view = geneticImportStatusView(final);
        if (view.phase === 'complete') {
          message = view.detail;
          detail = view.coverageLine || final.notes || '';
        } else if (view.phase === 'failed') {
          throw new Error(view.detail);
        } else {
          message = `${view.label}: ${view.detail}`;
          detail = view.coverageLine || '稍后在"基因档案"里可以查看最终结果.';
        }
        if (!isTerminalGeneticImportStatus(view)) {
          detail = `${detail}\n稍后在"基因档案"里可以查看最终结果.`;
        }
      } else if (kind === 'medical_pdf') {
        message = `体检报告解析成功: ${data.itemsCount ?? data.items_count ?? 0} 个指标`;
        const source = data.hospitalName ?? data.hospital_name;
        detail = `${source ? `来源: ${source}\n` : ''}请复核 OCR/AI 解析结果后再用于判断。`;
      } else if (kind === 'medical_image') {
        const abnormal = data.abnormalCount ?? data.abnormal_count ?? 0;
        message = `化验单识别完成: ${data.itemsCount ?? data.items_count ?? 0} 项` + (abnormal > 0 ? `, ${abnormal} 项异常` : '');
        detail = `${data.conclusion ? `${data.conclusion}\n` : ''}请复核 OCR/AI 解析结果后再用于判断。`;
      }
      setResult({ kind, message, detail });
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const status = e?.response?.status;
      const serverMsg = e?.response?.data?.detail || e?.message || '未知错误';
      let hint = '';
      let showFallback = false;

      if (status === 413) {
        hint = '文件过大 — 请压缩到 10MB (图片) / 20MB (PDF) 以内再试.';
      } else if (status === 422 || status === 400) {
        showFallback = true;
        hint = 'AI 未能识别出结构化数据 — 可以尝试手工贴文字, 让 AI 抽取指标.';
      } else {
        hint = '请稍后再试';
      }

      if (showFallback) {
        setFallbackOpen(true);
      } else {
        Alert.alert('上传失败', `${serverMsg}${hint ? '\n\n' + hint : ''}`);
      }
    } finally {
      setBusy(false);
    }
  }

  const onFallbackSubmit = async () => {
    const text = fallbackText.trim();
    if (!text) {
      Alert.alert('请输入内容', '至少输入一点文字, 比如 "血压 130/85".');
      return;
    }
    setFallbackOpen(false);
    setBusy(true);
    setBusyHint('AI 正在从文字中抽取健康指标...');
    try {
      const data = await uploadMedicalExamText(text, {
        exam_date: todayStr(),
        hospital_name: '手工贴文字',
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      const count = data.items_count ?? 0;
      const message = count > 0 ? `从文字中导入 ${count} 项指标` : '未能识别出指标';
      const detail = data.exam_id ? `已写入化验记录 #${data.exam_id}` : '';
      setResult({ kind: 'medical_image', message, detail });
    } catch (e: any) {
      Alert.alert('文字解析失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={{ padding: 6 }}>
          <Ionicons name="close" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>{isMedicalFocused ? '导入体检报告' : '导入健康档案'}</Text>
        <View style={{ width: 32 }} />
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={txt.lead}>
            {isMedicalFocused
              ? '上传体检报告 PDF、化验单照片，或粘贴文字结果。导入后会进入体检记录，先复核再用于判断。'
              : '上传基因或体检报告, AI 帮你解读并放进健康档案.'}
          </Text>

          <TouchableOpacity
            style={[styles.cta, busy && { opacity: 0.5 }]}
            onPress={onPickFile}
            disabled={busy}
            activeOpacity={0.8}
          >
            <View style={styles.ctaIcon}>
              <Ionicons name="document-outline" size={28} color={c.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.ctaTitle}>选择文件</Text>
              <Text style={txt.ctaSub}>
                {isMedicalFocused
                  ? '.pdf (体检报告) / .jpg .png .heic (化验单照片)'
                  : '.txt (基因 raw data) / .pdf (基因或体检报告) / .jpg (化验单照片)'}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={c.labelTertiary} />
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.cta, busy && { opacity: 0.5 }]}
            onPress={onTakePhoto}
            disabled={busy}
            activeOpacity={0.8}
          >
            <View style={styles.ctaIcon}>
              <Ionicons name="camera-outline" size={28} color={c.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.ctaTitle}>拍化验单</Text>
              <Text style={txt.ctaSub}>对准报告拍一张, AI 自动识别指标和异常项</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={c.labelTertiary} />
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.cta, busy && { opacity: 0.5 }]}
            onPress={onPickFromLibrary}
            disabled={busy}
            activeOpacity={0.8}
          >
            <View style={styles.ctaIcon}>
              <Ionicons name="images-outline" size={28} color={c.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={txt.ctaTitle}>从相册选图片</Text>
              <Text style={txt.ctaSub}>已存在手机里的化验单 / 体检单照片 (.jpg/.png/.heic)</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={c.labelTertiary} />
          </TouchableOpacity>

          {busy && (
            <View style={styles.busyBox}>
              <ActivityIndicator size="small" color={c.brand} />
              <Text style={txt.busyText}>{busyHint}</Text>
            </View>
          )}

          {result && !busy && (
            <View style={styles.resultBox}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="checkmark-circle" size={22} color={c.green} />
                <Text style={txt.resultTitle}>{result.message}</Text>
              </View>
              {!!result.detail && <Text style={txt.resultDetail}>{result.detail}</Text>}
              <AgentFeedbackLink
                label="跟小巴解读这次导入"
                accessibilityLabel="跟小巴解读这次导入"
                prompt="请基于我刚导入的健康档案结果，解释这次导入意味着什么、下一步该查看或补录什么，并给出后续健康管理行动建议。"
                context={createImportResultAgentContext({ kind: result.kind, result })}
                badge="导入结果"
              />
              {(result.kind === 'medical_pdf' || result.kind === 'medical_image') && (
                <TouchableOpacity
                  onPress={() => router.replace('/medical-exams' as any)}
                  style={styles.reviewBtn}
                  activeOpacity={0.8}
                  accessibilityRole="button"
                  accessibilityLabel="查看体检记录"
                >
                  <Ionicons name="document-text-outline" size={16} color={c.brand} />
                  <Text style={txt.reviewBtn}>查看体检记录并复核</Text>
                  <Ionicons name="chevron-forward" size={15} color={c.brand} />
                </TouchableOpacity>
              )}
              <TouchableOpacity
                onPress={() => router.back()}
                style={styles.doneBtn}
                activeOpacity={0.8}
              >
                <Text style={txt.doneBtn}>完成</Text>
              </TouchableOpacity>
            </View>
          )}

          <View style={styles.tipsBox}>
            <Text style={txt.tipsTitle}>支持的格式</Text>
            {!isMedicalFocused && (
              <>
                <Text style={txt.tipsItem}>• 基因: 23andMe / 微基因 raw data (.txt)</Text>
                <Text style={txt.tipsItem}>• 基因: 基因检测报告 (.pdf, 后台异步解析)</Text>
              </>
            )}
            <Text style={txt.tipsItem}>• 体检: 三甲医院体检报告 (.pdf)</Text>
            <Text style={txt.tipsItem}>• 化验: 单项化验单照片 (.jpg/.png)</Text>
            <Text style={[txt.tipsItem, { marginTop: spacing.sm, color: c.labelTertiary }]}>
              隐私: 文件仅用于解析, 解析后不保留原文件.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>

      <Modal
        visible={fallbackOpen}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setFallbackOpen(false)}
      >
        <SafeAreaView style={styles.safe} edges={['top']}>
          <View style={styles.header}>
            <TouchableOpacity onPress={() => setFallbackOpen(false)} hitSlop={10} style={{ padding: 6 }}>
              <Ionicons name="close" size={26} color={c.labelPrimary} />
            </TouchableOpacity>
            <Text style={txt.title}>手工贴文字</Text>
            <TouchableOpacity onPress={onFallbackSubmit} hitSlop={10} style={{ padding: 6 }}>
              <Text style={txt.saveBtn}>解析</Text>
            </TouchableOpacity>
          </View>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={{ flex: 1 }}
          >
            <ScrollView contentContainerStyle={styles.scroll}>
              <Text style={txt.lead}>
                AI 没识别成功? 把化验单 / 体检结果文字粘贴进来 (或者手打), AI 会从中抽取指标.
              </Text>
              <TextInput
                style={styles.fallbackInput}
                value={fallbackText}
                onChangeText={setFallbackText}
                placeholder={'例如:\n血压 130/85\nLDL 3.8\nHbA1c 5.7%\nALT 42 U/L'}
                placeholderTextColor={c.labelTertiary}
                multiline
                autoFocus
                maxLength={4000}
              />
              <Text style={[txt.tipsItem, { color: c.labelTertiary, marginTop: spacing.md }]}>
                提示: 一行一项, 包含数值 + 单位 (如 "LDL 3.8 mmol/L") 准确率最高.
              </Text>
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
      borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
    },
    scroll: { padding: spacing.lg, paddingBottom: 60 },
    cta: {
      flexDirection: 'row', alignItems: 'center', gap: spacing.md,
      backgroundColor: c.bgCard, borderRadius: radii.lg, padding: spacing.lg,
      marginTop: spacing.md, ...shadows.subtle,
    },
    ctaIcon: {
      width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandLight,
      alignItems: 'center', justifyContent: 'center',
    },
    busyBox: {
      flexDirection: 'row', alignItems: 'center', gap: spacing.md,
      marginTop: spacing.lg, padding: spacing.lg,
      backgroundColor: c.bgCard, borderRadius: radii.md,
    },
    resultBox: {
      marginTop: spacing.lg, padding: spacing.lg,
      backgroundColor: c.bgCard, borderRadius: radii.md,
      borderWidth: 1, borderColor: c.green + '33',
      gap: spacing.sm,
    },
    doneBtn: {
      marginTop: spacing.sm, paddingVertical: 12,
      backgroundColor: c.brand, borderRadius: radii.md, alignItems: 'center',
    },
    reviewBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      gap: 8, marginTop: spacing.xs, paddingVertical: 12,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.brand,
      borderRadius: radii.md, backgroundColor: c.brandLight,
    },
    tipsBox: {
      marginTop: spacing.xl * 1.2, padding: spacing.lg,
      backgroundColor: c.bgCard, borderRadius: radii.md,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
    },
    fallbackInput: {
      marginTop: spacing.md, padding: spacing.md,
      backgroundColor: c.bgCard, borderRadius: radii.md,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
      color: c.labelPrimary, fontSize: 15, minHeight: 240,
      textAlignVertical: 'top',
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    saveBtn: { fontSize: 16, fontWeight: '600', color: c.brand } as TextStyle,
    lead: { fontSize: 14, color: c.labelSecondary, lineHeight: 20, marginBottom: spacing.sm } as TextStyle,
    ctaTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, marginBottom: 2 } as TextStyle,
    ctaSub: { fontSize: 12, color: c.labelTertiary, lineHeight: 17 } as TextStyle,
    busyText: { fontSize: 14, color: c.labelSecondary } as TextStyle,
    resultTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    resultDetail: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
    doneBtn: { fontSize: 15, fontWeight: '600', color: '#fff' } as TextStyle,
    reviewBtn: { fontSize: 14, fontWeight: '600', color: c.brand } as TextStyle,
    tipsTitle: { fontSize: 13, fontWeight: '600', color: c.labelSecondary, marginBottom: spacing.sm } as TextStyle,
    tipsItem: { fontSize: 13, color: c.labelSecondary, lineHeight: 20 } as TextStyle,
  };
}
