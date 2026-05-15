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
import { colors, radii } from '../../../constants/theme';
import type { CardSpec } from './types';
import { sharePlainText } from '../../../utils/share';

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

function buildShareText(d: MenuShareData): string {
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
  lines.push('', '— 健康 Agent');
  return lines.join('\n');
}

export function MenuShareCardView(d: MenuShareData) {
  const items = Array.isArray(d.items) ? d.items : [];
  const totals = d.totals || {};

  const handleShare = async () => {
    Haptics.selectionAsync();
    try {
      await sharePlainText({
        title: d.title || '菜单分享',
        message: buildShareText(d),
      });
    } catch { /* noop */ }
  };

  const macros: { label: string; v?: number; color: string; unit: string }[] = [
    { label: '蛋白', v: totals.protein, color: '#FF375F', unit: 'g' },
    { label: '碳水', v: totals.carbs, color: '#FF9F0A', unit: 'g' },
    { label: '脂肪', v: totals.fat, color: '#BF5AF2', unit: 'g' },
  ].filter(m => m.v != null);

  return (
    <CardShell icon="restaurant" iconColor="#FF6723" title={d.title || '菜单'} bg="#FFF7F0">
      {d.reason ? <Text style={txt.reason}>{d.reason}</Text> : null}

      <View style={styles.itemList}>
        {items.map((it, i) => (
          <View key={i} style={styles.itemRow}>
            <View style={styles.itemDot} />
            <Text style={txt.itemName} numberOfLines={1}>{it.name}</Text>
            {it.qty ? <Text style={txt.itemQty}>{it.qty}</Text> : null}
            {it.kcal != null ? <Text style={txt.itemKcal}>{Math.round(it.kcal)} kcal</Text> : null}
          </View>
        ))}
      </View>

      {totals.kcal != null && (
        <View style={styles.totalsRow}>
          <Text style={txt.totalKcal}>
            {Math.round(totals.kcal)}<Text style={txt.totalKcalUnit}> kcal</Text>
          </Text>
          {macros.length > 0 && (
            <View style={styles.macros}>
              {macros.map(m => (
                <View key={m.label} style={styles.macroChip}>
                  <View style={[styles.macroDot, { backgroundColor: m.color }]} />
                  <Text style={txt.macroLabel}>{m.label}</Text>
                  <Text style={[txt.macroVal, { color: m.color }]}>{m.v!.toFixed(0)}{m.unit}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}

      <Pressable onPress={handleShare} style={({ pressed }) => [styles.shareBtn, pressed && { opacity: 0.85 }]}>
        <Ionicons name="share-social-outline" size={14} color="#fff" />
        <Text style={txt.shareText}>分享给家人</Text>
      </Pressable>
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
  itemList: { marginTop: 4, gap: 4 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  itemDot: { width: 4, height: 4, borderRadius: 2, backgroundColor: '#FF6723' },
  totalsRow: {
    flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between',
    marginTop: 8, paddingTop: 6,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: 'rgba(0,0,0,0.08)',
  },
  macros: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  macroChip: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  macroDot: { width: 5, height: 5, borderRadius: 2.5 },
  shareBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    marginTop: 10, paddingVertical: 8,
    borderRadius: radii.md, backgroundColor: '#FF6723',
  },
});

const txt = {
  reason: { fontSize: 12, color: colors.labelSecondary, lineHeight: 17, marginBottom: 4 } as TextStyle,
  itemName: { flex: 1, fontSize: 13, color: colors.labelPrimary, fontWeight: '500' } as TextStyle,
  itemQty: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  itemKcal: { fontSize: 11, color: '#FF6723', fontWeight: '600', fontVariant: ['tabular-nums'] as const, textAlign: 'right' } as TextStyle,
  totalKcal: { fontSize: 18, fontWeight: '800', color: colors.labelPrimary, fontVariant: ['tabular-nums'] as const } as TextStyle,
  totalKcalUnit: { fontSize: 11, fontWeight: '400', color: colors.labelTertiary } as TextStyle,
  macroLabel: { fontSize: 10, color: colors.labelSecondary } as TextStyle,
  macroVal: { fontSize: 11, fontWeight: '700', fontVariant: ['tabular-nums'] as const } as TextStyle,
  shareText: { fontSize: 13, color: '#fff', fontWeight: '700' } as TextStyle,
};
