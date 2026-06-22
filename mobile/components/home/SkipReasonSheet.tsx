/**
 * SkipReasonSheet —— 跳过原因底部抽屉(首页时间线「跳过」入口)。
 *
 * 复用 ExplainSheet 的 Modal + 半透明遮罩 + 上滑底卡 idiom,改用 Reva tokens
 * (RevaTimelineStrip 是 Reva 专屏)。8 个后端枚举原因 + 一个「不填原因」快捷出口。
 *
 * R4:跳过是纯记录动作(没做 + 为什么),无医疗内容。
 * onPick 携带 reason(undefined = 不填原因);onClose 关闭不动作。
 */
import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { revaColors as C } from '../../constants/revaTheme';
import { SKIP_REASONS } from '../../constants/skipReasons';
import type { AgendaSkipReason } from '../../services/agenda';

export interface SkipReasonSheetProps {
  visible: boolean;
  /** 跳过项的标题,展示在抽屉头部(让用户知道在跳过哪条)。 */
  title?: string | null;
  /** 选中一个原因(或「不填原因」→ undefined)。 */
  onPick: (reason: AgendaSkipReason | undefined) => void;
  /** 关闭(取消,不记录)。 */
  onClose: () => void;
}

export default function SkipReasonSheet({
  visible,
  title,
  onPick,
  onClose,
}: SkipReasonSheetProps) {
  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handle} />
          <Text style={styles.title}>跳过这一项的原因?</Text>
          {title ? (
            <Text style={styles.subtitle} numberOfLines={1}>
              {title}
            </Text>
          ) : null}

          <View style={styles.grid}>
            {SKIP_REASONS.map((r) => (
              <Pressable
                key={r.value}
                style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
                onPress={() => onPick(r.value)}
                accessibilityRole="button"
                accessibilityLabel={`跳过原因 ${r.label}`}
              >
                <Text style={styles.chipText}>{r.label}</Text>
              </Pressable>
            ))}
          </View>

          <Pressable
            style={({ pressed }) => [styles.noReason, pressed && styles.noReasonPressed]}
            onPress={() => onPick(undefined)}
            accessibilityRole="button"
            accessibilityLabel="跳过,不填原因"
          >
            <Text style={styles.noReasonText}>跳过(不填原因)</Text>
          </Pressable>

          <Pressable style={styles.cancel} onPress={onClose} accessibilityRole="button">
            <Text style={styles.cancelText}>取消</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(15,28,23,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: C.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 32,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: C.lineStrong,
    marginBottom: 14,
  },
  title: { fontSize: 18, fontWeight: '700', color: C.ink1 },
  subtitle: { fontSize: 13, color: C.ink3, marginTop: 4 },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 18,
  },
  chip: {
    paddingVertical: 11,
    paddingHorizontal: 16,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: C.lineStrong,
    backgroundColor: C.surface2,
  },
  chipPressed: { backgroundColor: C.green50, borderColor: C.green300 },
  chipText: { fontSize: 14.5, fontWeight: '600', color: C.ink1 },
  noReason: {
    marginTop: 18,
    paddingVertical: 13,
    borderRadius: 14,
    backgroundColor: C.paper2,
    alignItems: 'center',
  },
  noReasonPressed: { backgroundColor: C.line },
  noReasonText: { fontSize: 14.5, fontWeight: '600', color: C.ink2 },
  cancel: { alignSelf: 'center', marginTop: 14, padding: 6 },
  cancelText: { fontSize: 15, color: C.ink3 },
});
