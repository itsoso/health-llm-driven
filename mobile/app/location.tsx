/**
 * 地理位置 / 天气定位偏好.
 *
 * 三种模式:
 *   1. 自动检测 (后端按 IP) — 默认
 *   2. 手动设定 (用户输入城市) — 切换开关 + 选城市
 *   3. GPS 定位 (要 native, 下次 build 加 expo-location)
 *
 * 改 location 时后端会清天气/AQI 缓存, 立即生效.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextInput,
  Switch, ActivityIndicator, TextStyle, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import * as Location from 'expo-location';
import api from '../services/api';
import {
  updateManualLocation, refreshDetectedLocation, updateGPSLocation, reverseGeocodeOnDevice,
  getEffectiveTimezone, setManualTimezone, getDeviceTimezone, type EffectiveTimezone,
} from '../services/location';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';

// 常用城市快选 (用户更可能选这些, 避免拼写)
const COMMON_CITIES = [
  '北京', '上海', '广州', '深圳', '杭州', '成都', '南京', '武汉', '西安',
  '天津', '苏州', '重庆', '青岛', '厦门', '长沙', '郑州', '昆明', '香港',
];

// 常用时区快选 (IANA). 手动锁定时从这里选, 避免手输错.
const COMMON_TIMEZONES = [
  'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Tokyo', 'Asia/Singapore',
  'America/Los_Angeles', 'America/New_York', 'Europe/London', 'Europe/Paris',
  'Australia/Sydney', 'Asia/Dubai',
];

const TZ_SOURCE_LABEL: Record<string, string> = {
  manual: '手动锁定',
  detected: '跟随设备所在地',
  profile: '配置',
  default: '默认 (中国)',
};

function formatProvenance(source: string, staleMin: number | null): string {
  const ageStr = staleMin == null
    ? '时间未知'
    : staleMin < 1 ? '刚刚'
    : staleMin < 60 ? `${staleMin} 分钟前`
    : staleMin < 60 * 24 ? `${Math.round(staleMin / 60)} 小时前`
    : `${Math.round(staleMin / (60 * 24))} 天前`;
  const sourceStr = source === 'gps' ? 'GPS'
    : source === 'ip' ? 'IP 检测'
    : source === 'manual' ? '手动'
    : '未知';
  if (source === 'manual') return `数据源: 手动`;
  if (source === 'unknown') return `数据源: 未知 — 还没拿到位置`;
  return `数据源: ${sourceStr} · ${ageStr}`;
}

interface ProfileLocation {
  use_manual_location: boolean;
  manual_location: { city: string | null; region: string | null; country: string | null } | null;
  detected_location: { city: string | null; region: string | null; country: string | null } | null;
}

export default function LocationScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<ProfileLocation>({
    queryKey: ['profileLocation'],
    queryFn: async () => {
      const resp = await api.get('/profile/me');
      return {
        use_manual_location: resp.data?.use_manual_location || false,
        manual_location: resp.data?.manual_location,
        detected_location: resp.data?.detected_location,
      };
    },
    staleTime: 30_000,
  });

  // Provenance — resolver 算出来的 source + 新鲜度. 用于"数据源" 副标.
  const { data: effective } = useQuery<{
    source: 'manual' | 'gps' | 'ip' | 'unknown';
    stale_minutes: number | null;
  }>({
    queryKey: ['effectiveLocation'],
    queryFn: async () => {
      const resp = await api.get('/profile/me/effective-location');
      return resp.data;
    },
    staleTime: 30_000,
  });

  // 生效时区 (跟随设备 / 手动锁定)
  const { data: tz } = useQuery<EffectiveTimezone>({
    queryKey: ['effectiveTimezone'],
    queryFn: getEffectiveTimezone,
    staleTime: 30_000,
  });

  const [useManual, setUseManual] = useState(false);
  const [cityInput, setCityInput] = useState('');
  const [tzManual, setTzManual] = useState(false);
  const [tzInput, setTzInput] = useState('');

  // 同步服务端状态到本地 state
  useEffect(() => {
    if (data) {
      setUseManual(!!data.use_manual_location);
      setCityInput(data.manual_location?.city || '');
    }
  }, [data]);

  // 同步时区状态: 有 manual_timezone = 已锁定; 否则默认填生效时区方便切换
  useEffect(() => {
    if (tz) {
      setTzManual(!!tz.manual_timezone);
      setTzInput(tz.manual_timezone || tz.timezone || '');
    }
  }, [tz]);

  const saveMut = useMutation({
    mutationFn: (payload: { use: boolean; city: string }) =>
      updateManualLocation({
        use_manual_location: payload.use,
        city: payload.city || null,
        region: null,
        country: '中国',
      }),
    onSuccess: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      // 让其它地方 (主页天气卡 / dashboard 等) 拿新数据
      qc.invalidateQueries({ queryKey: ['profileLocation'] });
      qc.invalidateQueries({ queryKey: ['effectiveLocation'] });
      qc.invalidateQueries({ queryKey: ['weather'] });
      qc.invalidateQueries({ queryKey: ['weatherForecast'] });
      qc.invalidateQueries({ queryKey: ['airQuality'] });
      qc.invalidateQueries({ queryKey: ['environment'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      Alert.alert('已更新', '天气和空气质量缓存已清, 主页数据将自动刷新');
    },
    onError: (e: any) => {
      Alert.alert('保存失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    },
  });

  const refreshMut = useMutation({
    mutationFn: refreshDetectedLocation,
    onSuccess: (loc) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ['profileLocation'] });
      qc.invalidateQueries({ queryKey: ['effectiveLocation'] });
      Alert.alert('已重新检测', loc.city ? `检测到: ${loc.city}` : '未检测到城市, 请手动设置');
    },
    onError: () => Alert.alert('检测失败', '请稍后再试'),
  });

  const gpsMut = useMutation({
    mutationFn: async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        throw new Error('你没授权定位, 去系统设置里开一下');
      }
      const pos = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.Balanced,
      });
      // 客户端先反查给 backend hint, 跳过 qweather 调用 (离线/qweather 故障也能跑)
      const hint = await reverseGeocodeOnDevice(pos.coords.latitude, pos.coords.longitude);
      const loc = await updateGPSLocation(pos.coords.latitude, pos.coords.longitude, hint);
      return { loc, coords: pos.coords };
    },
    onSuccess: ({ loc, coords }) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ['profileLocation'] });
      qc.invalidateQueries({ queryKey: ['effectiveLocation'] });
      qc.invalidateQueries({ queryKey: ['weather'] });
      qc.invalidateQueries({ queryKey: ['weatherForecast'] });
      qc.invalidateQueries({ queryKey: ['airQuality'] });
      qc.invalidateQueries({ queryKey: ['environment'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      Alert.alert(
        'GPS 定位成功',
        loc.city
          ? `定位到: ${loc.city}\n(${coords.latitude.toFixed(3)}, ${coords.longitude.toFixed(3)})`
          : '反查城市失败',
      );
    },
    onError: (e: any) => {
      Alert.alert('GPS 定位失败', e?.message || e?.response?.data?.detail || '请稍后再试');
    },
  });

  const handleSave = () => {
    if (useManual && !cityInput.trim()) {
      Alert.alert('请选择城市', '手动模式需要指定一个城市');
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    saveMut.mutate({ use: useManual, city: cityInput.trim() });
  };

  const tzMut = useMutation({
    // 手动模式锁定所选时区; 关掉手动 → 传 null 解锁, 恢复自动跟随设备
    mutationFn: (manualTz: string | null) => setManualTimezone(manualTz),
    onSuccess: (res) => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ['effectiveTimezone'] });
      qc.invalidateQueries({ queryKey: ['profileLocation'] });
      Alert.alert('已更新', `生效时区: ${res.timezone}（${TZ_SOURCE_LABEL[res.source] || res.source}）`);
    },
    onError: (e: any) => {
      Alert.alert('保存失败', e?.response?.data?.detail || e?.message || '请稍后再试');
    },
  });

  const handleSaveTz = () => {
    if (tzManual && !tzInput.trim()) {
      Alert.alert('请选择时区', '手动模式需要指定一个时区');
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    tzMut.mutate(tzManual ? tzInput.trim() : null);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>位置设置</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll}>
          {/* 当前状态卡 */}
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>当前生效</Text>
            <Text style={txt.currentCity}>
              {useManual && cityInput.trim()
                ? `${cityInput.trim()} (手动)`
                : data?.detected_location?.city
                  ? `${data.detected_location.city} (自动)`
                  : '未知'}
            </Text>
            {effective ? (
              <Text style={[txt.subLabel, { marginTop: 4 }]}>
                {formatProvenance(effective.source, effective.stale_minutes)}
              </Text>
            ) : null}
            <Text style={txt.hint}>
              天气、空气质量都基于此位置. 改了位置会立即清缓存重新拉.
            </Text>
          </View>

          {/* 自动检测 */}
          <View style={styles.card}>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <Text style={txt.rowLabel}>自动检测城市</Text>
                <Text style={txt.subLabel}>
                  按你访问后端的 IP 解析. 跨城市旅行时手动重新检测.
                </Text>
              </View>
            </View>
            <Text style={[txt.detected, { marginTop: spacing.sm }]}>
              当前检测: {data?.detected_location?.city || '未知'}
            </Text>
            <View style={styles.btnRow}>
              <TouchableOpacity
                style={[styles.secondaryBtn, { flex: 1 }]}
                onPress={() => refreshMut.mutate()}
                disabled={refreshMut.isPending || gpsMut.isPending}
                activeOpacity={0.7}
              >
                {refreshMut.isPending ? (
                  <ActivityIndicator size="small" color={c.brand} />
                ) : (
                  <Ionicons name="refresh-outline" size={16} color={c.brand} />
                )}
                <Text style={[txt.btnLabel, { color: c.brand, marginLeft: 6 }]}>
                  按 IP 重检
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.secondaryBtn, { flex: 1, backgroundColor: c.brand }]}
                onPress={() => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  gpsMut.mutate();
                }}
                disabled={refreshMut.isPending || gpsMut.isPending}
                activeOpacity={0.7}
              >
                {gpsMut.isPending ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Ionicons name="navigate-outline" size={16} color="#fff" />
                )}
                <Text style={[txt.btnLabel, { color: '#fff', marginLeft: 6 }]}>
                  用 GPS 定位
                </Text>
              </TouchableOpacity>
            </View>
            <Text style={[txt.subLabel, { marginTop: spacing.xs }]}>
              GPS 精到区/县, 首次需授权. IP 定位通常只到市级且可能偏差.
            </Text>
          </View>

          {/* 手动设定 */}
          <View style={styles.card}>
            <View style={styles.rowBetween}>
              <View style={{ flex: 1 }}>
                <Text style={txt.rowLabel}>手动指定城市</Text>
                <Text style={txt.subLabel}>
                  开启后, 天气和空气质量始终用你选的城市, 忽略 IP 检测.
                </Text>
              </View>
              <Switch
                value={useManual}
                onValueChange={(v) => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  setUseManual(v);
                }}
                trackColor={{ false: c.fill, true: c.brand }}
                thumbColor="#fff"
              />
            </View>

            {useManual && (
              <>
                <TextInput
                  value={cityInput}
                  onChangeText={setCityInput}
                  placeholder="输入城市名, 如: 北京"
                  placeholderTextColor={c.labelTertiary}
                  style={styles.input}
                  returnKeyType="done"
                  onSubmitEditing={handleSave}
                />
                <Text style={[txt.subLabel, { marginTop: spacing.sm }]}>常用:</Text>
                <View style={styles.chipsRow}>
                  {COMMON_CITIES.map(city => (
                    <TouchableOpacity
                      key={city}
                      style={[
                        styles.chip,
                        cityInput === city && { backgroundColor: c.brandLight, borderColor: c.brand },
                      ]}
                      onPress={() => {
                        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                        setCityInput(city);
                      }}
                    >
                      <Text style={[txt.chipText, cityInput === city && { color: c.brand }]}>
                        {city}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </>
            )}
          </View>

          <TouchableOpacity
            style={[styles.primaryBtn, saveMut.isPending && { opacity: 0.6 }]}
            onPress={handleSave}
            disabled={saveMut.isPending}
            activeOpacity={0.7}
          >
            {saveMut.isPending ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={txt.primaryBtnLabel}>保存</Text>
            )}
          </TouchableOpacity>

          <Text style={[txt.hint, { textAlign: 'center', marginTop: spacing.lg }]}>
            {useManual ? '手动模式下 GPS/IP 自动检测被忽略' : 'GPS 精度 > IP 检测,建议有需要时点一下.'}
          </Text>

          {/* 时区: 自动跟随设备所在地 + 手动锁定 */}
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>时区</Text>
            <Text style={txt.currentCity}>{tz?.timezone || 'Asia/Shanghai'}</Text>
            <Text style={[txt.subLabel, { marginTop: 4 }]}>
              数据源: {tz ? (TZ_SOURCE_LABEL[tz.source] || tz.source) : '加载中'}
              {tz?.detected_timezone ? ` · 设备: ${tz.detected_timezone}` : ''}
            </Text>
            <Text style={txt.hint}>
              用药时长、随访到期等「今天」按此时区的日历日计算. 平时自动跟随设备所在地.
            </Text>

            <View style={[styles.rowBetween, { marginTop: spacing.sm }]}>
              <View style={{ flex: 1 }}>
                <Text style={txt.rowLabel}>手动指定时区</Text>
                <Text style={txt.subLabel}>
                  开启后固定用你选的时区, 忽略设备检测 (出差不想被带跑时用).
                </Text>
              </View>
              <Switch
                value={tzManual}
                onValueChange={(v) => {
                  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                  setTzManual(v);
                }}
                trackColor={{ false: c.fill, true: c.brand }}
                thumbColor="#fff"
              />
            </View>

            {tzManual && (
              <View style={styles.chipsRow}>
                {COMMON_TIMEZONES.map(z => (
                  <TouchableOpacity
                    key={z}
                    style={[
                      styles.chip,
                      tzInput === z && { backgroundColor: c.brandLight, borderColor: c.brand },
                    ]}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                      setTzInput(z);
                    }}
                  >
                    <Text style={[txt.chipText, tzInput === z && { color: c.brand }]}>{z}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            <TouchableOpacity
              style={[styles.primaryBtn, tzMut.isPending && { opacity: 0.6 }]}
              onPress={handleSaveTz}
              disabled={tzMut.isPending}
              activeOpacity={0.7}
            >
              {tzMut.isPending ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={txt.primaryBtnLabel}>{tzManual ? '锁定时区' : '保存（自动跟随）'}</Text>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 40, alignItems: 'flex-start' },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl, gap: spacing.md },
    center: { paddingTop: 80, alignItems: 'center' },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md, gap: spacing.xs, ...shadows.subtle,
    },
    rowBetween: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
      gap: spacing.sm,
    },
    input: {
      borderWidth: 1, borderColor: c.separator, borderRadius: radii.sm,
      padding: spacing.sm, fontSize: 15, color: c.labelPrimary,
      marginTop: spacing.sm,
      backgroundColor: c.bgPrimary,
    },
    chipsRow: {
      flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: spacing.xs,
    },
    chip: {
      paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14,
      borderWidth: 1, borderColor: c.separator, backgroundColor: c.bgPrimary,
    },
    secondaryBtn: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      paddingVertical: 10, paddingHorizontal: spacing.md,
      borderRadius: radii.sm, backgroundColor: c.brandLight,
      marginTop: spacing.sm,
    },
    btnRow: {
      flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm,
    },
    primaryBtn: {
      backgroundColor: c.brand, borderRadius: radii.md,
      paddingVertical: 14, alignItems: 'center', justifyContent: 'center',
      marginTop: spacing.sm,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    sectionTitle: { fontSize: 13, fontWeight: '500', color: c.labelSecondary } as TextStyle,
    currentCity: { fontSize: 24, fontWeight: '700', color: c.labelPrimary, marginTop: 4 } as TextStyle,
    rowLabel: { fontSize: 15, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    subLabel: { fontSize: 12, color: c.labelTertiary, lineHeight: 17, marginTop: 2 } as TextStyle,
    detected: { fontSize: 13, color: c.labelSecondary } as TextStyle,
    hint: { fontSize: 12, color: c.labelTertiary, lineHeight: 17 } as TextStyle,
    chipText: { fontSize: 13, color: c.labelSecondary } as TextStyle,
    btnLabel: { fontSize: 14, fontWeight: '500' } as TextStyle,
    primaryBtnLabel: { fontSize: 16, fontWeight: '600', color: '#fff' } as TextStyle,
  };
}
