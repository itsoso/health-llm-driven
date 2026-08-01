import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
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
import { Image } from 'expo-image';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import * as Haptics from 'expo-haptics';
import * as MediaLibrary from 'expo-media-library';
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
import { SocialBrandIcon } from '../common/SocialBrandIcon';
import { MACRO_HUES } from '../chat/cards/mealCardVisuals';
import { DietPrivacyRedactionOverlay } from './DietPrivacyRedactionOverlay';
import type { DietShareRedaction } from './dietShareImageEdit';
import {
  buildDietSharePresentation,
  type DietShareRecord,
} from './dietSharePresentation';

const MEAL_LABEL: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};
export const DIET_SHARE_IMAGE_TIMEOUT_MS = 5_000;
const DIET_SHARE_REVIEW_CONFIDENCE_THRESHOLD = 70;
type ShareTarget = 'generic' | 'wechat' | 'xiaohongshu';
type MacroSegmentKey = 'protein' | 'carbs' | 'fat';
type DietShareMacroSegment = {
  key: MacroSegmentKey;
  label: string;
  grams: number;
  percent: number;
  color: string;
};
type ShareResult =
  | { target: ShareTarget; kind: 'completed' }
  | { target: ShareTarget; kind: 'caption_fallback' }
  | { target: ShareTarget; kind: 'saved_to_library' }
  | { target: ShareTarget; kind: 'photo_library_permission_denied' };
type ShareReviewTone = 'none' | 'estimate' | 'low-confidence';
type ShareInFlight = ShareTarget | 'library';

function imageSourceIdentity(source: ImageSourcePropType | undefined): string {
  if (source == null) return 'none';
  if (typeof source === 'number') return `asset:${source}`;
  if (Array.isArray(source)) return source.map(imageSourceIdentity).join('|');
  const candidate = source as {
    uri?: string;
    width?: number;
    height?: number;
    scale?: number;
    headers?: Record<string, string>;
  };
  const headerMaterial = Object.entries(candidate.headers ?? {})
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([name, value]) => `${name}:${value}`)
    .join('\n');
  let headerFingerprint = 2166136261;
  for (let index = 0; index < headerMaterial.length; index += 1) {
    headerFingerprint ^= headerMaterial.charCodeAt(index);
    headerFingerprint = Math.imul(headerFingerprint, 16777619);
  }
  return JSON.stringify({
    uri: candidate.uri ?? '',
    width: candidate.width ?? null,
    height: candidate.height ?? null,
    scale: candidate.scale ?? null,
    headerFingerprint: (headerFingerprint >>> 0).toString(36),
  });
}

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

function isNutritionComplete(record: DietRecord): boolean {
  return [record.calories, record.protein, record.carbs, record.fat].every(hasMetric);
}

function hasAnyNutritionMetric(record: DietRecord): boolean {
  return [record.calories, record.protein, record.carbs, record.fat].some(hasMetric);
}

function nutritionSourceLabel(source?: string | null): string {
  if (!source || source === 'ai_estimate' || source === 'photo') return '智能估算';
  if (source === 'manual' || source === 'user_corrected') return '手动确认';
  if (source === 'mixed') return '多来源校准';
  return '营养表校准';
}

function isManuallyConfirmedNutritionSource(source?: string | null): boolean {
  return source === 'manual' || source === 'user_corrected';
}

export function buildDietShareHeadline(record: DietRecord): string {
  if (isLowConfidenceDietShare(record)) return '待核对的一餐';
  if (typeof record.protein === 'number' && record.protein >= 35) return '蛋白质拉满的一餐';
  if (typeof record.fiber === 'number' && record.fiber >= 6) return '膳食纤维在线的一餐';
  if (typeof record.calories === 'number' && record.calories <= 450) return '轻负担的一餐';
  return '这一餐，有据可查';
}

export function buildDietShareHighlights(record: DietRecord): string[] {
  if (isLowConfidenceDietShare(record)) return ['待核对'];
  const tags: string[] = [];
  if (typeof record.protein === 'number' && record.protein >= 30) tags.push('高蛋白');
  if (typeof record.fat === 'number' && record.fat <= 12) tags.push('低脂');
  if (typeof record.fiber === 'number' && record.fiber >= 5) tags.push('含纤维');
  if (typeof record.calories === 'number' && record.calories <= 450) tags.push('轻负担');
  return tags.slice(0, 3);
}

export function buildDietShareBalance(record: DietRecord): { score: number | null; label: string } {
  if (isLowConfidenceDietShare(record)) {
    return { score: null, label: '核对后生成均衡度' };
  }
  if (!isNutritionComplete(record)) {
    return { score: null, label: '营养回填后生成均衡度' };
  }

  let score = 58;
  if ((record.protein ?? 0) >= 30) score += (record.protein ?? 0) > 45 ? 14 : 16;
  else if ((record.protein ?? 0) >= 18) score += 9;
  if ((record.fat ?? 0) <= 12) score += 12;
  else if ((record.fat ?? 0) <= 20) score += 10;
  if ((record.fiber ?? 0) >= 5) score += 10;
  else if ((record.fiber ?? 0) >= 3) score += 6;
  if ((record.calories ?? 0) >= 350 && (record.calories ?? 0) <= 750) score += 10;
  else if ((record.calories ?? 0) >= 250 && (record.calories ?? 0) <= 850) score += 6;
  if ((record.carbs ?? 0) >= 25 && (record.carbs ?? 0) <= 90) score += 8;

  const normalized = Math.min(96, Math.max(62, score));
  if (normalized >= 90 && (record.protein ?? 0) >= 30) return { score: normalized, label: '高蛋白稳态餐' };
  if (normalized >= 88) return { score: normalized, label: '结构很在线' };
  if (normalized >= 78) return { score: normalized, label: '均衡感不错' };
  return { score: normalized, label: '已记录，可复盘' };
}

function buildDietShareCaptionStatusLine(highlights: string[]): string {
  if (highlights.length === 0) return '今日状态: 认真记录';
  return `今日状态: ${highlights.join(' / ')}`;
}

function buildDietShareHashtags(highlights: string[]): string {
  const tags: string[] = [];
  highlights.forEach((highlight) => {
    if (highlight === '高蛋白') tags.push('#高蛋白饮食');
    if (highlight === '低脂') tags.push('#低脂餐');
    if (highlight === '含纤维') tags.push('#膳食纤维');
    if (highlight === '轻负担') tags.push('#轻食打卡');
  });
  return [...tags, '#饮食打卡', '#健康生活', '#小巴记录'].join(' ');
}

function buildDietShareDataDisclosure(record: DietRecord): string {
  const sourceLabel = nutritionSourceLabel(record.source);
  if (isManuallyConfirmedNutritionSource(record.source)) return '营养数据: 手动核对，可继续复盘';
  const confidencePercent = normalizedAiConfidence(record.ai_confidence);
  if (confidencePercent != null && confidencePercent < DIET_SHARE_REVIEW_CONFIDENCE_THRESHOLD) {
    return `营养数据: ${sourceLabel}，待核对后再发布`;
  }
  if (!hasAnyNutritionMetric(record)) return '营养数据: 估算中，稍后可继续复盘';
  if (!isNutritionComplete(record)) return '营养数据: 部分估算中，可继续复盘';
  if (sourceLabel === '智能估算') return '营养数据: 智能估算，可继续复盘';
  if (sourceLabel === '手动确认') return '营养数据: 手动核对，可继续复盘';
  return `营养数据: ${sourceLabel}，已确认，可继续复盘`;
}

function normalizedAiConfidence(value: number | null | undefined): number | null {
  if (!hasMetric(value)) return null;
  const percent = value <= 1 ? value * 100 : value;
  if (percent < 0 || percent > 100) return null;
  return Math.round(percent);
}

function buildDietShareConfidenceDisclosure(record: DietRecord): string | null {
  if (isManuallyConfirmedNutritionSource(record.source)) return null;
  const percent = normalizedAiConfidence(record.ai_confidence);
  if (percent == null) return null;
  if (percent < DIET_SHARE_REVIEW_CONFIDENCE_THRESHOLD) return `识别置信度: ${percent}%，发布前建议核对食物和份量`;
  if (percent < 80) return `识别置信度: ${percent}%，建议复盘时留意份量`;
  return `识别置信度: ${percent}%`;
}

function isAiEstimatedNutritionSource(source?: string | null): boolean {
  return !source || source === 'ai_estimate' || source === 'photo';
}

function isLowConfidenceDietShare(record: DietRecord): boolean {
  if (isManuallyConfirmedNutritionSource(record.source)) return false;
  const percent = normalizedAiConfidence(record.ai_confidence);
  return percent != null && percent < DIET_SHARE_REVIEW_CONFIDENCE_THRESHOLD;
}

function buildDietShareMacroLine(record: DietRecord, style: 'compact' | 'sentence'): string {
  if (isLowConfidenceDietShare(record)) {
    return style === 'sentence'
      ? '这一餐营养估算待核对，确认后再生成热量和三大营养。'
      : '营养估算待核对，确认后再生成热量和三大营养';
  }
  const parts = [
    hasMetric(record.calories) ? `热量 ${metric(record.calories)} kcal` : null,
    hasMetric(record.protein) ? `蛋白质 ${metric(record.protein)}g` : null,
    hasMetric(record.carbs) ? `碳水 ${metric(record.carbs)}g` : null,
    hasMetric(record.fat) ? `脂肪 ${metric(record.fat, 1)}g` : null,
  ].filter((part): part is string => Boolean(part));
  if (parts.length === 0) return '营养估算中，稍后可继续复盘';
  const pendingParts = [
    hasMetric(record.calories) ? null : '热量估算中',
    hasMetric(record.protein) ? null : '蛋白质估算中',
    hasMetric(record.carbs) ? null : '碳水估算中',
    hasMetric(record.fat) ? null : '脂肪估算中',
  ].filter((part): part is string => Boolean(part));
  const allParts = parts.concat(pendingParts);
  return style === 'sentence'
    ? `这一餐约 ${allParts.join('，')}。`
    : allParts.join(' · ');
}

const SHARE_MACRO_DEFS: {
  key: MacroSegmentKey;
  field: 'protein' | 'carbs' | 'fat';
  label: string;
  kcalPerGram: number;
  color: string;
}[] = [
  { key: 'protein', field: 'protein', label: '蛋白', kcalPerGram: 4, color: MACRO_HUES.protein },
  { key: 'carbs', field: 'carbs', label: '碳水', kcalPerGram: 4, color: MACRO_HUES.carbs },
  { key: 'fat', field: 'fat', label: '脂肪', kcalPerGram: 9, color: MACRO_HUES.fat },
];

export function buildDietShareMacroSegments(record: DietRecord): DietShareMacroSegment[] {
  if (isLowConfidenceDietShare(record)) return [];

  const hasCompleteEnergyMacros = SHARE_MACRO_DEFS.every((def) => {
    const grams = record[def.field];
    return hasMetric(grams) && grams > 0;
  });
  if (!hasCompleteEnergyMacros) return [];

  const rawSegments = SHARE_MACRO_DEFS
    .map((def) => {
      const grams = record[def.field];
      if (!hasMetric(grams) || grams <= 0) return null;
      return {
        key: def.key,
        label: def.label,
        grams,
        kcal: grams * def.kcalPerGram,
        color: def.color,
      };
    })
    .filter((segment): segment is DietShareMacroSegment & { kcal: number } => Boolean(segment));

  const totalKcal = rawSegments.reduce((sum, segment) => sum + segment.kcal, 0);
  if (totalKcal <= 0) return [];

  const normalized = rawSegments.map((segment) => {
    const exactPercent = (segment.kcal / totalKcal) * 100;
    return {
      ...segment,
      percent: Math.floor(exactPercent),
      remainder: exactPercent - Math.floor(exactPercent),
    };
  });
  let remainingPercent = 100 - normalized.reduce((sum, segment) => sum + segment.percent, 0);
  [...normalized]
    .sort((a, b) => b.remainder - a.remainder)
    .forEach((segment) => {
      if (remainingPercent <= 0) return;
      segment.percent += 1;
      remainingPercent -= 1;
    });

  return normalized.map((segment) => ({
    key: segment.key,
    label: segment.label,
    grams: segment.grams,
    percent: segment.percent,
    color: segment.color,
  }));
}

function buildDietShareMacroStructureLine(record: DietRecord): string | null {
  if (isLowConfidenceDietShare(record)) return null;
  const segments = buildDietShareMacroSegments(record);
  if (segments.length === 0) return null;
  return `能量结构: ${segments.map((segment) => `${segment.label} ${segment.percent}%`).join(' / ')}`;
}

function shouldRenderHighlightCopy(highlights: string[]): boolean {
  return highlights.length > 0 && !highlights.includes('待核对');
}

export function compactDietShareFoodItems(foodItems: string, maxChars = 35): string {
  const normalized = foodItems.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxChars) return normalized;

  const parts = normalized
    .split(/[、,，]/)
    .map((part) => part.trim())
    .filter(Boolean);
  let compacted = '';
  for (const part of parts) {
    const candidate = compacted ? `${compacted}、${part}` : part;
    if (candidate.length > maxChars) break;
    compacted = candidate;
  }

  if (!compacted) compacted = normalized.slice(0, maxChars).trim();
  return `${compacted.replace(/[、,，\s]+$/, '')}…`;
}

export function buildDietShareCaption(record: DietRecord, dateLabel: string): string {
  const mealLabel = MEAL_LABEL[record.meal_type] ?? '餐食';
  const headline = buildDietShareHeadline(record);
  const highlights = buildDietShareHighlights(record);
  const foodItems = compactDietShareFoodItems(record.food_items);
  const lines = [
    `小巴饮食卡｜${headline}`,
    `今天这餐打卡: ${dateLabel}`,
    `${mealLabel}: ${foodItems}`,
    buildDietShareCaptionStatusLine(highlights),
    buildDietShareMacroLine(record, 'compact'),
  ];
  const macroStructureLine = buildDietShareMacroStructureLine(record);
  if (macroStructureLine) lines.push(macroStructureLine);
  if (shouldRenderHighlightCopy(highlights)) lines.push(`亮点: ${highlights.join(' / ')}`);
  if (record.fiber != null && !isLowConfidenceDietShare(record)) lines.push(`膳食纤维 ${metric(record.fiber, 1)}g`);
  lines.push(buildDietShareDataDisclosure(record));
  const confidenceDisclosure = buildDietShareConfidenceDisclosure(record);
  if (confidenceDisclosure) lines.push(confidenceDisclosure);
  lines.push('不是节食，是把身体照顾得更有章法。');
  lines.push('晒得出，也复盘得清楚。');
  lines.push('适合截图留档，也适合发给认真生活的朋友。');
  lines.push(buildDietShareHashtags(highlights));
  return lines.join('\n');
}

export function buildDietShareMomentsCaption(record: DietRecord, dateLabel: string): string {
  const mealLabel = MEAL_LABEL[record.meal_type] ?? '餐食';
  const headline = buildDietShareHeadline(record);
  const highlights = buildDietShareHighlights(record);
  const foodItems = compactDietShareFoodItems(record.food_items);
  const lines = [
    `${dateLabel}，${headline}。`,
    `${mealLabel}: ${foodItems}`,
    buildDietShareCaptionStatusLine(highlights),
    buildDietShareMacroLine(record, 'sentence'),
  ];
  const macroStructureLine = buildDietShareMacroStructureLine(record);
  if (macroStructureLine) lines.push(macroStructureLine);
  if (shouldRenderHighlightCopy(highlights)) lines.push(`亮点: ${highlights.join(' / ')}`);
  if (record.fiber != null && !isLowConfidenceDietShare(record)) lines.push(`膳食纤维 ${metric(record.fiber, 1)}g。`);
  lines.push(buildDietShareDataDisclosure(record));
  const confidenceDisclosure = buildDietShareConfidenceDisclosure(record);
  if (confidenceDisclosure) lines.push(confidenceDisclosure);
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

function publishHintForShareTarget(target: ShareTarget): { title: string; detail: string } {
  if (target === 'wechat') {
    return {
      title: '微信图片已生成，文案已复制',
      detail: '去微信或朋友圈选择图片后直接粘贴发布',
    };
  }
  if (target === 'xiaohongshu') {
    return {
      title: '小红书图片已生成，文案已复制',
      detail: '去小红书选择图片后直接粘贴发布',
    };
  }
  return {
    title: '分享图已生成',
    detail: '可在系统面板保存到相册或继续转发',
  };
}

function publishHintForReviewResult(result: ShareResult, reviewTone: Exclude<ShareReviewTone, 'none'>): { title: string; detail: string; icon: keyof typeof Ionicons.glyphMap; tone: 'success' | 'warning' } | null {
  const isLowConfidence = reviewTone === 'low-confidence';
  if (result.kind === 'caption_fallback') {
    return {
      title: isLowConfidence ? '图片没生成，核对文案已复制' : '图片没生成，复盘文案已复制',
      detail: isLowConfidence
        ? '先核对食物和份量，或点“保存/分享复盘图”重试生成核对图'
        : '可继续核对后，点“保存/分享复盘图”重试生成复盘图',
      icon: 'alert-circle',
      tone: 'warning',
    };
  }
  if (result.kind === 'saved_to_library') {
    return {
      title: isLowConfidence ? '核对素材已保存，文案已复制' : '复盘素材已保存，文案已复制',
      detail: isLowConfidence
        ? '先核对食物和份量，再从相册选择图片发布'
        : '可继续核对后，再从相册选择图片发布',
      icon: 'alert-circle',
      tone: isLowConfidence ? 'warning' : 'success',
    };
  }
  if (result.kind !== 'completed') return null;
  const targetDetail = result.target === 'xiaohongshu'
    ? `${isLowConfidence ? '先核对食物和份量' : '可继续核对后'}，再去小红书选择图片发布`
    : result.target === 'wechat'
      ? `${isLowConfidence ? '先核对食物和份量' : '可继续核对后'}，再去微信或朋友圈选择图片发布`
      : `${isLowConfidence ? '先核对食物和份量' : '可继续核对后'}，再从系统面板保存或转发`;
  return {
    title: isLowConfidence ? '核对素材已准备，文案已复制' : '复盘素材已准备，文案已复制',
    detail: targetDetail,
    icon: 'alert-circle',
    tone: isLowConfidence ? 'warning' : 'success',
  };
}

function publishHintForShareResult(result: ShareResult, reviewTone: ShareReviewTone = 'none'): { title: string; detail: string; icon: keyof typeof Ionicons.glyphMap; tone: 'success' | 'warning' } {
  if (reviewTone !== 'none') {
    const reviewHint = publishHintForReviewResult(result, reviewTone);
    if (reviewHint) return reviewHint;
  }
  if (result.kind === 'caption_fallback') {
    return {
      title: '图片没生成，文案已复制',
      detail: '先发文案，或点“保存/分享图片”重试生成高清图',
      icon: 'alert-circle',
      tone: 'warning',
    };
  }
  if (result.kind === 'saved_to_library') {
    return {
      title: '图片已保存到相册，文案已复制',
      detail: '去微信或小红书选择这张图片，再直接粘贴发布',
      icon: 'checkmark-circle',
      tone: 'success',
    };
  }
  if (result.kind === 'photo_library_permission_denied') {
    return {
      title: '需要相册权限',
      detail: '允许访问相册后，再保存高清分享图',
      icon: 'alert-circle',
      tone: 'warning',
    };
  }
  return {
    ...publishHintForShareTarget(result.target),
    icon: 'checkmark-circle',
    tone: 'success',
  };
}

export type DietShareCardProps = {
  record: DietShareRecord;
  dateLabel: string;
  imageSource: ImageSourcePropType;
  redactions?: DietShareRedaction[];
  onImageReady?: () => void;
  onImageError?: () => void;
};

export default function DietShareCard({
  record,
  dateLabel,
  imageSource,
  redactions = [],
  onImageReady,
  onImageError,
}: DietShareCardProps) {
  const presentation = buildDietSharePresentation(record);
  const tags = presentation.tags.slice(0, 3);
  const macroLines = presentation.macroLines.slice(0, 2);
  const showDisclosure = !macroLines.includes(presentation.disclosure);

  return (
    <View testID="diet-share-poster" style={styles.card}>
      <View testID="diet-share-photo-frame" style={styles.posterPhotoFrame}>
        <View testID="diet-share-photo-media" style={styles.posterPhotoMedia}>
          <Image
            testID="diet-share-image"
            source={imageSource}
            style={styles.posterPhoto}
            contentFit="contain"
            cachePolicy="memory-disk"
            priority="high"
            onDisplay={onImageReady}
            onError={onImageError}
          />
          <DietPrivacyRedactionOverlay redactions={redactions} />
          <View style={styles.posterPhotoShade} pointerEvents="none" />
        </View>
        <View style={styles.posterPhotoMeta} pointerEvents="none">
          <View style={styles.posterMealBadge}>
            <Text style={styles.posterMealBadgeText}>{presentation.mealLabel}</Text>
          </View>
          <Text style={styles.posterDate}>{dateLabel}</Text>
        </View>
      </View>

      <View testID="diet-share-poster-copy" style={styles.posterCopy}>
        <View style={styles.posterRuleRow}>
          <View style={styles.posterRuleLong} />
          <View style={styles.posterRuleShort} />
        </View>
        <Text testID="diet-share-headline" style={styles.posterHeadline} numberOfLines={1}>{presentation.headline}</Text>
        <Text testID="diet-share-food-line" style={styles.posterFoodLine} numberOfLines={2}>{presentation.foodLine}</Text>

        <View style={styles.posterNutrition}>
          {macroLines.map(line => (
            <Text key={line} style={styles.posterMacroLine} numberOfLines={1}>{line}</Text>
          ))}
        </View>

        {tags.length > 0 ? (
          <View style={styles.posterTagRow}>
            {tags.map((tag, index) => (
              <View key={`${tag}:${index}`} testID={`diet-share-tag-${index}`} style={styles.posterTag}>
                <Text style={styles.posterTagText}>{tag}</Text>
              </View>
            ))}
          </View>
        ) : null}

        <View style={styles.posterFooter}>
          {presentation.nextAction ? (
            <View testID="diet-share-next-action" style={styles.posterNextAction}>
              <View style={styles.posterNextActionDot} />
              <Text style={styles.posterNextActionText} numberOfLines={1}>{presentation.nextAction}</Text>
            </View>
          ) : <View />}
          {showDisclosure ? (
            <Text style={styles.posterDisclosure}>{presentation.disclosure}</Text>
          ) : null}
          <View style={styles.posterFooterMark}>
            <View style={styles.posterFooterMarkDot} />
            <View style={styles.posterFooterMarkLine} />
          </View>
        </View>
      </View>
    </View>
  );
}

function ShareReadyItem({ icon, label }: { icon: React.ComponentProps<typeof Ionicons>['name']; label: string }) {
  return (
    <View style={styles.shareReadyItem}>
      <Ionicons name={icon} size={14} color={C.green600} />
      <Text style={styles.shareReadyText}>{label}</Text>
    </View>
  );
}

export type DietShareSheetProps = {
  record: DietRecord;
  dateLabel: string;
  imageSource?: ImageSourcePropType;
  redactions?: DietShareRedaction[];
  visible: boolean;
  onClose: () => void;
  onAskReva?: () => void;
  onShareFeedback?: (hint: {
    title: string;
    detail: string;
    tone: 'success' | 'warning';
    result: ShareResult;
  }) => void;
  onShareTerminal?: (meta: {
    phase: 'completed' | 'failed';
    duration_ms: number;
    has_photo: boolean;
    share_target?: ShareTarget;
    error_code?: string;
  }) => void;
};

export function DietShareSheet({
  visible,
  record,
  dateLabel,
  imageSource,
  redactions = [],
  onClose,
  onAskReva,
  onShareFeedback,
  onShareTerminal,
}: DietShareSheetProps) {
  const cardRef = useRef<View>(null);
  const sharingRef = useRef(false);
  const imageRequestRef = useRef({ key: '', generation: 0 });
  const imageRequestKey = visible ? imageSourceIdentity(imageSource) : 'inactive';
  if (imageRequestRef.current.key !== imageRequestKey) {
    imageRequestRef.current = {
      key: imageRequestKey,
      generation: imageRequestRef.current.generation + 1,
    };
  }
  const imageRequestGeneration = imageRequestRef.current.generation;
  const [sharingAction, setSharingAction] = useState<ShareInFlight | null>(null);
  const [imageReadyGeneration, setImageReadyGeneration] = useState<number | null>(null);
  const [imageTimedOutGeneration, setImageTimedOutGeneration] = useState<number | null>(null);
  const [copiedCaption, setCopiedCaption] = useState<'moments' | 'xiaohongshu' | null>(null);
  const [shareResult, setShareResult] = useState<ShareResult | null>(null);
  const sharing = sharingAction !== null;
  const hasPhoto = Boolean(imageSource);
  const imageReady = imageReadyGeneration === imageRequestGeneration;
  const imageTimedOut = imageTimedOutGeneration === imageRequestGeneration;
  const imageCaptureAvailable = hasPhoto && imageReady && !imageTimedOut;
  const shareHasPhoto = imageCaptureAvailable;
  const lowConfidenceShare = isLowConfidenceDietShare(record);
  const estimatedShare = isAiEstimatedNutritionSource(record.source);
  const shareReviewTone: ShareReviewTone = lowConfidenceShare ? 'low-confidence' : estimatedShare ? 'estimate' : 'none';
  const publishHint = shareResult ? publishHintForShareResult(shareResult, shareReviewTone) : null;
  const sheetSubtitle = lowConfidenceShare
    ? '核对 3:4 图片 · 微信与小红书'
    : estimatedShare
      ? '复盘 3:4 图片 · 微信与小红书'
      : '高清 3:4 图片 · 微信与小红书';
  const momentsReadyLabel = lowConfidenceShare
    ? '核对后朋友圈文案'
    : estimatedShare
      ? '复盘朋友圈文案'
      : '朋友圈文案';
  const xhsReadyLabel = lowConfidenceShare
    ? '核对后小红书文案'
    : estimatedShare
      ? '复盘小红书文案'
      : '小红书话题';
  const wechatShareHint = lowConfidenceShare
    ? '先核对食物和份量'
    : estimatedShare
      ? '复制复盘朋友圈文案'
      : '自动复制朋友圈文案';
  const wechatShareLabel = lowConfidenceShare ? '核对后发微信/朋友圈' : '发微信/朋友圈';
  const wechatShareA11yLabel = lowConfidenceShare ? '核对后发微信或朋友圈' : '发微信或朋友圈';
  const xhsShareHint = lowConfidenceShare
    ? '核对后复制带话题文案'
    : estimatedShare
      ? '复制带话题复盘文案'
      : '自动复制带话题文案';
  const xhsShareLabel = lowConfidenceShare ? '核对后发小红书' : '发小红书';
  const wechatShareDisplayLabel = sharingAction === 'wechat' ? '生成微信图中' : wechatShareLabel;
  const xhsShareDisplayLabel = sharingAction === 'xiaohongshu' ? '生成小红书图中' : xhsShareLabel;
  const saveLibraryLabel = estimatedShare ? '保存复盘图到相册' : '保存到相册';
  const saveLibraryHint = lowConfidenceShare
    ? '核对后再存图发布'
    : estimatedShare
      ? '用于复盘或核对，确认后再发布'
      : '发布前先存图，微信 / 小红书直接选';
  const genericShareLabel = estimatedShare ? '保存/分享复盘图' : '保存/分享图片';
  const genericShareHint = lowConfidenceShare
    ? '系统面板里先保存，核对后再发'
    : estimatedShare
      ? '系统面板里保存或发给自己复盘'
      : '可在系统面板保存到相册';
  const copyMomentsLabel = lowConfidenceShare
    ? '核对后复制朋友圈文案'
    : estimatedShare
      ? '复制朋友圈复盘文案'
      : '复制朋友圈文案';
  const copiedMomentsLabel = lowConfidenceShare
    ? '已复制核对朋友圈文案'
    : estimatedShare
      ? '已复制朋友圈复盘文案'
      : '已复制朋友圈文案';
  const copyXhsLabel = lowConfidenceShare
    ? '核对后复制小红书文案'
    : estimatedShare
      ? '复制小红书复盘文案'
      : '复制小红书文案';
  const copiedXhsLabel = lowConfidenceShare
    ? '已复制核对小红书文案'
    : estimatedShare
      ? '已复制小红书复盘文案'
      : '已复制小红书文案';

  React.useEffect(() => {
    setImageReadyGeneration(null);
    setImageTimedOutGeneration(null);
    setCopiedCaption(null);
    setShareResult(null);
  }, [imageRequestKey]);

  React.useEffect(() => {
    if (!visible || !imageSource || imageReady) return undefined;
    const timeout = setTimeout(() => {
      if (imageRequestGeneration !== imageRequestRef.current.generation) return;
      setImageTimedOutGeneration(imageRequestGeneration);
    }, DIET_SHARE_IMAGE_TIMEOUT_MS);
    return () => clearTimeout(timeout);
  }, [imageReady, imageRequestGeneration, imageRequestKey, imageSource, visible]);

  const shareTextFallback = async (target: ShareTarget = 'generic') => {
    await Share.share({
      title: dialogTitleForShareTarget(target),
      message: captionForShareTarget(record, dateLabel, target),
    });
  };

  const publishShareResult = (result: ShareResult) => {
    setShareResult(result);
    const hint = publishHintForShareResult(result, shareReviewTone);
    onShareFeedback?.({
      title: hint.title,
      detail: hint.detail,
      tone: hint.tone,
      result,
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
      const isMoments = kind === 'moments';
      onShareFeedback?.({
        title: lowConfidenceShare
          ? '核对文案已复制'
          : estimatedShare
            ? '复盘文案已复制'
            : isMoments
              ? '朋友圈文案已复制'
              : '小红书文案已复制',
        detail: lowConfidenceShare
          ? isMoments
            ? '先核对食物和份量，再去微信或朋友圈粘贴'
            : '先核对食物和份量，再去小红书正文框粘贴'
          : estimatedShare
            ? isMoments
              ? '可继续核对后，再去微信或朋友圈粘贴'
              : '可继续核对后，再去小红书正文框粘贴'
          : isMoments
            ? '去微信或朋友圈直接粘贴发布'
            : '去小红书正文框直接粘贴发布',
        tone: lowConfidenceShare ? 'warning' : 'success',
        result: {
          target: isMoments ? 'wechat' : 'xiaohongshu',
          kind: 'completed',
        },
      });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      Alert.alert('复制失败', '请稍后重试');
    }
  };

  const handleShare = async (target: ShareTarget = 'generic') => {
    if (sharingRef.current || !imageCaptureAvailable || !cardRef.current) return;
    sharingRef.current = true;
    const startedAt = Date.now();
    let captureUri: string | null = null;
    setSharingAction(target);
    try {
      await Clipboard.setStringAsync(captionForShareTarget(record, dateLabel, target));
      if (!await Sharing.isAvailableAsync()) {
        await shareTextFallback(target);
        onShareTerminal?.({
          phase: 'completed',
          duration_ms: Date.now() - startedAt,
          has_photo: false,
          share_target: target,
        });
        publishShareResult({ target, kind: 'caption_fallback' });
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
        has_photo: shareHasPhoto,
        share_target: target,
      });
      publishShareResult({ target, kind: 'completed' });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      try {
        await shareTextFallback(target);
        onShareTerminal?.({
          phase: 'failed',
          duration_ms: Date.now() - startedAt,
          has_photo: false,
          share_target: target,
          error_code: 'image_share_fell_back_to_caption',
        });
        publishShareResult({ target, kind: 'caption_fallback' });
      } catch {
        setShareResult(null);
        onShareTerminal?.({
          phase: 'failed',
          duration_ms: Date.now() - startedAt,
          has_photo: shareHasPhoto,
          share_target: target,
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
      sharingRef.current = false;
      setSharingAction(null);
    }
  };

  const handleSaveToLibrary = async () => {
    if (sharingRef.current || !imageCaptureAvailable || !cardRef.current) return;
    sharingRef.current = true;
    const startedAt = Date.now();
    let captureUri: string | null = null;
    setSharingAction('library');
    try {
      const permission = await MediaLibrary.requestPermissionsAsync(true);
      if (!permission.granted && permission.status !== 'granted') {
        onShareTerminal?.({
          phase: 'failed',
          duration_ms: Date.now() - startedAt,
          has_photo: shareHasPhoto,
          share_target: 'generic',
          error_code: 'photo_library_permission_denied',
        });
        publishShareResult({ target: 'generic', kind: 'photo_library_permission_denied' });
        return;
      }
      const dimensions = dietShareCaptureDimensions();
      captureUri = await captureRef(cardRef, {
        format: 'png',
        quality: 1,
        ...dimensions,
        result: 'tmpfile',
      });
      await MediaLibrary.saveToLibraryAsync(captureUri);
      await Clipboard.setStringAsync(buildDietShareCaption(record, dateLabel));
      setCopiedCaption('xiaohongshu');
      onShareTerminal?.({
        phase: 'completed',
        duration_ms: Date.now() - startedAt,
        has_photo: shareHasPhoto,
        share_target: 'generic',
      });
      publishShareResult({ target: 'generic', kind: 'saved_to_library' });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    } catch {
      setShareResult(null);
      onShareTerminal?.({
        phase: 'failed',
        duration_ms: Date.now() - startedAt,
        has_photo: shareHasPhoto,
        share_target: 'generic',
        error_code: 'image_save_failed',
      });
      Alert.alert('保存失败', '请检查相册权限，或先使用“保存/分享图片”。');
    } finally {
      if (captureUri) {
        try {
          releaseCapture(captureUri);
        } catch {
          // Temporary-file cleanup is best effort after the image is saved.
        }
      }
      sharingRef.current = false;
      setSharingAction(null);
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
              <Text style={styles.sheetSubtitle}>{sheetSubtitle}</Text>
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
            {imageSource ? (
              <View ref={cardRef} collapsable={false} style={styles.captureSurface}>
                <DietShareCard
                  key={imageRequestGeneration}
                  record={record}
                  dateLabel={dateLabel}
                  imageSource={imageSource}
                  redactions={redactions}
                  onImageReady={() => {
                    if (imageRequestGeneration !== imageRequestRef.current.generation) return;
                    setImageTimedOutGeneration(null);
                    setImageReadyGeneration(imageRequestGeneration);
                  }}
                  onImageError={() => {
                    if (imageRequestGeneration !== imageRequestRef.current.generation) return;
                    setImageReadyGeneration(null);
                    setImageTimedOutGeneration(imageRequestGeneration);
                  }}
                />
              </View>
            ) : (
              <View style={styles.photoUnavailablePanel}>
                <Ionicons name="image-outline" size={28} color={C.ink3} />
                <Text style={styles.photoUnavailableTitle}>没有可编辑的餐食照片，当前只能分享正文</Text>
                <Text style={styles.photoUnavailableDetail}>返回餐食记录补充照片，或复制下方文案。</Text>
              </View>
            )}
          </View>

          {imageTimedOut ? (
            <View style={styles.photoErrorStrip}>
              <Ionicons name="alert-circle-outline" size={15} color={revaSemantic.caution.fg} />
              <Text style={styles.photoErrorText}>照片加载失败，请重试或改为分享正文</Text>
            </View>
          ) : null}

          <View
            style={styles.shareReadyStrip}
            accessibilityLabel={lowConfidenceShare ? '核对素材已准备完成' : '分享素材已准备完成'}
          >
            <ShareReadyItem
              icon="image-outline"
              label={!hasPhoto || imageTimedOut ? '图片暂不可用' : lowConfidenceShare ? '3:4 核对图' : '3:4 高清图'}
            />
            <ShareReadyItem
              icon="chatbubble-ellipses-outline"
              label={momentsReadyLabel}
            />
            <ShareReadyItem
              icon="sparkles-outline"
              label={xhsReadyLabel}
            />
          </View>

          <View style={styles.platformShareRow}>
            <TouchableOpacity
              style={[styles.platformShareButton, styles.wechatShareButton, (sharing || !imageCaptureAvailable) && styles.shareButtonDisabled]}
              onPress={() => handleShare('wechat')}
              disabled={sharing || !imageCaptureAvailable}
              activeOpacity={0.84}
              accessibilityRole="button"
              accessibilityLabel={wechatShareA11yLabel}
            >
              <SocialBrandIcon brand="wechat" size={15} />
              <View>
                <Text style={styles.platformShareText}>{wechatShareDisplayLabel}</Text>
                <Text style={styles.platformShareHint}>{wechatShareHint}</Text>
              </View>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.platformShareButton, styles.xhsShareButton, (sharing || !imageCaptureAvailable) && styles.shareButtonDisabled]}
              onPress={() => handleShare('xiaohongshu')}
              disabled={sharing || !imageCaptureAvailable}
              activeOpacity={0.84}
              accessibilityRole="button"
              accessibilityLabel={xhsShareLabel}
            >
              <SocialBrandIcon brand="xiaohongshu" size={15} />
              <View>
                <Text style={styles.platformShareText}>{xhsShareDisplayLabel}</Text>
                <Text style={styles.platformShareHint}>{xhsShareHint}</Text>
              </View>
            </TouchableOpacity>
          </View>

          {onAskReva ? (
            <>
              <View style={styles.databaseSavedStrip}>
                <View style={styles.databaseSavedItem}>
                  <Ionicons name="checkmark-circle" size={15} color={C.green600} />
                  <Text style={styles.databaseSavedTitle}>数据库已保存</Text>
                </View>
                <Text style={styles.databaseSavedText}>复盘会读取数据库快照</Text>
              </View>
              <TouchableOpacity
                style={styles.agentReviewButton}
                onPress={onAskReva}
                disabled={sharing}
                activeOpacity={0.82}
                accessibilityRole="button"
                accessibilityLabel="问小巴复盘今日饮食"
              >
                <View style={styles.agentReviewIcon}>
                  <Ionicons name="chatbubble-ellipses-outline" size={17} color={C.green600} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.agentReviewTitle}>问小巴复盘今日饮食</Text>
                  <Text style={styles.agentReviewSubtitle}>读取数据库记录，再看全天热量和下一餐</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={C.ink3} />
              </TouchableOpacity>
            </>
          ) : null}

          {publishHint ? (
            <View style={styles.publishHint} testID="diet-share-publish-hint">
              <Ionicons
                name={publishHint.icon}
                size={18}
                color={publishHint.tone === 'success' ? C.green600 : revaSemantic.caution.fg}
              />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={[
                  styles.publishHintTitle,
                  publishHint.tone === 'warning' && styles.publishHintTitleWarning,
                ]}>{publishHint.title}</Text>
                <Text style={styles.publishHintDetail}>{publishHint.detail}</Text>
              </View>
            </View>
          ) : null}

          <TouchableOpacity
            style={[styles.saveLibraryButton, (sharing || !imageCaptureAvailable) && styles.shareButtonDisabled]}
            onPress={handleSaveToLibrary}
            disabled={sharing || !imageCaptureAvailable}
            activeOpacity={0.84}
            accessibilityRole="button"
            accessibilityLabel="保存饮食图片到相册"
          >
            {sharingAction === 'library' || (hasPhoto && !imageReady && !imageTimedOut) ? (
              <ActivityIndicator size="small" color={C.green600} />
            ) : (
              <Ionicons name={imageCaptureAvailable ? 'download-outline' : 'image-outline'} size={19} color={C.green600} />
            )}
            <View style={styles.shareButtonCopy}>
              <Text style={styles.saveLibraryButtonText}>
                {!hasPhoto || imageTimedOut ? '图片暂不可用' : !imageReady ? '图片加载中' : sharingAction === 'library' ? '存图中' : saveLibraryLabel}
              </Text>
              {!sharing && imageCaptureAvailable ? (
                <Text style={styles.saveLibraryButtonHint}>{saveLibraryHint}</Text>
              ) : null}
            </View>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.shareButton, (sharing || !imageCaptureAvailable) && styles.shareButtonDisabled]}
            onPress={() => handleShare('generic')}
            disabled={sharing || !imageCaptureAvailable}
            activeOpacity={0.84}
            accessibilityRole="button"
            accessibilityLabel="保存或分享饮食图片"
          >
            {sharingAction === 'generic' || (hasPhoto && !imageReady && !imageTimedOut) ? (
              <ActivityIndicator size="small" color={C.greenOn} />
            ) : (
              <Ionicons name={imageCaptureAvailable ? 'share-outline' : 'document-text-outline'} size={19} color={C.greenOn} />
            )}
            <View style={styles.shareButtonCopy}>
              <Text style={styles.shareButtonText}>
                {!hasPhoto || imageTimedOut ? '请使用下方正文分享' : !imageReady ? '图片加载中' : sharingAction === 'generic' ? '生成中' : genericShareLabel}
              </Text>
              {!sharing && imageCaptureAvailable ? (
                <Text style={styles.shareButtonHint}>{genericShareHint}</Text>
              ) : null}
            </View>
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
                {copiedCaption === 'moments' ? copiedMomentsLabel : copyMomentsLabel}
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
                {copiedCaption === 'xiaohongshu' ? copiedXhsLabel : copyXhsLabel}
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
    backgroundColor: C.paper2,
    overflow: 'hidden',
  },
  posterPhotoFrame: {
    width: '100%',
    height: '100%',
    position: 'absolute',
    overflow: 'hidden',
    backgroundColor: C.lineStrong,
  },
  posterPhotoMedia: {
    width: '100%',
    height: '100%',
    aspectRatio: 3 / 4,
    position: 'relative',
    overflow: 'hidden',
    backgroundColor: C.lineStrong,
  },
  posterPhoto: {
    ...StyleSheet.absoluteFillObject,
  },
  posterPhotoShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(44, 31, 18, 0.06)',
  },
  posterPhotoMeta: {
    position: 'absolute',
    top: 14,
    left: 15,
    right: 15,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  posterMealBadge: {
    minHeight: 26,
    paddingHorizontal: 11,
    justifyContent: 'center',
    borderRadius: 13,
    borderCurve: 'continuous',
    backgroundColor: 'rgba(250, 243, 231, 0.92)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(99, 70, 40, 0.28)',
  },
  posterMealBadgeText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink2,
    fontWeight: '900',
    letterSpacing: 1.2,
  },
  posterDate: {
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.surface2,
    fontWeight: '800',
    textShadowColor: 'rgba(43, 29, 15, 0.55)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  posterCopy: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: '45%',
    paddingHorizontal: 20,
    paddingTop: 10,
    paddingBottom: 10,
    gap: 4,
    backgroundColor: C.paper2,
  },
  posterRuleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 3,
  },
  posterRuleLong: {
    width: 34,
    height: 3,
    borderRadius: 2,
    borderCurve: 'continuous',
    backgroundColor: revaSemantic.caution.fg,
  },
  posterRuleShort: {
    width: 7,
    height: 3,
    borderRadius: 2,
    borderCurve: 'continuous',
    backgroundColor: C.green600,
  },
  posterHeadline: {
    fontFamily: revaFonts.sans,
    fontSize: 20,
    lineHeight: 25,
    color: C.ink1,
    fontWeight: '900',
    letterSpacing: 0.2,
  },
  posterFoodLine: {
    fontFamily: revaFonts.sans,
    fontSize: 11.5,
    lineHeight: 16,
    color: C.ink2,
    fontWeight: '700',
  },
  posterNutrition: {
    paddingTop: 4,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(104, 76, 48, 0.2)',
    gap: 1,
  },
  posterMacroLine: {
    fontFamily: revaFonts.mono,
    fontSize: 12,
    lineHeight: 16,
    color: C.ink1,
    fontWeight: '700',
  },
  posterTagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  posterTag: {
    minHeight: 21,
    borderRadius: 11,
    borderCurve: 'continuous',
    justifyContent: 'center',
    paddingHorizontal: 9,
    backgroundColor: 'rgba(255, 250, 240, 0.72)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(82, 117, 93, 0.3)',
  },
  posterTagText: {
    fontFamily: revaFonts.sans,
    fontSize: 9.5,
    color: C.green700,
    fontWeight: '900',
  },
  posterFooter: {
    marginTop: 'auto',
    minHeight: 27,
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: 9,
  },
  posterNextAction: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  posterNextActionDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: revaSemantic.caution.fg,
  },
  posterNextActionText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 9.5,
    lineHeight: 13,
    color: C.ink2,
    fontWeight: '800',
  },
  posterDisclosure: {
    fontFamily: revaFonts.sans,
    fontSize: 8.5,
    lineHeight: 12,
    color: C.ink3,
    fontWeight: '700',
    textAlign: 'right',
  },
  posterFooterMark: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderCurve: 'continuous',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(82, 117, 93, 0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  posterFooterMarkDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: C.green600,
  },
  posterFooterMarkLine: {
    position: 'absolute',
    width: 9,
    height: 1,
    backgroundColor: 'rgba(82, 117, 93, 0.58)',
    transform: [{ rotate: '-35deg' }],
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
  confirmBadgeEstimate: {
    backgroundColor: '#FFF7E8',
    borderColor: '#F1D7A8',
  },
  confirmBadgePrimaryEstimate: { color: '#8A5B16' },
  confirmBadgeCaution: {
    backgroundColor: revaSemantic.caution.bg,
    borderColor: revaSemantic.caution.line,
  },
  confirmBadgePrimaryCaution: { color: revaSemantic.caution.fg },
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
  calorieAsidePending: {
    maxWidth: 58,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 15,
    color: revaSemantic.caution.fg,
    fontWeight: '900',
    textAlign: 'right',
  },
  macroSection: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    marginTop: 12,
    paddingTop: 10,
    paddingBottom: 9,
  },
  macroGrid: {
    flexDirection: 'row',
  },
  macroItem: { flex: 1, paddingHorizontal: 8, position: 'relative' },
  macroAccent: { width: 18, height: 3, borderRadius: 2, marginBottom: 6 },
  macroValue: { fontFamily: revaFonts.mono, fontSize: 15, color: C.ink1, fontWeight: '600' },
  macroLabel: { fontFamily: revaFonts.sans, fontSize: 9, color: C.ink3, marginTop: 2 },
  macroStructure: {
    marginTop: 9,
    borderRadius: 10,
    backgroundColor: '#F7F7F2',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E5E4DA',
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  macroStructureHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  macroStructureTitle: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink1, fontWeight: '900' },
  macroStructureMeta: { fontFamily: revaFonts.sans, fontSize: 8, color: C.ink3, fontWeight: '800' },
  macroStructureTrack: {
    height: 7,
    borderRadius: 4,
    backgroundColor: C.paper2,
    overflow: 'hidden',
    flexDirection: 'row',
    marginTop: 6,
  },
  macroStructureFill: { height: '100%', flexBasis: 0 },
  macroStructureLegend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 5,
    marginTop: 6,
  },
  macroStructureLegendItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  macroStructureDot: { width: 5, height: 5, borderRadius: 2.5 },
  macroStructureLegendText: { fontFamily: revaFonts.mono, fontSize: 8.5, color: C.ink2, fontWeight: '700' },
  pendingMacroPanel: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    marginTop: 14,
    paddingVertical: 12,
  },
  pendingMacroTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, fontWeight: '900' },
  pendingMacroText: { fontFamily: revaFonts.sans, fontSize: 10, lineHeight: 15, color: C.ink3, marginTop: 4 },
  balancePanel: {
    minHeight: 46,
    borderRadius: 12,
    backgroundColor: '#F8F4EC',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E9D9BE',
    marginTop: 10,
    paddingHorizontal: 11,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  balanceCopy: { flex: 1, minWidth: 0 },
  balanceLabel: { fontFamily: revaFonts.sans, fontSize: 8.5, color: '#B87921', fontWeight: '900' },
  balanceTitle: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 16, color: C.ink1, fontWeight: '900', marginTop: 1 },
  balanceScoreWrap: { width: 72, alignItems: 'flex-end' },
  balanceScore: { fontFamily: revaFonts.mono, fontSize: 23, lineHeight: 25, color: '#C66A23', fontWeight: '700' },
  balancePending: { fontFamily: revaFonts.sans, fontSize: 10, color: revaSemantic.caution.fg, fontWeight: '900' },
  balanceTrack: {
    width: 66,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(198,106,35,0.16)',
    overflow: 'hidden',
    marginTop: 3,
  },
  balanceFill: { height: '100%', borderRadius: 2, backgroundColor: '#C66A23' },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 11 },
  sourceText: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '800' },
  fiberText: { fontFamily: revaFonts.mono, fontSize: 9, color: C.ink3, marginLeft: 'auto' },
  confidencePanel: {
    minHeight: 34,
    borderRadius: 10,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: 7,
    paddingHorizontal: 10,
    paddingVertical: 6,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  confidencePanelWarning: {
    backgroundColor: revaSemantic.caution.bg,
    borderColor: revaSemantic.caution.line,
  },
  confidencePrimaryRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  confidencePrimary: { fontFamily: revaFonts.sans, fontSize: 9.5, color: C.green600, fontWeight: '900' },
  confidencePrimaryWarning: { color: revaSemantic.caution.fg },
  confidenceDetail: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 8.5,
    lineHeight: 11,
    color: C.ink3,
    fontWeight: '800',
    textAlign: 'right',
  },
  lifestylePanel: {
    minHeight: 45,
    borderRadius: 12,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: 10,
    paddingHorizontal: 11,
    paddingVertical: 8,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  lifestyleIcon: {
    width: 24,
    height: 24,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.72)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  lifestyleTitle: { fontFamily: revaFonts.sans, fontSize: 10.5, lineHeight: 14, color: C.focusInk1, fontWeight: '900' },
  lifestyleMeta: { fontFamily: revaFonts.sans, fontSize: 8.5, lineHeight: 12, color: C.focusInk2, fontWeight: '800', marginTop: 2 },
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
  photoUnavailablePanel: {
    flex: 1,
    paddingHorizontal: 28,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 9,
    backgroundColor: '#F7EAD7',
  },
  photoUnavailableTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    lineHeight: 20,
    color: C.ink2,
    fontWeight: '900',
    textAlign: 'center',
  },
  photoUnavailableDetail: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 16,
    color: C.ink3,
    fontWeight: '700',
    textAlign: 'center',
  },
  photoErrorStrip: {
    width: '100%',
    minHeight: 34,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 10,
    borderRadius: revaRadii.sm,
    borderCurve: 'continuous',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: revaSemantic.caution.bg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
  },
  photoErrorText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: revaSemantic.caution.fg,
    fontWeight: '800',
  },
  shareReadyStrip: {
    width: '100%',
    minHeight: 38,
    borderRadius: revaRadii.md,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: revaSpacing.s3,
    paddingHorizontal: 10,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  shareReadyItem: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
  },
  shareReadyText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.focusInk1,
    fontWeight: '800',
  },
  platformShareRow: {
    width: '100%',
    flexDirection: 'row',
    gap: 10,
    marginTop: revaSpacing.s3,
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
  databaseSavedStrip: {
    width: '100%',
    minHeight: 34,
    borderRadius: revaRadii.sm,
    backgroundColor: '#F0F8F3',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 11,
    paddingVertical: 7,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  databaseSavedItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    minWidth: 0,
  },
  databaseSavedTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.green700,
    fontWeight: '900',
  },
  databaseSavedText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    fontWeight: '700',
    textAlign: 'right',
  },
  agentReviewButton: {
    width: '100%',
    minHeight: 52,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  agentReviewIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: C.focusBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  agentReviewTitle: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink1, fontWeight: '900' },
  agentReviewSubtitle: { fontFamily: revaFonts.sans, fontSize: 10.5, color: C.ink3, fontWeight: '700', marginTop: 1 },
  publishHint: {
    width: '100%',
    minHeight: 46,
    borderRadius: revaRadii.md,
    backgroundColor: C.focusBg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.focusLine,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 12,
    paddingVertical: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  publishHintTitle: { fontFamily: revaFonts.sans, fontSize: 12.5, color: C.green600, fontWeight: '900' },
  publishHintTitleWarning: { color: revaSemantic.caution.fg },
  publishHintDetail: { fontFamily: revaFonts.sans, fontSize: 10.5, color: C.ink3, fontWeight: '700', marginTop: 1 },
  saveLibraryButton: {
    width: '100%',
    minHeight: 52,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    marginTop: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  saveLibraryButtonText: { fontFamily: revaFonts.sans, fontSize: 15, color: C.green700, fontWeight: '900' },
  saveLibraryButtonHint: { fontFamily: revaFonts.sans, fontSize: 10, color: C.green600, fontWeight: '700', marginTop: 1 },
  shareButton: {
    width: '100%',
    minHeight: 52,
    borderRadius: revaRadii.md,
    backgroundColor: C.ink2,
    marginTop: revaSpacing.s2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
  },
  shareButtonDisabled: { opacity: 0.72 },
  shareButtonCopy: { alignItems: 'center', justifyContent: 'center' },
  shareButtonText: { fontFamily: revaFonts.sans, fontSize: 15, color: C.greenOn, fontWeight: '800' },
  shareButtonHint: { fontFamily: revaFonts.sans, fontSize: 10, color: 'rgba(255,255,255,0.72)', fontWeight: '700', marginTop: 1 },
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
