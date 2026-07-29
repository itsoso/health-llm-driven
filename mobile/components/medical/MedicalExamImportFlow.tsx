import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import {
  confirmMedicalExamPreview,
  previewMedicalExamAsset,
  type MedicalExamImportAsset,
  type MedicalExamImportResult,
  type MedicalExamPreview,
} from '../../services/medicalExams';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';

type FlowStatus = 'choose' | 'previewing' | 'review' | 'saving' | 'success' | 'error';

interface Props {
  visible?: boolean;
  presentation?: 'modal' | 'screen';
  onClose: () => void;
  onImported: (result: MedicalExamImportResult) => void;
}

function errorMessage(error: any): string {
  return String(
    error?.response?.data?.detail
      ?? error?.message
      ?? '暂时无法解析这份报告，请稍后重试。',
  );
}

function newConfirmationKey(): string {
  return `medical-confirm-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function abnormalCount(preview: MedicalExamPreview): number {
  return preview.items.filter(item => {
    const status = String(item.is_abnormal ?? '').toLowerCase();
    return status !== '' && status !== 'normal';
  }).length;
}

export default function MedicalExamImportFlow({
  visible = true,
  presentation = 'modal',
  onClose,
  onImported,
}: Props) {
  const [status, setStatus] = useState<FlowStatus>('choose');
  const [asset, setAsset] = useState<MedicalExamImportAsset | null>(null);
  const [preview, setPreview] = useState<MedicalExamPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirmationKeyRef = useRef(newConfirmationKey());

  const reset = useCallback(() => {
    setStatus('choose');
    setAsset(null);
    setPreview(null);
    setError(null);
    confirmationKeyRef.current = newConfirmationKey();
  }, []);

  useEffect(() => {
    if (!visible) reset();
  }, [reset, visible]);

  const close = useCallback(() => {
    reset();
    onClose();
  }, [onClose, reset]);

  const parseAsset = useCallback(async (nextAsset: MedicalExamImportAsset) => {
    setAsset(nextAsset);
    setPreview(null);
    setError(null);
    setStatus('previewing');
    confirmationKeyRef.current = newConfirmationKey();
    try {
      const result = await previewMedicalExamAsset(nextAsset);
      setPreview(result);
      setStatus('review');
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    } catch (cause) {
      setError(errorMessage(cause));
      setStatus('error');
    }
  }, []);

  const pickDocument = useCallback(async () => {
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'image/*'],
        copyToCacheDirectory: true,
      });
      const selected = !picked.canceled ? picked.assets?.[0] : null;
      if (selected) {
        await parseAsset({
          uri: selected.uri,
          name: selected.name,
          mimeType: selected.mimeType,
        });
      }
    } catch (cause) {
      setError(errorMessage(cause));
      setStatus('error');
    }
  }, [parseAsset]);

  const takePhoto = useCallback(async () => {
    try {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted) {
        setError('需要相机权限。请在系统设置中允许小巴使用相机后重试。');
        setStatus('error');
        return;
      }
      const picked = await ImagePicker.launchCameraAsync({
        mediaTypes: ['images'],
        quality: 0.9,
        allowsEditing: false,
      });
      const selected = !picked.canceled ? picked.assets?.[0] : null;
      if (selected) {
        await parseAsset({
          uri: selected.uri,
          name: selected.fileName || 'medical-exam-photo.jpg',
          mimeType: selected.mimeType || 'image/jpeg',
        });
      }
    } catch (cause) {
      setError(errorMessage(cause));
      setStatus('error');
    }
  }, [parseAsset]);

  const pickLibrary = useCallback(async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        setError('需要照片权限。请在系统设置中允许小巴访问照片后重试。');
        setStatus('error');
        return;
      }
      const picked = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.9,
        allowsEditing: false,
      });
      const selected = !picked.canceled ? picked.assets?.[0] : null;
      if (selected) {
        await parseAsset({
          uri: selected.uri,
          name: selected.fileName || 'medical-exam-image.jpg',
          mimeType: selected.mimeType || 'image/jpeg',
        });
      }
    } catch (cause) {
      setError(errorMessage(cause));
      setStatus('error');
    }
  }, [parseAsset]);

  const retryPreview = useCallback(() => {
    if (asset) void parseAsset(asset);
  }, [asset, parseAsset]);

  const confirm = useCallback(async () => {
    if (!preview || status === 'saving') return;
    setError(null);
    setStatus('saving');
    try {
      const result = await confirmMedicalExamPreview(
        preview,
        confirmationKeyRef.current,
      );
      setStatus('success');
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      onImported(result);
    } catch (cause) {
      setError(errorMessage(cause));
      setStatus('review');
    }
  }, [onImported, preview, status]);

  const title = status === 'review' || status === 'saving'
    ? '核对报告'
    : status === 'success'
      ? '导入完成'
      : '导入体检报告';

  const body = (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={close}
          style={styles.iconButton}
          accessibilityRole="button"
          accessibilityLabel="关闭导入体检报告"
        >
          <Ionicons name="close" size={22} color={C.ink2} />
        </TouchableOpacity>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.step}>
            {status === 'review' || status === 'saving' ? '第 2 步，共 2 步' : '先解析预览，再确认保存'}
          </Text>
        </View>
        <View style={styles.headerSpacer} />
      </View>

      {(status === 'choose' || (status === 'error' && !asset)) && (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.intro}>
            <View style={styles.introIcon}>
              <Ionicons name="document-text-outline" size={24} color={C.green500} />
            </View>
            <Text style={styles.introTitle}>选择一份报告</Text>
            <Text style={styles.introBody}>
              支持体检 PDF 和化验单照片。系统会先提取日期、机构和指标，核对后才写入健康档案。
            </Text>
          </View>
          {!!error && <InlineError message={error} />}
          <SourceRow
            icon="document-outline"
            title="选择报告文件"
            subtitle="PDF、JPG、PNG、HEIC 或 WebP"
            onPress={pickDocument}
          />
          <SourceRow
            icon="camera-outline"
            title="拍摄报告"
            subtitle="保持页面完整、文字清晰、避免反光"
            onPress={takePhoto}
          />
          <SourceRow
            icon="images-outline"
            title="从相册选择"
            subtitle="选择已有的体检报告或化验单照片"
            onPress={pickLibrary}
          />
          <Text style={styles.privacy}>
            原文件仅用于本次解析，不作为公开内容。AI 识别可能有误，保存前请核对。
          </Text>
        </ScrollView>
      )}

      {status === 'previewing' && (
        <View style={styles.centerState}>
          <ActivityIndicator color={C.green500} size="large" />
          <Text style={styles.stateTitle}>正在整理报告</Text>
          <Text style={styles.stateBody}>{asset?.name || '体检报告'}</Text>
          <Text style={styles.stateHint}>通常需要 10–60 秒，请保持页面打开</Text>
        </View>
      )}

      {status === 'error' && asset && (
        <View style={styles.errorState}>
          <View style={styles.fileLine}>
            <Ionicons name="document-outline" size={20} color={C.ink2} />
            <Text numberOfLines={2} style={styles.fileName}>{asset.name || '体检报告'}</Text>
          </View>
          <InlineError message={error || '暂时无法解析这份报告'} />
          <View style={styles.errorActions}>
            <TouchableOpacity style={styles.primaryButton} onPress={retryPreview}>
              <Text style={styles.primaryButtonText}>重新解析</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryButton} onPress={reset}>
              <Text style={styles.secondaryButtonText}>更换报告</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {(status === 'review' || status === 'saving') && preview && (
        <>
          <ScrollView contentContainerStyle={styles.reviewContent}>
            <View style={styles.reportSummary}>
              <Text style={styles.reportName} numberOfLines={2}>{preview.fileName}</Text>
              <Text style={styles.reportMeta}>
                {preview.exam_date}
                {preview.hospital_name ? ` · ${preview.hospital_name}` : ''}
              </Text>
              <View style={styles.metricRow}>
                <Metric value={preview.items.length} label="识别指标" />
                <Metric value={abnormalCount(preview)} label="需复核" tone="caution" />
                <Metric value={preview.conclusions?.length ?? 0} label="报告结论" />
              </View>
            </View>
            {!!error && <InlineError message={error} />}
            {preview.overall_assessment ? (
              <View style={styles.assessment}>
                <Text style={styles.sectionLabel}>报告摘要</Text>
                <Text style={styles.assessmentText}>{preview.overall_assessment}</Text>
              </View>
            ) : null}
            <Text style={styles.sectionTitle}>识别结果</Text>
            {preview.items.length > 0 ? preview.items.slice(0, 30).map((item, index) => (
              <View key={`${item.item_code || item.item_name}-${index}`} style={styles.itemRow}>
                <View style={styles.itemCopy}>
                  <Text style={styles.itemName}>{item.item_name}</Text>
                  <Text style={styles.itemReference}>
                    {item.reference_range ? `参考 ${item.reference_range}` : '请对照原报告复核'}
                  </Text>
                </View>
                <Text style={[
                  styles.itemValue,
                  item.is_abnormal !== 'normal' && styles.itemValueCaution,
                ]}>
                  {item.value ?? item.value_text ?? '—'}{item.unit ? ` ${item.unit}` : ''}
                </Text>
              </View>
            )) : (
              <Text style={styles.emptyItems}>未识别到结构化指标，将保存报告摘要供后续查看。</Text>
            )}
          </ScrollView>
          <View style={styles.footer}>
            <TouchableOpacity style={styles.changeButton} onPress={reset} disabled={status === 'saving'}>
              <Text style={styles.changeButtonText}>更换报告</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.confirmButton, status === 'saving' && styles.buttonDisabled]}
              onPress={confirm}
              disabled={status === 'saving'}
              accessibilityRole="button"
              accessibilityLabel="确认保存体检报告"
            >
              {status === 'saving'
                ? <ActivityIndicator color={C.greenOn} />
                : <Text style={styles.confirmButtonText}>确认保存</Text>}
            </TouchableOpacity>
          </View>
        </>
      )}

      {status === 'success' && (
        <View style={styles.centerState}>
          <View style={styles.successIcon}>
            <Ionicons name="checkmark" size={30} color={C.greenOn} />
          </View>
          <Text style={styles.stateTitle}>已保存到健康档案</Text>
          <Text style={styles.stateBody}>小巴现在可以在对话中引用这份报告。</Text>
          <TouchableOpacity style={[styles.primaryButton, styles.doneButton]} onPress={close}>
            <Text style={styles.primaryButtonText}>完成</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );

  if (presentation === 'screen') return body;
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={close}
    >
      {body}
    </Modal>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <View style={styles.inlineError}>
      <Ionicons name="alert-circle-outline" size={20} color={revaSemantic.risk.fg} />
      <Text style={styles.inlineErrorText}>{message}</Text>
    </View>
  );
}

function SourceRow({
  icon,
  title,
  subtitle,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable style={({ pressed }) => [styles.sourceRow, pressed && styles.rowPressed]} onPress={onPress}>
      <View style={styles.sourceIcon}>
        <Ionicons name={icon} size={22} color={C.green500} />
      </View>
      <View style={styles.sourceCopy}>
        <Text style={styles.sourceTitle}>{title}</Text>
        <Text style={styles.sourceSubtitle}>{subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={C.ink3} />
    </Pressable>
  );
}

function Metric({ value, label, tone }: { value: number; label: string; tone?: 'caution' }) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, tone === 'caution' && styles.metricCaution]}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    minHeight: 72,
    paddingHorizontal: revaSpacing.s4,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
    backgroundColor: C.surface,
  },
  iconButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface2,
  },
  headerCopy: { flex: 1, alignItems: 'center' },
  headerSpacer: { width: 40 },
  title: { fontSize: 18, lineHeight: 24, fontWeight: '700', color: C.ink1 },
  step: { marginTop: 2, fontSize: 12, lineHeight: 17, color: C.ink3 },
  content: { padding: revaSpacing.s5, paddingBottom: revaSpacing.s8 },
  intro: { paddingVertical: revaSpacing.s3, marginBottom: revaSpacing.s4 },
  introIcon: {
    width: 48,
    height: 48,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: revaSpacing.s4,
  },
  introTitle: { fontSize: 24, lineHeight: 31, fontWeight: '700', color: C.ink1 },
  introBody: { marginTop: revaSpacing.s2, fontSize: 15, lineHeight: 23, color: C.ink2 },
  sourceRow: {
    minHeight: 78,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: revaSpacing.s4,
    marginBottom: revaSpacing.s3,
    borderRadius: revaRadii.md,
    borderWidth: 1,
    borderColor: C.line,
    backgroundColor: C.surface,
  },
  rowPressed: { backgroundColor: C.green50, borderColor: C.green100 },
  sourceIcon: {
    width: 42,
    height: 42,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  sourceCopy: { flex: 1, marginHorizontal: revaSpacing.s3 },
  sourceTitle: { fontSize: 16, lineHeight: 22, fontWeight: '600', color: C.ink1 },
  sourceSubtitle: { marginTop: 3, fontSize: 13, lineHeight: 18, color: C.ink3 },
  privacy: { marginTop: revaSpacing.s3, fontSize: 12, lineHeight: 18, color: C.ink3 },
  centerState: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: revaSpacing.s6,
  },
  stateTitle: { marginTop: revaSpacing.s5, fontSize: 21, lineHeight: 28, fontWeight: '700', color: C.ink1 },
  stateBody: { marginTop: revaSpacing.s2, textAlign: 'center', fontSize: 15, lineHeight: 22, color: C.ink2 },
  stateHint: { marginTop: revaSpacing.s3, fontSize: 13, lineHeight: 19, color: C.ink3 },
  errorState: { flex: 1, padding: revaSpacing.s5 },
  fileLine: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: revaSpacing.s4,
    marginBottom: revaSpacing.s4,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
  },
  fileName: { flex: 1, marginLeft: revaSpacing.s3, fontSize: 15, lineHeight: 21, color: C.ink1 },
  inlineError: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    padding: revaSpacing.s4,
    borderRadius: revaRadii.md,
    backgroundColor: revaSemantic.risk.bg,
    borderWidth: 1,
    borderColor: revaSemantic.risk.line,
    marginBottom: revaSpacing.s4,
  },
  inlineErrorText: {
    flex: 1,
    marginLeft: revaSpacing.s2,
    fontSize: 14,
    lineHeight: 21,
    color: revaSemantic.risk.fg,
  },
  errorActions: { marginTop: 'auto', gap: revaSpacing.s3 },
  primaryButton: {
    minHeight: 52,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green500,
  },
  primaryButtonText: { fontSize: 16, fontWeight: '700', color: C.greenOn },
  secondaryButton: {
    minHeight: 52,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: C.lineStrong,
    backgroundColor: C.surface,
  },
  secondaryButtonText: { fontSize: 16, fontWeight: '600', color: C.ink2 },
  reviewContent: { padding: revaSpacing.s5, paddingBottom: 110 },
  reportSummary: {
    paddingBottom: revaSpacing.s5,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  reportName: { fontSize: 20, lineHeight: 27, fontWeight: '700', color: C.ink1 },
  reportMeta: { marginTop: revaSpacing.s2, fontSize: 14, lineHeight: 20, color: C.ink2 },
  metricRow: { marginTop: revaSpacing.s5, flexDirection: 'row' },
  metric: { flex: 1 },
  metricValue: { fontSize: 26, lineHeight: 31, fontWeight: '600', color: C.ink1 },
  metricCaution: { color: revaSemantic.caution.fg },
  metricLabel: { marginTop: 3, fontSize: 12, lineHeight: 17, color: C.ink3 },
  assessment: {
    marginTop: revaSpacing.s5,
    paddingLeft: revaSpacing.s3,
    borderLeftWidth: 3,
    borderLeftColor: C.green300,
  },
  sectionLabel: { fontSize: 12, lineHeight: 17, fontWeight: '600', color: C.green600 },
  assessmentText: { marginTop: revaSpacing.s2, fontSize: 14, lineHeight: 22, color: C.ink2 },
  sectionTitle: { marginTop: revaSpacing.s6, marginBottom: revaSpacing.s2, fontSize: 17, lineHeight: 23, fontWeight: '700', color: C.ink1 },
  itemRow: {
    minHeight: 64,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  itemCopy: { flex: 1, paddingVertical: revaSpacing.s3, paddingRight: revaSpacing.s3 },
  itemName: { fontSize: 15, lineHeight: 21, fontWeight: '600', color: C.ink1 },
  itemReference: { marginTop: 3, fontSize: 12, lineHeight: 17, color: C.ink3 },
  itemValue: { maxWidth: '42%', textAlign: 'right', fontSize: 15, lineHeight: 21, fontWeight: '600', color: C.ink1 },
  itemValueCaution: { color: revaSemantic.caution.fg },
  emptyItems: { paddingVertical: revaSpacing.s5, fontSize: 14, lineHeight: 22, color: C.ink2 },
  footer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3,
    flexDirection: 'row',
    gap: revaSpacing.s3,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    backgroundColor: C.surface,
    ...revaShadows.sm,
  },
  changeButton: {
    minWidth: 108,
    minHeight: 52,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: C.lineStrong,
  },
  changeButtonText: { fontSize: 15, fontWeight: '600', color: C.ink2 },
  confirmButton: {
    flex: 1,
    minHeight: 52,
    borderRadius: revaRadii.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green500,
  },
  confirmButtonText: { fontSize: 16, fontWeight: '700', color: C.greenOn },
  buttonDisabled: { opacity: 0.65 },
  successIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green500,
  },
  doneButton: { alignSelf: 'stretch', marginTop: revaSpacing.s6 },
});
