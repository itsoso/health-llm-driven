/**
 * /supplement-inventory —— 补剂库存管理 (P3 · proactive-planning PRD §3.D, D1).
 *
 * 列出每个补剂的剩余天数 + 状态(ok / low / unknown)。「补货」登记到货数量,
 * 「校正剩余」手动纠错剩余量。复购**提醒**本身通过首页 WriteIntentCard 的
 * reorder_nudge 出现 —— 本页只做库存登记与展示。
 *
 * ⚠️ 范围:检测 + 提醒展示 + 库存录入。**无下单 / 购买 / 支付**(D2/P5)。
 * 全程 hedged 物流语气(「约 N 天」),不是医疗建议。
 */
import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';

import { revaColors as C, revaRadii } from '../constants/revaTheme';
import { Card, Icon, SectionLabel } from '../components/reva/RevaKit';
import {
  useRestockSupplement,
  useSetUnitsRemaining,
  useSupplementInventory,
} from '../hooks/useSupplementInventory';
import type { InventoryItem } from '../services/supplementInventory';

// 剩余天数四舍五入展示;null 不编造(显示「未记录」)。
function roundDays(d: number | null): number | null {
  if (d == null || !Number.isFinite(d)) return null;
  return Math.max(0, Math.round(d));
}

type SheetMode = 'restock' | 'correct';

function StatusLine({ item }: { item: InventoryItem }) {
  const days = roundDays(item.days_remaining);
  if (item.status === 'low') {
    return (
      <Text style={[styles.statusLine, styles.statusLow]} numberOfLines={2}>
        {days != null ? `还剩约 ${days} 天 · 该补货` : '快用完了 · 该补货'}
      </Text>
    );
  }
  if (item.status === 'ok') {
    return (
      <Text style={[styles.statusLine, styles.statusOk]} numberOfLines={1}>
        {days != null ? `还剩约 ${days} 天` : '库存充足'}
      </Text>
    );
  }
  // unknown —— 不编造剩余天数
  return (
    <Text style={[styles.statusLine, styles.statusUnknown]} numberOfLines={2}>
      未记录库存 · 补货时登记数量即可估算
    </Text>
  );
}

function InventoryRow({
  item,
  last,
  onRestock,
  onCorrect,
}: {
  item: InventoryItem;
  last: boolean;
  onRestock: () => void;
  onCorrect: () => void;
}) {
  const meta = [item.brand, item.spec].filter((s) => s && s.length > 0).join(' · ');
  const isLow = item.status === 'low';
  return (
    <View style={[styles.row, last && { borderBottomWidth: 0 }]}>
      <View style={[styles.rowIcon, isLow && { backgroundColor: '#FBE8E4' }]}>
        <Icon name="pill" size={18} color={isLow ? '#D5503A' : C.green600} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.name} numberOfLines={1}>
          {item.name}
        </Text>
        {meta ? (
          <Text style={styles.meta} numberOfLines={1}>
            {meta}
          </Text>
        ) : null}
        <StatusLine item={item} />
      </View>
      <View style={styles.rowActions}>
        <Pressable
          onPress={onRestock}
          style={({ pressed }) => [styles.restockBtn, pressed && { opacity: 0.85 }]}
          accessibilityRole="button"
          accessibilityLabel={`补货:${item.name}`}
        >
          <Text style={styles.restockText}>补货</Text>
        </Pressable>
        <Pressable
          onPress={onCorrect}
          hitSlop={8}
          style={({ pressed }) => [styles.correctBtn, pressed && { opacity: 0.6 }]}
          accessibilityRole="button"
          accessibilityLabel={`校正剩余:${item.name}`}
        >
          <Text style={styles.correctText}>校正剩余</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function SupplementInventoryScreen() {
  const router = useRouter();
  const { data, isLoading, isError, refetch, isRefetching } = useSupplementInventory();
  const restock = useRestockSupplement();
  const setRemaining = useSetUnitsRemaining();

  const [sheet, setSheet] = useState<{ mode: SheetMode; item: InventoryItem } | null>(null);
  // 受控输入
  const [unitsAdded, setUnitsAdded] = useState('');
  const [brand, setBrand] = useState('');
  const [spec, setSpec] = useState('');
  const [packageUnits, setPackageUnits] = useState('');
  const [unitsRemaining, setUnitsRemainingInput] = useState('');

  const items = useMemo(() => data ?? [], [data]);
  const busy = restock.isPending || setRemaining.isPending;

  const openRestock = (item: InventoryItem) => {
    setUnitsAdded('');
    setBrand(item.brand ?? '');
    setSpec(item.spec ?? '');
    setPackageUnits('');
    setSheet({ mode: 'restock', item });
  };
  const openCorrect = (item: InventoryItem) => {
    setUnitsRemainingInput(
      item.units_remaining != null ? String(item.units_remaining) : '',
    );
    setSheet({ mode: 'correct', item });
  };
  const closeSheet = () => setSheet(null);

  const submitRestock = () => {
    if (!sheet) return;
    const added = Number(unitsAdded);
    if (!Number.isFinite(added) || added <= 0) return;
    restock.mutate(
      {
        supplementId: sheet.item.supplement_id,
        payload: {
          units_added: added,
          brand: brand.trim() ? brand.trim() : null,
          spec: spec.trim() ? spec.trim() : null,
          package_units: packageUnits.trim() ? Number(packageUnits) : null,
        },
      },
      {
        onSuccess: () => {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(
            () => {},
          );
          closeSheet();
        },
      },
    );
  };

  const submitCorrect = () => {
    if (!sheet) return;
    const remaining = Number(unitsRemaining);
    if (!Number.isFinite(remaining) || remaining < 0) return;
    setRemaining.mutate(
      {
        supplementId: sheet.item.supplement_id,
        payload: { units_remaining: remaining },
      },
      {
        onSuccess: () => {
          Haptics.selectionAsync().catch(() => {});
          closeSheet();
        },
      },
    );
  };

  const Header = (
    <View style={styles.header}>
      <TouchableOpacity onPress={() => router.back()} hitSlop={10} style={styles.back}>
        <Ionicons name="chevron-back" size={26} color={C.ink1} />
      </TouchableOpacity>
      <Text style={styles.headerTitle}>补剂库存</Text>
      <View style={styles.back} />
    </View>
  );

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <ActivityIndicator color={C.green500} />
        </View>
      </SafeAreaView>
    );
  }

  if (isError) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <Icon name="alert-triangle" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>暂时拉不到库存</Text>
          <Text style={styles.emptySub}>请检查网络后重试</Text>
          <Pressable style={styles.retryBtn} onPress={() => refetch()}>
            <Text style={styles.retryText}>重试</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  if (items.length === 0) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ headerShown: false }} />
        {Header}
        <View style={styles.center}>
          <Icon name="pill" size={30} color={C.ink3} />
          <Text style={styles.emptyTitle}>还没有补剂</Text>
          <Text style={styles.emptySub}>先去补剂页添加,这里就能跟踪库存与该补货的时机。</Text>
        </View>
      </SafeAreaView>
    );
  }

  const lowCount = items.filter((it) => it.status === 'low').length;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      {Header}
      <ScrollView contentContainerStyle={styles.content}>
        <SectionLabel>
          {lowCount > 0 ? `库存 · ${lowCount} 项该补货` : '库存'}
        </SectionLabel>
        <Card pad={0}>
          {items.map((it, i) => (
            <InventoryRow
              key={it.supplement_id}
              item={it}
              last={i === items.length - 1}
              onRestock={() => openRestock(it)}
              onCorrect={() => openCorrect(it)}
            />
          ))}
        </Card>
        <Text style={styles.disclaimer}>
          剩余天数按每日用量估算,仅作补货物流提醒,不构成医疗建议。实际用量请以医嘱与说明书为准。
        </Text>
        {isRefetching ? (
          <View style={{ paddingTop: 12 }}>
            <ActivityIndicator color={C.green500} />
          </View>
        ) : null}
      </ScrollView>

      {/* 补货 / 校正 输入弹层 */}
      <Modal
        visible={sheet != null}
        transparent
        animationType="slide"
        onRequestClose={closeSheet}
      >
        <Pressable style={styles.backdrop} onPress={closeSheet}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : undefined}
            style={styles.sheetWrap}
          >
            <Pressable style={styles.sheet} onPress={() => {}}>
              {sheet?.mode === 'restock' ? (
                <>
                  <Text style={styles.sheetTitle}>补货 · {sheet.item.name}</Text>
                  <Text style={styles.sheetHint}>登记本次到货的数量(片/粒/包等)。</Text>
                  <Text style={styles.fieldLabel}>到货数量</Text>
                  <TextInput
                    style={styles.input}
                    value={unitsAdded}
                    onChangeText={setUnitsAdded}
                    keyboardType="number-pad"
                    placeholder="例如 60"
                    placeholderTextColor={C.ink4}
                    autoFocus
                  />
                  <Text style={styles.fieldLabel}>品牌(可选)</Text>
                  <TextInput
                    style={styles.input}
                    value={brand}
                    onChangeText={setBrand}
                    placeholder="例如 某品牌"
                    placeholderTextColor={C.ink4}
                  />
                  <Text style={styles.fieldLabel}>规格(可选)</Text>
                  <TextInput
                    style={styles.input}
                    value={spec}
                    onChangeText={setSpec}
                    placeholder="例如 1000mg"
                    placeholderTextColor={C.ink4}
                  />
                  <Text style={styles.fieldLabel}>每包数量(可选)</Text>
                  <TextInput
                    style={styles.input}
                    value={packageUnits}
                    onChangeText={setPackageUnits}
                    keyboardType="number-pad"
                    placeholder="例如 60"
                    placeholderTextColor={C.ink4}
                  />
                  <View style={styles.sheetActions}>
                    <Pressable style={styles.cancelBtn} onPress={closeSheet}>
                      <Text style={styles.cancelText}>取消</Text>
                    </Pressable>
                    <Pressable
                      style={({ pressed }) => [
                        styles.submitBtn,
                        (busy || !(Number(unitsAdded) > 0)) && { opacity: 0.5 },
                        pressed && { opacity: 0.85 },
                      ]}
                      disabled={busy || !(Number(unitsAdded) > 0)}
                      onPress={submitRestock}
                    >
                      {busy ? (
                        <ActivityIndicator color={C.greenOn} />
                      ) : (
                        <Text style={styles.submitText}>登记补货</Text>
                      )}
                    </Pressable>
                  </View>
                </>
              ) : sheet?.mode === 'correct' ? (
                <>
                  <Text style={styles.sheetTitle}>校正剩余 · {sheet.item.name}</Text>
                  <Text style={styles.sheetHint}>
                    直接设定当前剩余数量(纠错用,不累加)。
                  </Text>
                  <Text style={styles.fieldLabel}>当前剩余数量</Text>
                  <TextInput
                    style={styles.input}
                    value={unitsRemaining}
                    onChangeText={setUnitsRemainingInput}
                    keyboardType="number-pad"
                    placeholder="例如 30"
                    placeholderTextColor={C.ink4}
                    autoFocus
                  />
                  <View style={styles.sheetActions}>
                    <Pressable style={styles.cancelBtn} onPress={closeSheet}>
                      <Text style={styles.cancelText}>取消</Text>
                    </Pressable>
                    <Pressable
                      style={({ pressed }) => [
                        styles.submitBtn,
                        (busy || !(Number(unitsRemaining) >= 0 && unitsRemaining.trim() !== '')) && {
                          opacity: 0.5,
                        },
                        pressed && { opacity: 0.85 },
                      ]}
                      disabled={
                        busy || !(Number(unitsRemaining) >= 0 && unitsRemaining.trim() !== '')
                      }
                      onPress={submitCorrect}
                    >
                      {busy ? (
                        <ActivityIndicator color={C.greenOn} />
                      ) : (
                        <Text style={styles.submitText}>保存</Text>
                      )}
                    </Pressable>
                  </View>
                </>
              ) : null}
            </Pressable>
          </KeyboardAvoidingView>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  back: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', color: C.ink1 },
  content: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 24 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 8 },

  emptyTitle: { fontSize: 16, fontWeight: '700', color: C.ink1, marginTop: 4 },
  emptySub: { fontSize: 13.5, color: C.ink3, textAlign: 'center', lineHeight: 20 },
  retryBtn: {
    marginTop: 8,
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 22,
    paddingVertical: 10,
  },
  retryText: { color: C.greenOn, fontSize: 14, fontWeight: '700' },

  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: C.line,
  },
  rowIcon: {
    width: 38,
    height: 38,
    borderRadius: 11,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  name: { fontSize: 15, fontWeight: '600', color: C.ink1 },
  meta: { fontSize: 12.5, color: C.ink3, marginTop: 1 },
  statusLine: { fontSize: 13, marginTop: 3 },
  statusLow: { color: '#C98A1E', fontWeight: '700' },
  statusOk: { color: C.ink3 },
  statusUnknown: { color: C.ink3 },
  rowActions: { alignItems: 'flex-end', gap: 6 },
  restockBtn: {
    backgroundColor: C.green500,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 16,
    paddingVertical: 7,
  },
  restockText: { color: C.greenOn, fontSize: 13.5, fontWeight: '700' },
  correctBtn: { paddingHorizontal: 6, paddingVertical: 2 },
  correctText: { color: C.ink3, fontSize: 12.5 },

  disclaimer: {
    fontSize: 11.5,
    color: C.ink3,
    lineHeight: 17,
    marginTop: 16,
    paddingHorizontal: 4,
  },

  // sheet
  backdrop: { flex: 1, backgroundColor: 'rgba(15,28,23,0.4)', justifyContent: 'flex-end' },
  sheetWrap: { width: '100%' },
  sheet: {
    backgroundColor: C.surface,
    borderTopLeftRadius: revaRadii.xl,
    borderTopRightRadius: revaRadii.xl,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 36,
    gap: 6,
  },
  sheetTitle: { fontSize: 17, fontWeight: '700', color: C.ink1 },
  sheetHint: { fontSize: 13, color: C.ink3, marginBottom: 6, lineHeight: 19 },
  fieldLabel: { fontSize: 12, fontWeight: '600', color: C.ink2, marginTop: 8 },
  input: {
    borderWidth: 1.5,
    borderColor: C.lineStrong,
    borderRadius: revaRadii.sm,
    paddingHorizontal: 14,
    paddingVertical: 11,
    fontSize: 15,
    color: C.ink1,
    backgroundColor: C.surface2,
    marginTop: 4,
  },
  sheetActions: { flexDirection: 'row', gap: 12, marginTop: 18 },
  cancelBtn: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: revaRadii.pill,
    borderWidth: 1.5,
    borderColor: C.lineStrong,
  },
  cancelText: { color: C.ink2, fontSize: 15, fontWeight: '600' },
  submitBtn: {
    flex: 1.6,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green500,
  },
  submitText: { color: C.greenOn, fontSize: 15, fontWeight: '700' },
});
