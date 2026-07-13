/**
 * 菜单分享卡 — 后端 FuelStrategist 命中"今晚吃啥/明天早餐"等意图时下发.
 *
 * 协议 (后端 SSE done 事件 cards 数组):
 *   { type: "menu_share", data: { title, items[], totals?, reason?, shopping_list? } }
 *
 * - 餐次标题 + 一句话理由
 * - 食材表 (name / qty / kcal)
 * - 营养汇总
 * - 「分享给家人」按钮 → 系统分享 (微信/群/朋友圈)
 * - shopping_list 不在卡里渲染, 出现在分享文本末尾, 方便对方直接照单买
 */
import React from 'react';
import { View, Text, StyleSheet, TextStyle, Pressable } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { revaColors as C, revaRadii, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';

// 菜单/饮食类目 accent (橙) + 卡底 tint = 装饰色, 保留字面量 (= legacy orange/tintOrange).
const MENU_ACCENT = '#C97A2E';
const MENU_TINT = '#F6E9DA';

// 营养素装饰性 hue (蛋白粉/碳水琥珀/脂肪紫), 区分类目非临床好坏, 保留字面量.
const MACRO_PINK = '#C2487A';
const MACRO_AMBER = '#C98A1E';
const MACRO_PURPLE = '#7C5CBF';

interface MenuItem {
  name: string;
  qty?: string;
  kcal?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
}

interface MenuShareData {
  title: string;
  items: MenuItem[];
  totals?: { kcal?: number; protein?: number; carbs?: number; fat?: number; fiber?: number };
  reason?: string;
  shopping_list?: string[];
}

type MenuShareTarget = 'wechat' | 'xiaohongshu';

interface MenuSharePayload {
  title: string;
  message: string;
}

function buildWechatShareText(d: MenuShareData): string {
  const lines: string[] = [`【${d.title}】`];
  if (d.reason) lines.push(d.reason, '');
  for (const it of d.items) {
    const qty = it.qty ? ` · ${it.qty}` : '';
    const kcal = it.kcal != null ? `  ${Math.round(it.kcal)} kcal` : '';
    lines.push(`• ${it.name}${qty}${kcal}`);
  }
  if (d.totals) {
    const t = d.totals;
    const parts: string[] = [];
    if (t.kcal != null) parts.push(`${Math.round(t.kcal)} kcal`);
    if (t.protein != null) parts.push(`蛋白 ${t.protein.toFixed(0)}g`);
    if (t.carbs != null) parts.push(`碳水 ${t.carbs.toFixed(0)}g`);
    if (t.fat != null) parts.push(`脂肪 ${t.fat.toFixed(0)}g`);
    if (parts.length) lines.push('', `汇总: ${parts.join(' · ')}`);
  }
  if (d.shopping_list && d.shopping_list.length) {
    lines.push('', '买菜清单:');
    for (const s of d.shopping_list) lines.push(`· ${s}`);
  }
  lines.push('', '— 小巴');
  return lines.join('\n');
}

function buildMacroSummary(d: MenuShareData): string {
  const t = d.totals || {};
  const parts: string[] = [];
  if (t.kcal != null) parts.push(`${Math.round(t.kcal)} kcal`);
  if (t.protein != null) parts.push(`蛋白 ${t.protein.toFixed(0)}g`);
  if (t.carbs != null) parts.push(`碳水 ${t.carbs.toFixed(0)}g`);
  if (t.fat != null) parts.push(`脂肪 ${t.fat.toFixed(0)}g`);
  if (t.fiber != null) parts.push(`膳食纤维 ${t.fiber.toFixed(0)}g`);
  return parts.join(' · ');
}

function buildXiaohongshuShareText(d: MenuShareData): string {
  const title = d.title || '小巴菜单';
  const lines: string[] = [`📌 ${title}`];
  if (d.reason) lines.push(d.reason);

  const items = Array.isArray(d.items) ? d.items : [];
  if (items.length) {
    lines.push('', '🥗 吃什么');
    items.forEach((it, index) => {
      const qty = it.qty ? ` · ${it.qty}` : '';
      const kcal = it.kcal != null ? ` · ${Math.round(it.kcal)} kcal` : '';
      lines.push(`${index + 1}. ${it.name}${qty}${kcal}`);
    });
  }

  const macroSummary = buildMacroSummary(d);
  if (macroSummary) lines.push('', '📊 营养估算', macroSummary);

  if (d.shopping_list && d.shopping_list.length) {
    lines.push('', '🛒 备菜', d.shopping_list.join(' / '));
  }

  lines.push(
    '',
    '小巴给我配的轻负担菜单，适合想吃得清爽但不想瞎算的人。',
    '',
    '#饮食打卡 #健康饮食 #高蛋白饮食 #小巴健康',
  );
  return lines.join('\n');
}

export function buildSharePayload(d: MenuShareData, target: MenuShareTarget = 'wechat'): MenuSharePayload {
  if (target === 'xiaohongshu') {
    const kcal = d.totals?.kcal != null ? `${Math.round(d.totals.kcal)} kcal ` : '';
    const tag = (d.totals?.protein || 0) >= 25 ? '轻负担高蛋白' : '健康菜单';
    return {
      title: `${d.title || '小巴菜单'}｜${kcal}${tag}`.trim(),
      message: buildXiaohongshuShareText(d),
    };
  }

  return {
    title: d.title || '菜单分享',
    message: buildWechatShareText(d),
  };
}

export function buildShareText(d: MenuShareData): string {
  return buildSharePayload(d, 'wechat').message;
}

export function MenuShareCardView(d: MenuShareData) {
  const items = Array.isArray(d.items) ? d.items : [];
  const totals = d.totals || {};

  const handleShare = async (target: MenuShareTarget) => {
    Haptics.selectionAsync();
    try {
      const { sharePlainText } = await import('../../../utils/share');
      const payload = buildSharePayload(d, target);
      await sharePlainText({
        title: payload.title,
        message: payload.message,
      });
    } catch { /* noop */ }
  };

  const macros: { label: string; v?: number; color: string; unit: string }[] = [
    { label: '蛋白', v: totals.protein, color: MACRO_PINK, unit: 'g' },
    { label: '碳水', v: totals.carbs, color: MACRO_AMBER, unit: 'g' },
    { label: '脂肪', v: totals.fat, color: MACRO_PURPLE, unit: 'g' },
  ].filter(m => m.v != null);

  return (
    <CardShell icon="restaurant" iconColor={MENU_ACCENT} title={d.title || '菜单'} bg={MENU_TINT}>
      {d.reason ? (
        <Text maxFontSizeMultiplier={1.3} style={styles.reason}>
          {d.reason}
        </Text>
      ) : null}

      <View style={styles.itemList}>
        {items.map((it, i) => (
          <View key={i} style={styles.itemRow}>
            <View style={[styles.itemDot, { backgroundColor: MENU_ACCENT }]} />
            <Text maxFontSizeMultiplier={1.3} style={styles.itemName} numberOfLines={1} ellipsizeMode="tail">
              {it.name}
            </Text>
            {it.qty ? (
              <Text maxFontSizeMultiplier={1.3} style={styles.itemQty}>
                {it.qty}
              </Text>
            ) : null}
            {it.kcal != null ? (
              <Text maxFontSizeMultiplier={1.3} style={styles.itemKcal}>
                {Math.round(it.kcal)} kcal
              </Text>
            ) : null}
          </View>
        ))}
      </View>

      {totals.kcal != null && (
        <View style={styles.totalsRow}>
          <Text maxFontSizeMultiplier={1.3} style={styles.totalKcal}>
            {Math.round(totals.kcal)}
            <Text style={styles.totalKcalUnit}> kcal</Text>
          </Text>
          {macros.length > 0 && (
            <View style={styles.macros}>
              {macros.map(m => (
                <View key={m.label} style={styles.macroChip}>
                  <View style={[styles.macroDot, { backgroundColor: m.color }]} />
                  <Text maxFontSizeMultiplier={1.3} style={styles.macroLabel}>
                    {m.label}
                  </Text>
                  <Text maxFontSizeMultiplier={1.3} style={[styles.macroVal, { color: m.color }]}>
                    {m.v!.toFixed(0)}{m.unit}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      <View style={styles.shareActions}>
        <Pressable
          onPress={() => handleShare('wechat')}
          style={({ pressed }) => [styles.shareBtn, { backgroundColor: MENU_ACCENT }, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="logo-wechat" size={14} color="#fff" />
          <Text maxFontSizeMultiplier={1.2} style={styles.shareText}>微信/家人</Text>
        </Pressable>
        <Pressable
          onPress={() => handleShare('xiaohongshu')}
          style={({ pressed }) => [styles.shareBtn, styles.shareBtnSecondary, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="book-outline" size={14} color={MENU_ACCENT} />
          <Text maxFontSizeMultiplier={1.2} style={styles.shareTextSecondary}>小红书</Text>
        </Pressable>
      </View>
    </CardShell>
  );
}

export const MenuShareCardSpec: CardSpec<MenuShareData> = {
  type: 'menu_share',
  label: '菜单分享',
  // 不本地匹配, 只接受后端 SSE done 事件下发
  match: () => null,
  build: () => null,
  render: (d) => <MenuShareCardView {...d} />,
};

const styles = StyleSheet.create({
  itemList: { marginTop: 4, gap: 4, minWidth: 0 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  itemDot: { width: 4, height: 4, borderRadius: 2 },
  totalsRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 10,
    marginTop: 8, paddingTop: 6,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  macros: { flex: 1, minWidth: 0, flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 8 },
  macroChip: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  macroDot: { width: 5, height: 5, borderRadius: 2.5 },
  shareActions: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 },
  shareBtn: {
    flex: 1,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    minHeight: 36,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: revaRadii.md,
  },
  shareBtnSecondary: { backgroundColor: '#FFF8EF', borderWidth: StyleSheet.hairlineWidth, borderColor: '#E7C7A5' },
  reason: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: C.ink2, marginBottom: 4 } as TextStyle,
  itemName: { fontFamily: revaFonts.sans, flex: 1, minWidth: 0, fontSize: 13, fontWeight: '500', color: C.ink1 } as TextStyle,
  itemQty: { fontFamily: revaFonts.sans, flexShrink: 0, fontSize: 11, color: C.ink3 } as TextStyle,
  itemKcal: { fontFamily: revaFonts.mono, flexShrink: 0, fontSize: 11, fontWeight: '600', color: MENU_ACCENT, fontVariant: ['tabular-nums'] as const, textAlign: 'right' } as TextStyle,
  totalKcal: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  totalKcalUnit: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '400', color: C.ink3 } as TextStyle,
  macroLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  macroVal: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  shareText: { fontFamily: revaFonts.sans, fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
  shareTextSecondary: { fontFamily: revaFonts.sans, fontSize: 13, color: MENU_ACCENT, fontWeight: '700' } as TextStyle,
});
