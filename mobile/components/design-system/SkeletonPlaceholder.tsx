import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { colors, radii, spacing } from '@/constants/theme';

function Bone({ width, height = 14, style }: { width: number | string; height?: number; style?: any }) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.7, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, []);

  return (
    <Animated.View style={[styles.bone, { width: width as any, height, opacity }, style]} />
  );
}

export function HomeHeaderSkeleton() {
  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={{ flex: 1, gap: 8 }}>
          <Bone width={120} height={22} />
          <Bone width={180} height={14} />
          <Bone width={150} height={12} />
        </View>
        <Bone width={52} height={52} style={{ borderRadius: 26 }} />
      </View>
      <View style={[styles.row, { marginTop: 14, paddingTop: 14, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.separator }]}>
        <Bone width={50} height={30} style={{ borderRadius: 8 }} />
        <Bone width={50} height={30} style={{ borderRadius: 8 }} />
        <Bone width={50} height={30} style={{ borderRadius: 8 }} />
        <Bone width={50} height={30} style={{ borderRadius: 8 }} />
      </View>
    </View>
  );
}

export function CardSkeleton() {
  return (
    <View style={styles.skCard}>
      <Bone width={100} height={16} />
      <Bone width="100%" height={12} style={{ marginTop: 8 }} />
      <Bone width="80%" height={12} style={{ marginTop: 6 }} />
    </View>
  );
}

export function VitalsGridSkeleton() {
  return (
    <View style={styles.gridRow}>
      {[0, 1, 2, 3].map(i => (
        <View key={i} style={styles.gridItem}>
          <Bone width={26} height={26} style={{ borderRadius: 8 }} />
          <Bone width={40} height={10} style={{ marginTop: 8 }} />
          <Bone width={50} height={20} style={{ marginTop: 4 }} />
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bone: { backgroundColor: '#E5E5EA', borderRadius: 6 },
  card: {
    backgroundColor: colors.bgCard, borderRadius: radii.xl,
    padding: spacing.lg, marginHorizontal: spacing.lg,
    marginTop: spacing.sm, marginBottom: spacing.md,
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  skCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
  },
  gridRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginBottom: spacing.lg },
  gridItem: {
    width: '47.5%', backgroundColor: colors.bgCard,
    borderRadius: radii.lg, padding: 14,
  },
});
