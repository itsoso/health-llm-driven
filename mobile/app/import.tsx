/**
 * 统一导入页 /import (Iter 1 Day 3-4)
 *
 * 入口:
 *   - Home 顶部"导入"按钮
 *
 * 流程:
 *   1. 用户点 "选择文件" → DocumentPicker → 按扩展名分发:
 *        .txt           → 基因 raw_data  → POST /genetic-data/profiles/upload-txt
 *        .pdf (基因报告) → POST /genetic-data/profiles/upload-pdf
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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';
import { uploadMedicalExamPdf, uploadMedicalExamImage } from '../services/medicalExams';
import { uploadGeneticTxt, uploadGeneticPdf } from '../services/geneticData';

type FileKind = 'genetic_txt' | 'genetic_pdf' | 'medical_pdf' | 'medical_image';

interface UploadResult {
  kind: FileKind;
  message: string;
  detail?: string;
}

export default function ImportScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);

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
        Alert.alert('需要相机权限', '在"设置 → 健康助理"中开启相机权限,才能拍摄化验单.');
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

  async function runUpload<T>(kind: FileKind, fn: () => Promise<T>) {
    setBusy(true);
    setResult(null);
    try {
      const data: any = await fn();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);

      let message = '';
      let detail = '';
      if (kind === 'genetic_txt') {
        message = `成功匹配 ${data.matched_count ?? 0} 个健康相关基因位点`;
        detail = data.message || '';
      } else if (kind === 'genetic_pdf') {
        message = 'PDF 已上传, AI 正在后台解析基因位点...';
        detail = '解析需 1-2 分钟, 完成后在"基因档案"里可以查看.';
      } else if (kind === 'medical_pdf') {
        message = `体检报告解析成功: ${data.items_count ?? 0} 个指标`;
        detail = data.hospital_name ? `来源: ${data.hospital_name}` : '';
      } else if (kind === 'medical_image') {
        const abnormal = data.abnormal_count ?? 0;
        message = `化验单识别完成: ${data.items_count ?? 0} 项` + (abnormal > 0 ? `, ${abnormal} 项异常` : '');
        detail = data.conclusion || '';
      }
      setResult({ kind, message, detail });
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      const status = e?.response?.status;
      const serverMsg = e?.response?.data?.detail || e?.message || '未知错误';
      let hint = '';
      if (status === 413) hint = '文件过大 — 请压缩到 10MB (图片) / 20MB (PDF) 以内再试.';
      else if (status === 422) hint = 'AI 未能识别出结构化数据 — 换一张更清晰的图, 或上传 PDF 原件.';
      else if (status === 400) hint = '文件格式不对 — 请检查扩展名.';
      Alert.alert('上传失败', `${serverMsg}${hint ? '\n\n' + hint : ''}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={{ padding: 6 }}>
          <Ionicons name="close" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>导入健康档案</Text>
        <View style={{ width: 32 }} />
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <Text style={txt.lead}>上传基因或体检报告, AI 帮你解读并放进健康档案.</Text>

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
              <Text style={txt.ctaSub}>.txt (基因 raw data) / .pdf (基因或体检报告) / .jpg (化验单照片)</Text>
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

          {busy && (
            <View style={styles.busyBox}>
              <ActivityIndicator size="small" color={c.brand} />
              <Text style={txt.busyText}>AI 正在解析, 请稍候 (10-60 秒)...</Text>
            </View>
          )}

          {result && !busy && (
            <View style={styles.resultBox}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="checkmark-circle" size={22} color={c.green} />
                <Text style={txt.resultTitle}>{result.message}</Text>
              </View>
              {!!result.detail && <Text style={txt.resultDetail}>{result.detail}</Text>}
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
            <Text style={txt.tipsItem}>• 基因: 23andMe / 微基因 raw data (.txt)</Text>
            <Text style={txt.tipsItem}>• 基因: 基因检测报告 (.pdf, 后台异步解析)</Text>
            <Text style={txt.tipsItem}>• 体检: 三甲医院体检报告 (.pdf)</Text>
            <Text style={txt.tipsItem}>• 化验: 单项化验单照片 (.jpg/.png)</Text>
            <Text style={[txt.tipsItem, { marginTop: spacing.sm, color: c.labelTertiary }]}>
              隐私: 文件仅用于解析, 解析后不保留原文件.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
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
    tipsBox: {
      marginTop: spacing.xl * 1.2, padding: spacing.lg,
      backgroundColor: c.bgCard, borderRadius: radii.md,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    lead: { fontSize: 14, color: c.labelSecondary, lineHeight: 20, marginBottom: spacing.sm } as TextStyle,
    ctaTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, marginBottom: 2 } as TextStyle,
    ctaSub: { fontSize: 12, color: c.labelTertiary, lineHeight: 17 } as TextStyle,
    busyText: { fontSize: 14, color: c.labelSecondary } as TextStyle,
    resultTitle: { fontSize: 15, fontWeight: '600', color: c.labelPrimary, flex: 1 } as TextStyle,
    resultDetail: { fontSize: 13, color: c.labelSecondary, lineHeight: 19 } as TextStyle,
    doneBtn: { fontSize: 15, fontWeight: '600', color: '#fff' } as TextStyle,
    tipsTitle: { fontSize: 13, fontWeight: '600', color: c.labelSecondary, marginBottom: spacing.sm } as TextStyle,
    tipsItem: { fontSize: 13, color: c.labelSecondary, lineHeight: 20 } as TextStyle,
  };
}
