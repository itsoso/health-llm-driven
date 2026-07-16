import React, { useMemo } from 'react';
import { StyleSheet, Text, TouchableOpacity, View, type TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { radii, shadows, spacing } from '../../constants/theme';
import { useAppUpdate } from '../../hooks/useAppUpdate';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

export default function AppUpdateBanner() {
  const {
    status,
    error,
    isForced,
    nativeUpdateRequirement = 'none',
    nativeUpdateUrl = null,
    openNativeUpdate = async () => false,
    applyUpdate,
    dismiss,
  } = useAppUpdate();
  const { c, s } = useTheme();
  const insets = useSafeAreaInsets();
  const styles = useMemo(() => createStyles(c), [c]);

  const showNativeGate = nativeUpdateRequirement !== 'none'
    && status !== 'ready'
    && status !== 'applying';

  if (showNativeGate) {
    const isRequired = nativeUpdateRequirement === 'required';
    return (
      <View
        testID="native-update-banner"
        style={[styles.banner, { top: insets.top + spacing.sm }]}
        accessibilityLiveRegion="assertive"
      >
        <Ionicons
          name={isRequired ? 'alert-circle-outline' : 'cloud-download-outline'}
          size={20}
          color={isRequired ? s.warning.solid : c.brand}
        />
        <View style={styles.copy}>
          <Text style={styles.title}>{isRequired ? '需要更新小巴' : '建议更新小巴'}</Text>
          <Text style={styles.body}>
            {error ?? (isRequired
              ? '当前版本需要原生升级后才能继续获得新能力'
              : '有一个原生版本可选，不影响当前使用')}
          </Text>
        </View>
        {nativeUpdateUrl ? (
          <TouchableOpacity
            style={styles.primaryAction}
            onPress={() => void openNativeUpdate()}
            accessibilityRole="button"
          >
            <Text style={styles.primaryActionText}>去更新</Text>
          </TouchableOpacity>
        ) : null}
        {!isRequired ? (
          <TouchableOpacity onPress={dismiss} accessibilityRole="button" hitSlop={8}>
            <Text style={styles.secondaryActionText}>稍后</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    );
  }

  if (status !== 'ready' && status !== 'applying') return null;

  return (
    <View
      testID="app-update-banner"
      style={[styles.banner, { top: insets.top + spacing.sm }]}
      accessibilityLiveRegion="polite"
    >
      <Ionicons name="arrow-down-circle-outline" size={20} color={c.brand} />
      <View style={styles.copy}>
        <Text style={styles.title}>{isForced ? '请完成应用更新' : '新版本已准备好'}</Text>
        <Text style={styles.body}>
          {isForced ? '为保证当前版本兼容，请更新后继续使用' : '现在更新，几秒后回到当前页面'}
        </Text>
      </View>
      <TouchableOpacity
        style={styles.primaryAction}
        onPress={() => void applyUpdate()}
        disabled={status === 'applying'}
        accessibilityRole="button"
      >
        <Text style={styles.primaryActionText}>{status === 'applying' ? '更新中' : '立即更新'}</Text>
      </TouchableOpacity>
      {!isForced && status !== 'applying' ? (
        <TouchableOpacity onPress={dismiss} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.secondaryActionText}>稍后</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    banner: {
      position: 'absolute',
      left: spacing.md,
      right: spacing.md,
      zIndex: 9998,
      minHeight: 58,
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      borderRadius: radii.md,
      backgroundColor: c.bgCard,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      ...shadows.medium,
    },
    copy: { flex: 1, minWidth: 0 },
    title: { fontSize: 14, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    body: { marginTop: 2, fontSize: 11, color: c.labelSecondary } as TextStyle,
    primaryAction: {
      minHeight: 34,
      justifyContent: 'center',
      paddingHorizontal: spacing.md,
      borderRadius: radii.sm,
      backgroundColor: c.brand,
    },
    primaryActionText: { fontSize: 13, fontWeight: '700', color: '#fff' } as TextStyle,
    secondaryActionText: { fontSize: 12, fontWeight: '600', color: c.labelSecondary } as TextStyle,
  });
}
