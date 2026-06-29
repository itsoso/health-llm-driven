import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { APP_DISPLAY_NAME } from '../constants/brand';
import { useTheme, type ColorPalette } from '../hooks/useTheme';

export default function AppLockScreen({ onUnlock }: { onUnlock: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  return (
    <View style={styles.lockContainer}>
      <Ionicons name="lock-closed" size={48} color={c.brand} />
      <Text style={styles.lockTitle}>{APP_DISPLAY_NAME}</Text>
      <TouchableOpacity style={styles.unlockBtn} onPress={onUnlock} activeOpacity={0.7}>
        <Ionicons name="finger-print" size={22} color="#fff" />
        <Text style={styles.unlockText}>解锁</Text>
      </TouchableOpacity>
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  lockContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: c.bgPrimary,
    gap: 16,
  },
  lockTitle: {
    fontSize: 22,
    fontWeight: '600',
    color: c.labelPrimary,
  } as TextStyle,
  unlockBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: c.brand,
    borderRadius: 12,
    paddingHorizontal: 24,
    paddingVertical: 12,
    marginTop: 16,
  },
  unlockText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  } as TextStyle,
});
