/**
 * VoiceRecordingOverlay — 全屏沉浸式「心跳波形」语音录音层(阿福 form,复元 Reva 设计语言)。
 *
 * 替代微信式小气的「按住说话」内联小条:按住时弹出**全屏**沉浸层,中央一排随语音起伏的
 * 波形(心跳),配「松开发送 · 上滑取消」提示 + 录音时的情境追问建议。放开=发送,上滑进入
 * 取消区(cancelArmed)=丢弃。
 *
 * **隔离原则**:本组件是纯呈现层,完全独立于正在被并行改写的 ChatInputBar / 语音 hooks。
 * 手势判定(按住/上滑)、真实音频电平、发送/取消动作都由**将来的接线**从外部喂进来:
 *  - `visible` 控制显隐;`cancelArmed` 反映上滑取消区是否激活;
 *  - `levels`(0..1 的一段振幅历史)接真实 metering;不传则自持「心跳」动画,先看得见活的。
 * 因此它现在可独立构建 + 测试,接线等 ChatInputBar 落定后再做一小段。
 *
 * 色彩:阿福原图是紫,本实现走 Reva 绿 token(设计 token 闸只认 revaTheme)。要不要改成
 * 专属「语音模式」色板,是后续一个小决定(需先加品牌 token)。
 */
import React, { useEffect, useMemo, useRef } from 'react';
import { View, Text, Modal, StyleSheet, Animated, Easing } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSpacing,
  revaSemantic,
} from '../../constants/revaTheme';

const BAR_COUNT = 28;
const BAR_MIN = 0.22; // 静息振幅(scaleY 下限)

export interface VoiceRecordingOverlayProps {
  /** 是否显示(按住说话时为 true)。 */
  visible: boolean;
  /** 上滑取消区已激活:提示与波形转为「松开取消」危险态。 */
  cancelArmed?: boolean;
  /** 录音时展示的情境追问建议(可点/仅展示,由接线决定;此处只呈现)。 */
  suggestions?: string[];
  /** 可选:真实音频振幅历史(0..1),长度不限,取尾部 BAR_COUNT 段驱动波形。 */
  levels?: number[];
  /** 系统返回或 Modal 关闭回调。 */
  onRequestClose?: () => void;
}

export function VoiceRecordingOverlay({
  visible,
  cancelArmed = false,
  suggestions,
  levels,
  onRequestClose,
}: VoiceRecordingOverlayProps) {
  // 每根波形柱一个 Animated.Value(scaleY),初值 = 静息。
  const bars = useRef(
    Array.from({ length: BAR_COUNT }, () => new Animated.Value(BAR_MIN)),
  ).current;

  // 自持「心跳」动画:无真实 levels 时,让每根柱在低/高之间有机起伏(错峰、随机时长)。
  useEffect(() => {
    if (!visible || levels) return;
    const loops = bars.map((bar) =>
      Animated.loop(
        Animated.sequence([
          Animated.timing(bar, {
            toValue: BAR_MIN + Math.random() * (1 - BAR_MIN),
            duration: 260 + Math.random() * 320,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
          Animated.timing(bar, {
            toValue: BAR_MIN + Math.random() * 0.25,
            duration: 240 + Math.random() * 260,
            easing: Easing.inOut(Easing.ease),
            useNativeDriver: true,
          }),
        ]),
      ),
    );
    const timers = loops.map((l, i) => setTimeout(() => l.start(), i * 28));
    return () => {
      timers.forEach(clearTimeout);
      loops.forEach((l) => l.stop());
      bars.forEach((b) => b.setValue(BAR_MIN));
    };
  }, [visible, levels, bars]);

  // 真实 metering:把尾部 BAR_COUNT 段振幅直接落到各柱(平滑交给 timing)。
  useEffect(() => {
    if (!visible || !levels) return;
    const tail = levels.slice(-BAR_COUNT);
    bars.forEach((bar, i) => {
      const v = tail[i];
      Animated.timing(bar, {
        toValue: Math.max(BAR_MIN, Math.min(1, typeof v === 'number' ? v : BAR_MIN)),
        duration: 90,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }).start();
    });
  }, [visible, levels, bars]);

  const waveColor = cancelArmed ? revaSemantic.risk.fg : C.green500;
  const hintText = cancelArmed ? '松开取消' : '松开发送 · 上滑取消';
  const hintColor = cancelArmed ? revaSemantic.risk.fg : C.ink2;
  const cleanSuggestions = useMemo(
    () => (Array.isArray(suggestions) ? suggestions.filter((s) => typeof s === 'string' && s.trim()) : []),
    [suggestions],
  );

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onRequestClose}>
      <View style={styles.fill} accessibilityViewIsModal accessibilityLabel="语音录入中">
        {/* 情境追问建议(录音时透出,先只展示) */}
        {cleanSuggestions.length > 0 ? (
          <View style={styles.suggestWrap}>
            {cleanSuggestions.slice(0, 3).map((s, i) => (
              <View key={i} style={styles.suggestChip}>
                <Text maxFontSizeMultiplier={1.2} style={styles.suggestText} numberOfLines={2}>{s}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {/* 中央:心跳波形 + 柔光晕 */}
        <View style={styles.center}>
          <View style={[styles.halo, { backgroundColor: cancelArmed ? revaSemantic.risk.bg : C.green50 }]} />
          <View style={styles.wave} accessibilityLabel="语音波形">
            {bars.map((bar, i) => (
              <Animated.View
                key={i}
                style={[
                  styles.bar,
                  { backgroundColor: waveColor, transform: [{ scaleY: bar }] },
                ]}
              />
            ))}
          </View>
        </View>

        {/* 底部提示 */}
        <View style={styles.footer}>
          <Ionicons
            name={cancelArmed ? 'close-circle' : 'mic'}
            size={20}
            color={cancelArmed ? revaSemantic.risk.fg : C.green500}
          />
          <Text maxFontSizeMultiplier={1.3} style={[styles.hint, { color: hintColor }]}>{hintText}</Text>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  fill: {
    flex: 1,
    backgroundColor: C.surface,
    justifyContent: 'space-between',
    paddingTop: 96,
    paddingBottom: 72,
    paddingHorizontal: revaSpacing.s5,
  },
  suggestWrap: { gap: revaSpacing.s2, alignItems: 'center' },
  suggestChip: {
    maxWidth: 320,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s2 + 2,
    borderRadius: revaRadii.lg,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  suggestText: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    color: C.ink2,
    lineHeight: 21,
    textAlign: 'center',
  } as TextStyle,
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  halo: {
    position: 'absolute',
    width: 240,
    height: 240,
    borderRadius: 120,
    opacity: 0.6,
  },
  wave: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    height: 64,
    gap: 4,
  },
  bar: {
    width: 3.5,
    height: 56,
    borderRadius: 2,
  },
  footer: { alignItems: 'center', gap: revaSpacing.s2 },
  hint: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '600',
    letterSpacing: 0.3,
  } as TextStyle,
});
