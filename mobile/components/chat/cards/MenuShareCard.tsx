/**
 * 菜单分享卡 — 后端 FuelStrategist 命中"今晚吃啥/明天早餐"等意图时下发.
 *
 * 协议 (后端 SSE done 事件 cards 数组):
 *   { type: "menu_share", data: { title, items[], totals?, reason?, shopping_list? } }
 *
 * - 餐次标题 + 一句话理由
 * - 食材表 (name / qty / kcal)
 * - 营养汇总
 * - 「发微信 / 发小红书 / 更多」按钮 → 系统分享 (微信/群/朋友圈/小红书)
 * - shopping_list 不在卡里渲染, 出现在分享文本末尾, 方便对方直接照单买
 */
import React from 'react';
import { View, Text, StyleSheet, TextStyle, Pressable } from 'react-native';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import { revaColors as C, revaRadii, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import { sharePlainCaption, sharePlainText } from '../../../utils/share';

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
  fiber?: number;
}

interface MenuShareData {
  title: string;
  items: MenuItem[];
  totals?: { kcal?: number; protein?: number; carbs?: number; fat?: number; fiber?: number };
  reason?: string;
  shopping_list?: string[];
}

export function buildShareText(d: MenuShareData): string {
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

export function buildXiaohongshuShareText(d: MenuShareData): string {
  const lines: string[] = [
    '小巴给我的一餐建议',
    '',
    `这餐: ${d.title || '这一餐'}`,
  ];
  if (d.reason) lines.push(`为什么这样搭: ${d.reason}`);
  const items = Array.isArray(d.items) ? d.items : [];
  if (items.length > 0) {
    lines.push('', '吃什么:');
    for (const [index, it] of items.entries()) {
      const parts = [
        it.name,
        it.qty,
        it.kcal != null ? `${Math.round(it.kcal)} kcal` : null,
        it.protein != null ? `蛋白 ${it.protein.toFixed(0)}g` : null,
      ].filter(Boolean);
      lines.push(`${index + 1}. ${parts.join(' · ')}`);
    }
  }
  if (d.totals) {
    const t = d.totals;
    const parts: string[] = [];
    if (t.kcal != null) parts.push(`${Math.round(t.kcal)} kcal`);
    if (t.protein != null) parts.push(`蛋白 ${t.protein.toFixed(0)}g`);
    if (t.carbs != null) parts.push(`碳水 ${t.carbs.toFixed(0)}g`);
    if (t.fat != null) parts.push(`脂肪 ${t.fat.toFixed(0)}g`);
    if (t.fiber != null) parts.push(`纤维 ${t.fiber.toFixed(0)}g`);
    if (parts.length) lines.push('', `营养概览：${parts.join(' · ')}`);
  }
  const shoppingList = Array.isArray(d.shopping_list) ? d.shopping_list.filter(Boolean) : [];
  if (shoppingList.length > 0) {
    lines.push('', `买菜清单: ${shoppingList.join(' / ')}`);
  }
  lines.push(
    '',
    '仅作健康管理参考，不替代医生诊疗。',
    '#小巴饮食建议 #健康饮食 #饮食记录',
  );
  return lines.join('\n');
}

export function MenuShareCardView(d: MenuShareData) {
  const items = Array.isArray(d.items) ? d.items : [];
  const totals = d.totals || {};

  const handleShare = async (target: 'wechat' | 'xiaohongshu' | 'more' = 'more') => {
    Haptics.selectionAsync();
    try {
      if (target === 'xiaohongshu') {
        await sharePlainCaption({
          title: `${d.title || '菜单分享'} · 小红书文案`,
          message: buildXiaohongshuShareText(d),
        });
        return;
      }
      await sharePlainText({ title: d.title || '菜单分享', message: buildShareText(d) });
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
            <Text maxFontSizeMultiplier={1.25} style={styles.itemName}>
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
          accessibilityRole="button"
          accessibilityLabel="发微信分享菜单"
          style={({ pressed }) => [styles.wechatShareBtn, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="logo-wechat" size={14} color="#fff" />
          <Text maxFontSizeMultiplier={1.2} style={styles.wechatShareText}>发微信</Text>
        </Pressable>
        <Pressable
          onPress={() => handleShare('xiaohongshu')}
          accessibilityRole="button"
          accessibilityLabel="发小红书分享菜单"
          style={({ pressed }) => [styles.xhsShareBtn, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="book-outline" size={14} color={MENU_ACCENT} />
          <Text maxFontSizeMultiplier={1.2} style={styles.xhsShareText}>发小红书</Text>
        </Pressable>
        <Pressable
          onPress={() => handleShare('more')}
          accessibilityRole="button"
          accessibilityLabel="更多分享菜单"
          style={({ pressed }) => [styles.moreShareBtn, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="share-social-outline" size={14} color={C.ink2} />
          <Text maxFontSizeMultiplier={1.2} style={styles.moreShareText}>更多</Text>
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
  shareActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
  },
  wechatShareBtn: {
    minHeight: 32,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: '#1AAD19',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  xhsShareBtn: {
    minHeight: 32,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#E7CDB7',
    backgroundColor: '#FFF8F1',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  moreShareBtn: {
    minHeight: 32,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.paper,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  reason: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 17, color: C.ink2, marginBottom: 4 } as TextStyle,
  itemName: { fontFamily: revaFonts.sans, flex: 1, minWidth: 0, fontSize: 13, fontWeight: '500', color: C.ink1 } as TextStyle,
  itemQty: { fontFamily: revaFonts.sans, flexShrink: 0, fontSize: 11, color: C.ink3 } as TextStyle,
  itemKcal: { fontFamily: revaFonts.mono, flexShrink: 0, fontSize: 11, fontWeight: '600', color: MENU_ACCENT, fontVariant: ['tabular-nums'] as const, textAlign: 'right' } as TextStyle,
  totalKcal: { fontFamily: revaFonts.mono, fontSize: 18, fontWeight: '800', color: C.ink1, fontVariant: ['tabular-nums'] as const } as TextStyle,
  totalKcalUnit: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '400', color: C.ink3 } as TextStyle,
  macroLabel: { fontFamily: revaFonts.sans, fontSize: 10, color: C.ink2 } as TextStyle,
  macroVal: { fontFamily: revaFonts.mono, fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  wechatShareText: { fontFamily: revaFonts.sans, fontSize: 12.5, color: '#fff', fontWeight: '800' } as TextStyle,
  xhsShareText: { fontFamily: revaFonts.sans, fontSize: 12.5, color: MENU_ACCENT, fontWeight: '800' } as TextStyle,
  moreShareText: { fontFamily: revaFonts.sans, fontSize: 12.5, color: C.ink2, fontWeight: '700' } as TextStyle,
});
