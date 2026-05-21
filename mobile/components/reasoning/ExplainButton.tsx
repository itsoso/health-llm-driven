/**
 * Task 3: "为什么?" 按钮 — 点开 ExplainSheet 抽屉.
 *
 * 挂在 Safety alert / Specialist finding 上, 提供决策可解释性入口.
 * 样式保持和 alerts.tsx 中的 aiBtn 视觉一致 (小 pill).
 */
import React, { useState } from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { ExplainSheet } from './ExplainSheet';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

type Props =
  | { source: 'safety'; auditId: number; ruleId: string }
  | { source: 'specialist'; auditId: number; specialist: string };

export function ExplainButton(props: Props) {
  const [open, setOpen] = useState(false);
  const { c } = useTheme();
  const styles = createStyles(c);
  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        style={styles.btn}
        accessibilityLabel="查看这条的推理依据"
        accessibilityRole="button"
      >
        <Text style={styles.text}>为什么?</Text>
      </Pressable>
      <ExplainSheet visible={open} onClose={() => setOpen(false)} {...props} />
    </>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    btn: {
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: 8,
      backgroundColor: c.tintBlue,
    },
    text: { fontSize: 12, color: c.brand, fontWeight: '500' },
  });
}
