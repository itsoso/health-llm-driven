import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  ImageSourcePropType,
  Modal,
  PixelRatio,
  Platform,
  Share,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as Sharing from 'expo-sharing';
import { captureRef, releaseCapture } from 'react-native-view-shot';

import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import type { DietRecord } from '../../services/diet';

const MEAL_LABEL: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};
export const DIET_SHARE_IMAGE_TIMEOUT_MS = 5_000;
type ShareTarget = 'generic' | 'wechat' | 'xiaohongshu';

export function dietShareCaptureDimensions(
  platform = Platform.OS,
  pixelRatio = PixelRatio.get(),
): { width: number; height: number } {
  const pointScale = platform === 'ios' ? Math.max(pixelRatio, 1) : 1;
  return { width: 1080 / pointScale, height: 1440 / pointScale };
}

function metric(value: number | null | undefined, precision = 0): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '--';
  const factor = 10 ** precision;
  return `${Math.round(value * factor) / factor}`;
}

function hasMetric(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function hasAnyMacro(record: DietRecord): boolean {
  return [record.protein, record.carbs, record.fat].some(hasMetric);
}

function nutritionSourceLabel(source?: string | null): string {
  if (!source || source === 'ai_estimate' || source === 'photo') return '智能估算';
  if (source === 'manual' || source === 'user_corrected') return '手动确认';
  if (source === 'mixed') return '多来源校准';
  return '营养表校准';
}

export function buildDietShareHeadline(record: DietRecord): string {
  if (typeof record.protein === 'number' && record.protein >= 35) return '蛋白质拉满的一餐';
  if (typeof record.fiber === 'number' && record.fiber >= 6) return '膳食纤维在线的一餐';
  if (typeof record.calories === 'number' && record.calories <= 450) return '轻负担的一餐';
  return '这一餐，有据可查';
}

export function buildDietShareHighlights(record: DietRecord): string[] {
  const tags: string[] = [];
  if (typeof record.protein === 'number' && record.protein >= 30) tags.push('高蛋白');
  if (typeof record.fat === 'number' && record.fat <= 12) tags.push('低脂');
  if (typeof record.fiber === 'number' && record.fiber >= 5) tags.push('含纤维');
  if (typeof record.calories === 'number' && record.calories <= 450) tags.push('轻负担');
  return tags.slice(0, 3);
}

function buildDietShareStatusLine(highlights: string[]): string {
  if (highlights.length === 0) return '今日状态：认真记录';
  return `今日状态：${highlights.join(' · ')}`;
}

function buildDietShareCaptionStatusLine(highlights: string[]): string {
  if (highlights.length === 0) return '今日状态: 认真记录';
  return `今日状态: ${highlights.join(' / ')}`;
}

function buildDietShareDataDisclosure(record: DietRecord): string {
  const sourceLabel = nutritionSourceLabel(record.source);
  if (!hasMetric(record.calories) && !hasAnyMacro(record)) return '营养数据: 估算中，稍后可继续复盘';
  if (sourceLabel === '智能估算') return '营养数据: 智能估算，已确认，可继续复盘';
  if (sourceLabel === '手动确认') return '营养数据: 手动确认，可继续复盘';
  return `营养数据: ${sourceLabel}，已确认，可继续复盘`;
}

function buildDietShareMacroLine(record: DietRecord, style: 'compact' | 'sentence'): string {
  const parts = [
    hasMetric(record.calories) ? `热量 ${metric(record.calories)} kcal` : null,
    hasMetric(record.protein) ? `蛋白质 ${metric(record.protein)}g` : null,
    hasMetric(record.carbs) ? `碳水 ${metric(record.carbs)}g` : null,
    hasMetric(record.fat) ? `脂肪 ${metric(record.fat, 1)}g` : null,
  ].filter((part): part is string => Boolean(part));
  if (parts.length === 0) return '营养估算中，稍后可继续复盘';
  return style === 'sentence'
    ? `这一餐约 ${parts.join('，')}。`
    : parts.join(' · ');
}

export function buildDietShareCaption(record: DietRecord, dateLabel: string): string {
  const mealLabel = MEAL_LABEL[record.meal_type] ?? '餐食';
  const headline = buildDietShareHeadline(record);
  const highlights = buildDietShareHighlights(record);
  const lines = [
    `今天这餐打卡: ${dateLabel}`,
    headline,
    `${mealLabel}: ${record.food_items}`,
    buildDietShareCaptionStatusLine(highlights),
    buildDietShareMacroLine(record, 'compact'),
  ];
  if (highlights.length > 0) lines.push(`亮点: ${highlights.join(' / ')}`);
  if (record.fiber != null) lines.push(`膳食纤维 ${metric(record.fiber, 1)}g`);
  lines.push(buildDietShareDataDisclosure(record));
  lines.push('认真记录，也认真生活。');
  lines.push('#饮食打卡 #健康生活 #小巴记录');
  return lines.join('\n');
}

export function buildDietShareMomentsCaption(record: DietRecord, dateLabel: string): string {
  const mealLabel = MEAL_LABEL[record.meal_type] ?? '餐食';
  const headline = buildDietShareHeadline(record);
  const highlights = buildDietShareHighlights(record);
  const lines = [
    `${dateLabel}，${headline}。`,
    `${mealLabel}: ${record.food_items}`,
    buildDietShareCaptionStatusLine(highlights),
    buildDietShareMacroLine(record, 'sentence'),
  ];
  if (highlights.length > 0) lines.push(`亮点: ${highlights.join(' / ')}`);
  if (record.fiber != null) lines.push(`膳食纤维 ${metric(record.fiber, 1)}g。`);
  lines.push(buildDietShareDataDisclosure(record));
  lines.push('小巴帮我把吃过的东西留成一张可复盘的记录。');
  return lines.join('\n');
}

function captionForShareTarget(record: DietRecord, dateLabel: string, target: ShareTarget): string {
  return target === 'wechat'
    ? buildDietShareMomentsCaption(record, dateLabel)
    : buildDietShareCaption(record, dateLabel);
}

function dialogTitleForShareTarget(target: ShareTarget): string {
  if (target === 'wechat') return '发微信/朋友圈';
  if (target === 'xiaohongshu') return '发小红书';
  return '分享饮食打卡';
}

export type DietShareCardProps = {
  record: DietRecord;
  dateLabel: string;
  imageSource?: ImageSourcePropType;
  onImageReady?: () => void;
  forceImageFallback?: boolean;
};

export default function DietShareCard({
  record,
  dateLabel,
  imageSource,
  onImageReady,
  forceImageFallback = false,
}: DietShareCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = Boolean(imageSource) && !imageFailed && !forceImageFallback;
  const calories = metric(record.calories);
  const hasCalories = hasMetric(record.calories);
  const hasMacros = hasAnyMacro(record);
  const sourceLabel = nutritionSourceLabel(record.source);
  const headline = buildDietShareHeadline(record);
  const highlights = buildDietShareHighlights(record);
  const statusLine = buildDietShareStatusLine(highlights);

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.brandMark}>
          <Ionicons name="sparkles" size={15} color={C.greenBright} />
        </View>
        <Text style={styles.brand}>小巴 / 今日饮食</Text>
        <View style={styles.confirmBadge}>
          <Text style={styles.confirmBadgePrimary}>已确认</Text>
          <Text style={styles.confirmBadgeSecondary}>可分享</Text>
        </View>
        <Text style={styles.date}>{dateLabel}</Text>
      </View>

      {showImage ? (
        <Image
          testID="diet-share-image"
          source={imageSource}
          style={styles.mealImage}
          resizeMode="cover"
          onLoad={onImageReady}
          onError={() => {
            setImageFailed(true);
            onImageReady?.();
          }}
        />
      ) : (
        <View style={styles.metricHero}>
          <View>
            <Text style={styles.heroLabel}>{MEAL_LABEL[record.meal_type] ?? '餐食'}能量</Text>
            {hasCalories ? (
              <View style={styles.heroMetricRow}>
                <Text style={styles.heroMetric}>{calories}</Text>
                <Text style={styles.heroUnit}>kcal</Text>
              </View>
            ) : (
              <Text style={styles.pendingHeroMetric}>营养估算中</Text>
            )}
          </View>
          <View style={styles.heroBars}>
            <View style={[styles.heroBar, { backgroundColor: '#F26945', width: '92%' }]} />
            <View style={[styles.heroBar, { backgroundColor: C.blue500, width: '68%' }]} />
            <View style={[styles.heroBar, { backgroundColor: C.greenBright, width: '46%' }]} />
          </View>
        </View>
      )}

      <View style={styles.cardBody}>
        <View style={styles.storyRow}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.storyTitle}>{headline}</Text>
            <Text style={styles.foods} numberOfLines={3}>{record.food_items}</Text>
            {highlights.length > 0 ? (
              <View style={styles.highlightRow}>
                {highlights.map((tag) => (
                  <View key={tag} style={styles.highlightPill}>
                    <Text style={styles.highlightText}>{tag}</Text>
                  </View>
                ))}
              </View>
            ) : null}
            <Text style={styles.statusLine}>{statusLine}</Text>
          </View>
          {showImage ? (
            <View style={styles.calorieAside}>
              <Text style={styles.calorieAsideValue}>{calories}</Text>
              <Text style={styles.calorieAsideUnit}>kcal</Text>
            </View>
          ) : null}
        </View>

        {hasMacros ? (
          <View style={styles.macroGrid}>
            <ShareMacro label="蛋白质" value={hasMetric(record.protein) ? `${metric(record.protein)}g` : '估算中'} color="#E34F6F" />
            <ShareMacro label="碳水" value={hasMetric(record.carbs) ? `${metric(record.carbs)}g` : '估算中'} color={C.blue500} />
            <ShareMacro label="脂肪" value={hasMetric(record.fat) ? `${metric(record.fat, 1)}g` : '估算中'} color="#D18B1D" />
          </View>
        ) : (
          <View style={styles.pendingMacroPanel}>
            <Text style={styles.pendingMacroTitle}>营养估算中</Text>
            <Text style={styles.pendingMacroText}>确认记录已保存，热量和三大营养会回填后用于复盘。</Text>
          </View>
        )}

        <View style={styles.sourceRow}>
          <Ionicons
            name={sourceLabel === '智能估算' ? 'scan-outline' : 'shield-checkmark-outline'}
            size={14}
            color={sourceLabel === '智能估算' ? revaSemantic.caution.fg : C.green600}
          />
          <Text style={[
            styles.sourceText,
            { color: sourceLabel === '智能估算' ? revaSemantic.caution.fg : C.green600 },
          ]}>{sourceLabel}</Text>
          {record.fiber != null ? <Text style={styles.fiberText}>膳食纤维 {metric(record.fiber, 1)}g</Text> : null}
        </View>
      </View>

      <View style={styles.cardFooter}>
        <Text style={styles.footerPrimary}>认真记录，也认真生活</Text>
        <Text style={styles.footerSecondary}>营养数据以本次确认记录为准</Text>
      </View>
    </View>
  );
}

function ShareMacro({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.macroItem}>
      <View style={[styles.macroAccent, { backgroundColor: color }]} />
      <Text style={styles.macroValue}>{value}</Text>
      <Text style={styles.macroLabel}>{label}</Text>
    </View>
  );
}

export type DietShareSheetProps = DietShareCardProps & {
  visible: boolean;
  onClose: () => void;
  onShareTerminal?: (meta: {
    phase: 'completed' | 'failed';
    duration_ms: number;
    has_photo: boolean;
    error_code?: string;
  }) => void;
};

export function DietShareSheet({
  visible,
  record,
  dateLabel,
  imageSource,
  onClose,
  onShareTerminal,
}: DietShareSheetProps) {
  const cardRef = useRef<View>(null);
  const [sharing, setSharing] = useState(false);
  const [imageReady, setImageReady] = useState(!imageSource);
  const [imageTimedOut, setImageTimedOut] = useState(false);
  const [copiedCaption, setCopiedCaption] = useState<'moments' | 'xiaohongshu' | null>(null);

  React.useEffect(() => {
    setImageReady(!imageSource);
    setImageTimedOut(false);
    setCopiedCaption(null);
  }, [imageSource, visible]);

  React.useEffect(() => {
    if (!visible || !imageSource || imageReady) return undefined;
    const timeout = setTimeout(() => {
      setImageTimedOut(true);
      setImageReady(true);
    }, DIET_SHARE_IMAGE_TIMEOUT_MS);
    return () => clearTimeout(timeout);
  }, [imageReady, imageSource, visible]);

  const shareTextFallback = async (target: ShareTarget = 'generic') => {
    await Share.share({
      title: dialogTitleForShareTarget(target),
      message: captionForShareTarget(record, dateLabel, target),
    });
  };

  const copyCaption = async (kind: 'moments' | 'xiaohongshu') => {
    try {
      await Clipboard.setStringAsync(
        kind === 'moments'
          ? buildDietShareMomentsCaption(record, dateLabel)
          : buildDietShareCaption(record, dateLabel),
      );
      setCopiedCaption(kind);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      Alert.alert('复制失败', '请稍后重试');
    }
  };

  const handleShare = async (target: ShareTarget = 'generic') => {
    if (sharing || !imageReady || !cardRef.current) return;
    const startedAt = Date.now();
    let captureUri: string | null = null;
    setSharing(true);
    try {
      if (target !== 'generic') {
        await Clipboard.setStringAsync(captionForShareTarget(record, dateLabel, target));
      }
      if (!await Sharing.isAvailableAsync()) {
        await shareTextFallback(target);
        onShareTerminal?.({
          phase: 'completed',
          duration_ms: Date.now() - startedAt,
          has_photo: false,
        });
        return;
      }
      const dimensions = dietShareCaptureDimensions();
      captureUri = await captureRef(cardRef, {
        format: 'png',
        quality: 1,
        ...dimensions,
        result: 'tmpfile',
      });
      await Sharing.shareAsync(captureUri, {
        mimeType: 'image/png',
        UTI: 'public.png',
        dialogTitle: dialogTitleForShareTarget(target),
      });
      onShareTerminal?.({
        phase: 'completed',
        duration_ms: Date.now() - startedAt,
        has_photo: Boolean(record.image_url),
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      try {
        await shareTextFallback(target);
        onShareTerminal?.({
          phase: 'completed',
          duration_ms: Date.now() - startedAt,
          has_photo: false,
        });
      } catch {
        onShareTerminal?.({
          phase: 'failed',
          duration_ms: Date.now() - startedAt,
          has_photo: Boolean(record.image_url),
          error_code: 'image_share_failed',
        });
        Alert.alert('分享失败', '图片和文字分享均不可用，请稍后重试');
      }
    } finally {
      if (captureUri) {
        try {
          releaseCapture(captureUri);
        } catch {
          // Temporary-file cleanup is best effort after the system share promise settles.
        }
      }
      setSharing(false);
    }
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent
      statusBarTranslucent
      onRequestClose={onClose}
    >
      <View style={styles.modalBackdrop}>
        <SafeAreaView style={styles.sheet}>
          <View style={styles.sheetHeader}>
            <View>
              <Text style={styles.sheetTitle}>分享这一餐</Text>
              <Text style={styles.sheetSubtitle}>高清 3:4 图片 · 微信与小红书</Text>
            </View>
            <TouchableOpacity
              style={styles.closeButton}
              onPress={onClose}
              accessibilityRole="button"
              accessibilityLabel="关闭分享预览"
            >
              <Ionicons name="close" size={22} color={C.ink2} />
            </TouchableOpacity>
          </View>

          <View style={styles.previewFrame}>
            <View ref={cardRef} collapsable={false} style={styles.captureSurface}>
              <DietShareCard
                record={record}
                dateLabel={dateLabel}
                imageSource={imageSource}
                onImageReady={() => setImageReady(true)}
                forceImageFallback={imageTimedOut}
              />
            </View>
          </View>

          <View style={styles.platformShareRow}>
            <TouchableOpacity
              style={[styles.platformShareButton, styles.wechatShareButton, (sharing || !imageReady) && styles.shareButtonDisabled]}
              onPress={() => handleShare('wechat')}
              disabled={sharing || !imageReady}
              activeOpacity={0.84}
              accessibilityRole="button"
              accessibilityLabel="发微信或朋友圈"
            >
              <Ionicons name="chatbubble-ellipses-outline" size={18} color={C.greenOn} />
              <View>
                <Text style={styles.platformShareText}>发微信/朋友圈</Text>
                <Text style={styles.platformShareHint}>自动复制朋友圈文案</Text>
              </View>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.platformShareButton, styles.xhsShareButton, (sharing || !imageReady) && styles.shareButtonDisabled]}
              onPress={() => handleShare('xiaohongshu')}
              disabled={sharing || !imageReady}
              activeOpacity={0.84}
              accessibilityRole="button"
              accessibilityLabel="发小红书"
            >
              <Ionicons name="sparkles-outline" size={18} color="#fff" />
              <View>
                <Text style={styles.platformShareText}>发小红书</Text>
                <Text style={styles.platformShareHint}>自动复制带话题文案</Text>
              </View>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={[styles.shareButton, (sharing || !imageReady) && styles.shareButtonDisabled]}
            onPress={() => handleShare('generic')}
            disabled={sharing || !imageReady}
            activeOpacity={0.84}
            accessibilityRole="button"
            accessibilityLabel="分享饮食图片"
          >
            {sharing || !imageReady ? (
              <ActivityIndicator size="small" color={C.greenOn} />
            ) : (
              <Ionicons name="share-outline" size={19} color={C.greenOn} />
            )}
            <Text style={styles.shareButtonText}>{!imageReady ? '图片加载中' : sharing ? '生成中' : '分享图片'}</Text>
          </TouchableOpacity>
          <View style={styles.captionButtonRow}>
            <TouchableOpacity
              style={styles.captionButton}
              onPress={() => copyCaption('moments')}
              disabled={sharing}
              activeOpacity={0.78}
              accessibilityRole="button"
              accessibilityLabel="复制朋友圈文案"
            >
              <Ionicons name="chatbubble-ellipses-outline" size={17} color={C.green600} />
              <Text style={styles.captionButtonText}>
                {copiedCaption === 'moments' ? '已复制朋友圈文案' : '复制朋友圈文案'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.captionButton}
              onPress={() => copyCaption('xiaohongshu')}
              disabled={sharing}
              activeOpacity={0.78}
              accessibilityRole="button"
              accessibilityLabel="复制小红书文案"
            >
              <Ionicons name="copy-outline" size={17} color={C.green600} />
              <Text style={styles.captionButtonText}>
                {copiedCaption === 'xiaohongshu' ? '已复制小红书文案' : '复制小红书文案'}
              </Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  card: {
    width: '100%',
    aspectRatio: 3 / 4,
    backgroundColor: C.surface,
    overflow: 'hidden',
  },
  cardHeader: {
    height: 48,
    paddingHorizontal: 16,
    backgroundColor: C.focusBg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  brandMark: {
    width: 25,
    height: 25,
    borderRadius: 6,
    backgroundColor: C.focusBg2,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
  },
  brand: { fontFamily: revaFonts.sans, fontSize: 12, color: C.focusInk1, fontWeight: '800', flex: 1 },
  confirmBadge: {
    minHeight: 25,
    borderRadius: 7,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: 'rgba(255,255,255,0.64)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    alignItems: 'center',
    justifyContent: 'center',
  },
  confirmBadgePrimary: { fontFamily: revaFonts.sans, fontSize: 8, color: C.green600, fontWeight: '900' },
  confirmBadgeSecondary: { fontFamily: revaFonts.sans, fontSize: 7, color: C.focusInk2, fontWeight: '800', marginTop: -1 },
  date: { fontFamily: revaFonts.mono, fontSize: 10, color: C.focusInk2 },
  mealImage: { width: '100%', height: 136, backgroundColor: C.paper2 },
  metricHero: {
    height: 136,
    backgroundColor: C.focusBg2,
    paddingHorizontal: 20,
    paddingVertical: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heroLabel: { fontFamily: revaFonts.sans, fontSize: 11, color: C.focusInk2, fontWeight: '700' },
  heroMetricRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 7, marginTop: 4 },
  heroMetric: { fontFamily: revaFonts.mono, fontSize: 48, lineHeight: 52, color: C.focusInk1, fontWeight: '600' },
  heroUnit: { fontFamily: revaFonts.mono, fontSize: 12, color: '#F6A184', marginBottom: 8 },
  pendingHeroMetric: { fontFamily: revaFonts.sans, fontSize: 24, lineHeight: 31, color: C.focusInk1, fontWeight: '900', marginTop: 10 },
  heroBars: { width: 80, gap: 9, alignItems: 'flex-end' },
  heroBar: { height: 5, borderRadius: 2 },
  cardBody: { flex: 1, paddingHorizontal: 18, paddingTop: 16, paddingBottom: 12 },
  storyRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  storyTitle: { fontFamily: revaFonts.sans, fontSize: 19, lineHeight: 24, color: C.ink1, fontWeight: '800' },
  foods: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 19, color: C.ink2, marginTop: 7 },
  highlightRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 9 },
  highlightPill: {
    minHeight: 20,
    borderRadius: 10,
    paddingHorizontal: 8,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    justifyContent: 'center',
  },
  highlightText: { fontFamily: revaFonts.sans, fontSize: 9, color: C.green600, fontWeight: '900' },
  statusLine: { fontFamily: revaFonts.sans, fontSize: 10, lineHeight: 15, color: C.ink2, fontWeight: '800', marginTop: 9 },
  calorieAside: { alignItems: 'flex-end', paddingTop: 2 },
  calorieAsideValue: { fontFamily: revaFonts.mono, fontSize: 26, lineHeight: 29, color: '#E45D3B', fontWeight: '600' },
  calorieAsideUnit: { fontFamily: revaFonts.mono, fontSize: 9, color: C.ink3, marginTop: 2 },
  macroGrid: {
    flexDirection: 'row',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    marginTop: 14,
    paddingVertical: 12,
  },
  macroItem: { flex: 1, paddingHorizontal: 8, position: 'relative' },
  macroAccent: { width: 18, height: 3, borderRadius: 2, marginBottom: 6 },
  macroValue: { fontFamily: revaFonts.mono, fontSize: 15, color: C.ink1, fontWeight: '600' },
  macroLabel: { fontFamily: revaFonts.sans, fontSize: 9, color: C.ink3, marginTop: 2 },
  pendingMacroPanel: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    marginTop: 14,
    paddingVertical: 12,
  },
  pendingMacroTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, fontWeight: '900' },
  pendingMacroText: { fontFamily: revaFonts.sans, fontSize: 10, lineHeight: 15, color: C.ink3, marginTop: 4 },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 11 },
  sourceText: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '800' },
  fiberText: { fontFamily: revaFonts.mono, fontSize: 9, color: C.ink3, marginLeft: 'auto' },
  cardFooter: {
    height: 42,
    paddingHorizontal: 18,
    backgroundColor: C.paper2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  footerPrimary: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2, fontWeight: '800' },
  footerSecondary: { fontFamily: revaFonts.sans, fontSize: 8, color: C.ink3 },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(15, 28, 23, 0.58)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: C.paper,
    borderTopLeftRadius: revaRadii.xl,
    borderTopRightRadius: revaRadii.xl,
    paddingHorizontal: revaSpacing.s5,
    paddingTop: revaSpacing.s4,
    paddingBottom: revaSpacing.s4,
    alignItems: 'center',
  },
  sheetHeader: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: revaSpacing.s3,
  },
  sheetTitle: { fontFamily: revaFonts.sans, fontSize: 18, color: C.ink1, fontWeight: '800' },
  sheetSubtitle: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 2 },
  closeButton: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: C.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  previewFrame: {
    width: '92%',
    maxWidth: 330,
    aspectRatio: 3 / 4,
    backgroundColor: C.surface,
    ...revaShadows.md,
  },
  captureSurface: { width: '100%', height: '100%', backgroundColor: C.surface },
  platformShareRow: {
    width: '100%',
    flexDirection: 'row',
    gap: 10,
    marginTop: revaSpacing.s4,
  },
  platformShareButton: {
    flex: 1,
    minHeight: 54,
    borderRadius: revaRadii.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: 10,
  },
  wechatShareButton: { backgroundColor: C.green500 },
  xhsShareButton: { backgroundColor: '#D95A45' },
  platformShareText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.greenOn, fontWeight: '900' },
  platformShareHint: { fontFamily: revaFonts.sans, fontSize: 9.5, color: 'rgba(255,255,255,0.78)', marginTop: 1 },
  shareButton: {
    width: '100%',
    minHeight: 48,
    borderRadius: revaRadii.md,
    backgroundColor: C.ink2,
    marginTop: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  shareButtonDisabled: { opacity: 0.72 },
  shareButtonText: { fontFamily: revaFonts.sans, fontSize: 15, color: C.greenOn, fontWeight: '800' },
  captionButtonRow: {
    width: '100%',
    flexDirection: 'row',
    gap: 10,
    marginTop: revaSpacing.s2,
  },
  captionButton: {
    flex: 1,
    minHeight: 44,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: 8,
  },
  captionButtonText: { fontFamily: revaFonts.sans, fontSize: 13, color: C.green600, fontWeight: '800' },
});
