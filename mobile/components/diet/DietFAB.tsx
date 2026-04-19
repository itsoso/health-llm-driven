import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radii, shadows } from '@/constants/theme';

interface Props {
  onPhoto: () => void;
  onText: () => void;
}

export default function DietFAB({ onPhoto, onText }: Props) {
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
  const rotation = anim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '45deg'] });

  return (
    <View style={styles.container} pointerEvents="box-none">
      <Animated.View style={[styles.subFab, { transform: [{ translateY: textY }], opacity: anim }]}>
        <TouchableOpacity style={[styles.subBtn, { backgroundColor: colors.tintAmber }]}
          onPress={() => { toggle(); onText(); }} activeOpacity={0.7}>
          <Ionicons name="text-outline" size={20} color={colors.amber} />
        </TouchableOpacity>
      </Animated.View>
      <Animated.View style={[styles.subFab, { transform: [{ translateY: photoY }], opacity: anim }]}>
        <TouchableOpacity style={[styles.subBtn, { backgroundColor: colors.tintGreen }]}
          onPress={() => { toggle(); onPhoto(); }} activeOpacity={0.7}>
          <Ionicons name="camera-outline" size={20} color={colors.green} />
        </TouchableOpacity>
      </Animated.View>
      <TouchableOpacity style={styles.mainFab} onPress={toggle} activeOpacity={0.8}>
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
    backgroundColor: colors.brand, alignItems: 'center', justifyContent: 'center',
    ...shadows.heavy,
  },
  subFab: { position: 'absolute', bottom: 0 },
  subBtn: {
    width: 44, height: 44, borderRadius: 22,
    alignItems: 'center', justifyContent: 'center',
    ...shadows.medium,
  },
});
