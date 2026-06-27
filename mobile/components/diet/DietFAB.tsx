import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import {
  revaColors as C,
  revaShadows,
} from '../../constants/revaTheme';

// 三种录入方式的类目装饰色(区分"哪种录入",非"好坏"):语音蓝 / 文字琥珀 / 拍照绿。
const CAP_HUES = {
  voice: { fg: C.blue500, bg: C.blue50 },
  text: { fg: '#C98A1E', bg: '#F6ECD9' },
  photo: { fg: C.green500, bg: C.green50 },
} as const;

interface Props {
  onPhoto: () => void;
  onText: () => void;
  onVoice: () => void;
}

export default function DietFAB({ onPhoto, onText, onVoice }: Props) {
  const [open, setOpen] = useState(false);
  const anim = React.useRef(new Animated.Value(0)).current;

  const toggle = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    const toVal = open ? 0 : 1;
    Animated.spring(anim, { toValue: toVal, useNativeDriver: true, friction: 6 }).start();
    setOpen(!open);
  };

  const photoY = anim.interpolate({ inputRange: [0, 1], outputRange: [0, -65] });
  const textY = anim.interpolate({ inputRange: [0, 1], outputRange: [0, -125] });
  const voiceY = anim.interpolate({ inputRange: [0, 1], outputRange: [0, -185] });
  const rotation = anim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '45deg'] });

  return (
    <View style={styles.container} pointerEvents="box-none">
      <Animated.View style={[styles.subFab, { transform: [{ translateY: voiceY }], opacity: anim }]}>
        <TouchableOpacity style={[styles.subBtn, { backgroundColor: CAP_HUES.voice.bg }]}
          onPress={() => { toggle(); onVoice(); }} activeOpacity={0.7}
          accessibilityRole="button" accessibilityLabel="语音记录饮食">
          <Ionicons name="mic-outline" size={20} color={CAP_HUES.voice.fg} />
        </TouchableOpacity>
      </Animated.View>
      <Animated.View style={[styles.subFab, { transform: [{ translateY: textY }], opacity: anim }]}>
        <TouchableOpacity style={[styles.subBtn, { backgroundColor: CAP_HUES.text.bg }]}
          onPress={() => { toggle(); onText(); }} activeOpacity={0.7}
          accessibilityRole="button" accessibilityLabel="文字记录饮食">
          <Ionicons name="text-outline" size={20} color={CAP_HUES.text.fg} />
        </TouchableOpacity>
      </Animated.View>
      <Animated.View style={[styles.subFab, { transform: [{ translateY: photoY }], opacity: anim }]}>
        <TouchableOpacity style={[styles.subBtn, { backgroundColor: CAP_HUES.photo.bg }]}
          onPress={() => { toggle(); onPhoto(); }} activeOpacity={0.7}
          accessibilityRole="button" accessibilityLabel="拍照记录饮食">
          <Ionicons name="camera-outline" size={20} color={CAP_HUES.photo.fg} />
        </TouchableOpacity>
      </Animated.View>
      <TouchableOpacity style={styles.mainFab} onPress={toggle} activeOpacity={0.8}
        accessibilityRole="button" accessibilityLabel="添加饮食记录">
        <Animated.View style={{ transform: [{ rotate: rotation }] }}>
          <Ionicons name="add" size={28} color="#fff" />
        </Animated.View>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { position: 'absolute', bottom: 110, right: 20, alignItems: 'center' },
  mainFab: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: C.green500, alignItems: 'center', justifyContent: 'center',
    ...revaShadows.md,
  },
  subFab: { position: 'absolute', bottom: 0 },
  subBtn: {
    width: 44, height: 44, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center',
    ...revaShadows.sm,
  },
});
