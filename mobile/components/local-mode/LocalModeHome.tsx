import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { useAppSession } from '../../hooks/useAppSession';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import AppModeSelector from './AppModeSelector';
import LocalDietScreen from './LocalDietScreen';
import LocalDataScreen from './LocalDataScreen';
import { LocalDietRepository } from '../../services/localDietRepository';

export default function LocalModeHome() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { session } = useAppSession();
  const isStrict = session?.mode === 'strict_local';
  const [panel, setPanel] = useState<'home' | 'diet' | 'data'>('home');
  const dietRepository = useMemo(
    () => session?.localIdentityId ? new LocalDietRepository(session.localIdentityId) : null,
    [session?.localIdentityId],
  );

  if (panel === 'diet' && dietRepository) {
    return <LocalDietScreen repository={dietRepository} onBack={() => setPanel('home')} />;
  }
  if (panel === 'data') {
    return <LocalDataScreen onBack={() => setPanel('home')} />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.hero}>
          <View style={styles.heroIcon}>
            <Ionicons name="lock-closed" size={27} color={c.brand} />
          </View>
          <Text style={styles.eyebrow}>{isStrict ? '严格本地模式' : '本地优先模式'}</Text>
          <Text style={styles.title}>你的健康资料留在这台 iPhone</Text>
          <Text style={styles.subtitle}>
            本地保险库已启用设备密码保护；切换模式不会自动搬运本机或云端的既有资料。
          </Text>
        </View>

        <View style={styles.statusCard}>
          <StatusRow icon="key-outline" title="本地加密保险库" value="已开启" />
          <StatusRow icon="cloud-offline-outline" title="自动云端同步" value="已关闭" />
          <StatusRow
            icon="sparkles-outline"
            title="云端 AI"
            value={isStrict ? '已关闭' : '仅主动调用'}
          />
        </View>

        <Pressable
          style={({ pressed }) => [styles.featureCard, pressed ? styles.featureCardPressed : null]}
          onPress={() => setPanel('diet')}
          accessibilityRole="button"
          accessibilityLabel="打开本地饮食记录"
        >
          <View style={styles.featureIcon}>
            <Ionicons name="restaurant-outline" size={22} color={c.brand} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.featureTitle}>本地饮食记录</Text>
            <Text style={styles.featureDetail}>文字录入、营养草稿、确认和历史全部离线完成</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={c.labelTertiary} />
        </Pressable>

        <Pressable
          style={({ pressed }) => [styles.featureCard, pressed ? styles.featureCardPressed : null]}
          onPress={() => setPanel('data')}
          accessibilityRole="button"
          accessibilityLabel="打开本地数据备份与删除"
        >
          <View style={styles.featureIcon}>
            <Ionicons name="archive-outline" size={22} color={c.brand} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.featureTitle}>本地数据管理</Text>
            <Text style={styles.featureDetail}>加密备份、恢复和永久删除</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={c.labelTertiary} />
        </Pressable>

        <View>
          <Text style={styles.sectionTitle}>运行模式</Text>
          <Text style={styles.sectionHint}>可随时切换；本地资料不会被静默上传。</Text>
        </View>
        <AppModeSelector />

        <View style={styles.notice}>
          <Ionicons name="information-circle-outline" size={20} color={c.brand} />
          <Text style={styles.noticeText}>
            换机或重装前，请导出恢复文件，并把恢复密钥分开保存。两者缺一都无法恢复。
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function StatusRow({
  icon,
  title,
  value,
}: {
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  value: string;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={styles.statusRow}>
      <Ionicons name={icon} size={19} color={c.labelSecondary} />
      <Text style={styles.statusTitle}>{title}</Text>
      <Text style={styles.statusValue}>{value}</Text>
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  content: { paddingHorizontal: 20, paddingVertical: 22, gap: 18 },
  hero: { alignItems: 'center', paddingHorizontal: 14, gap: 7 },
  heroIcon: {
    width: 58,
    height: 58,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: c.brandLight,
    marginBottom: 3,
  },
  eyebrow: { color: c.brand, fontSize: 13, fontWeight: '700' },
  title: { color: c.labelPrimary, fontSize: 23, fontWeight: '800', textAlign: 'center' },
  subtitle: { color: c.labelSecondary, fontSize: 14, lineHeight: 21, textAlign: 'center' },
  statusCard: {
    borderRadius: 16,
    backgroundColor: c.bgCard,
    borderWidth: 1,
    borderColor: c.separator,
    paddingHorizontal: 15,
  },
  statusRow: {
    minHeight: 50,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  statusTitle: { flex: 1, color: c.labelPrimary, fontSize: 14 },
  statusValue: { color: c.brand, fontSize: 13, fontWeight: '700' },
  featureCard: {
    minHeight: 78,
    borderRadius: 16,
    backgroundColor: c.bgCard,
    borderWidth: 1,
    borderColor: c.separator,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  featureCardPressed: { opacity: 0.72 },
  featureIcon: { width: 42, height: 42, borderRadius: 13, backgroundColor: c.brandLight, alignItems: 'center', justifyContent: 'center' },
  featureTitle: { color: c.labelPrimary, fontSize: 16, fontWeight: '700' },
  featureDetail: { color: c.labelSecondary, fontSize: 12, lineHeight: 18, marginTop: 3 },
  sectionTitle: { color: c.labelPrimary, fontSize: 18, fontWeight: '800' },
  sectionHint: { color: c.labelSecondary, fontSize: 13, marginTop: 4 },
  notice: {
    flexDirection: 'row',
    gap: 10,
    borderRadius: 14,
    backgroundColor: c.brandLight,
    padding: 14,
  },
  noticeText: { flex: 1, color: c.labelSecondary, fontSize: 13, lineHeight: 19 },
});
