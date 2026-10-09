import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, AppState, Alert, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';
import { useTheme } from '../../hooks/useTheme';
import { fetchHealthWeekNavigation, refreshHealthWeekNavigation, fetchHealthNavigationGrants, revokeHealthNavigationGrant, navigationErrorMessage, navigationStatusLabel, validHealthActionRef, type HealthWeekNavigation as Week, type NavigationGrant } from '../../services/healthNavigation';

export default function HealthWeekNavigation() {
  const { c } = useTheme();
  const router = useRouter();
  const [data, setData] = useState<Week | null>(null);
  const [grants, setGrants] = useState<NavigationGrant[]>([]);
  const [grantError, setGrantError] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState(false);
  const updateLock = React.useRef(false);
  const focusVersion = React.useRef(0);
  const [now, setNow] = useState(Date.now());
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') setRefresh(value => value + 1);
      else { focusVersion.current++; setData(null); setGrants([]); }
    });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { subscription.remove(); clearInterval(timer); };
  }, []);
  useFocusEffect(useCallback(() => {
    const version = ++focusVersion.current;
    setData(null); setGrants([]); setMessage(''); setGrantError(''); setLoading(true);
    fetchHealthWeekNavigation().then(value => { if (version === focusVersion.current) setData(value); })
      .catch(error => { if (version === focusVersion.current) setMessage(navigationErrorMessage(error)); })
      .finally(() => { if (version === focusVersion.current) setLoading(false); });
    fetchHealthNavigationGrants().then(value => { if (version === focusVersion.current) setGrants(value); })
      .catch(() => { if (version === focusVersion.current) setGrantError('暂时无法查询连接授权，请重试。'); });
    return () => { focusVersion.current++; setData(null); setGrants([]); };
  }, [refresh]));
  const button = (label: string, onPress: () => void, disabled = false) => (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} disabled={disabled}
      style={{ padding: 14, borderRadius: 12, borderWidth: 1, borderColor: c.separator, backgroundColor: c.bgCard, opacity: disabled ? 0.5 : 1 }}>
      <Text style={{ color: c.brand }}>{label}</Text>
    </Pressable>
  );
  const update = async () => {
    if (updateLock.current) return;
    updateLock.current = true;
    const version = focusVersion.current;
    setUpdating(true); setMessage('');
    try {
      await refreshHealthWeekNavigation();
      if (version === focusVersion.current) setRefresh(value => value + 1);
    } catch (error) { if (version === focusVersion.current) setMessage(navigationErrorMessage(error)); }
    finally { updateLock.current = false; setUpdating(false); }
  };
  const revoke = (grant: NavigationGrant) => Alert.alert('撤销连接授权', '撤销后对方将无法继续读取。已读取内容无法远程追回。', [
    { text: '取消', style: 'cancel' },
    { text: '撤销', style: 'destructive', onPress: () => {
      const version = focusVersion.current;
      revokeHealthNavigationGrant(grant.grant_id).then(() => { if (version === focusVersion.current) setRefresh(value => value + 1); })
        .catch(() => { if (version === focusVersion.current) setGrantError('撤销失败，授权状态尚未改变，请重试。'); });
    } },
  ]);
  useEffect(() => {
    if (data?.expires_at && Date.parse(data.expires_at) <= now) {
      setData(null); setMessage('健康摘要已过期，请更新或重新读取。');
    }
  }, [data, now]);
  const ready = data && ['ready', 'partial'].includes(data.availability);
  const expired = data?.expires_at && Date.parse(data.expires_at) <= now;
  return <>
    <Stack.Screen options={{ title: '健康周导航', headerShown: true, headerBackTitle: '返回' }} />
    <ScrollView style={{ flex: 1, backgroundColor: c.bgPrimary }} contentContainerStyle={{ padding: 24, gap: 14 }}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={() => setRefresh(value => value + 1)} />}>
      <Text style={{ color: c.labelPrimary, fontSize: 22, fontWeight: '700' }}>健康周导航</Text>
      {loading ? <ActivityIndicator /> : null}
      {message ? <Text accessibilityRole="alert" style={{ color: c.labelSecondary }}>{message}</Text> : null}
      {data?.availability === 'not_generated' ? <Text style={{ color: c.labelSecondary }}>尚未生成可用的健康行动快照。</Text> : null}
      {data?.availability === 'unavailable' ? <Text style={{ color: c.labelSecondary }}>健康摘要暂时不可用，请重试。</Text> : null}
      {ready && data ? <>
        <Text style={{ color: c.labelSecondary }}>{data.review_window.start_date} → {data.review_window.end_date} · 含今天的滚动 7 天</Text>
        <Text style={{ color: c.labelTertiary }}>时区：{data.timezone}（{data.timezone_source}）</Text>
        <Text style={{ color: c.labelSecondary }}>已记录 {data.review.recorded_days}/{data.review.window_days} 天</Text>
        <Text style={{ color: c.labelSecondary }}>已完成 {data.review.completed_occurrences} · 已跳过 {data.review.skipped_occurrences} · 已延期 {data.review.deferred_occurrences} · 未知 {data.review.unknown_occurrences}</Text>
        <Text style={{ color: c.labelTertiary }}>{data.review.claim_boundary}</Text>
        <Text style={{ color: c.labelTertiary }}>来源截至：{data.source_as_of ?? '来源时间未知'}</Text>
        {data.availability === 'partial' ? <Text style={{ color: c.labelSecondary }}>部分数据缺失，空白不代表未完成或健康正常。</Text> : null}
        {expired ? <Text style={{ color: c.labelSecondary }}>快照已过期，请更新后核对安全条件。</Text> : null}
        {data.actions.map(action => <View key={action.action_ref} style={{ padding: 16, borderRadius: 16, backgroundColor: c.bgCard, gap: 8 }}>
          <Text style={{ color: c.labelPrimary, fontWeight: '700' }}>{action.share_title}</Text>
          <Text style={{ color: c.labelSecondary }}>{action.share_completion_criterion}</Text>
          <Text style={{ color: c.labelSecondary }}>{navigationStatusLabel[action.execution_status]}</Text>
          {action.safety_state !== 'allowed' || action.requires_health_review || expired ? <Text style={{ color: c.labelSecondary }}>请回到 Health 核对，安全条件尚未确认。</Text> : null}
          {validHealthActionRef(action.action_ref) ? button('查看并核对行动', () => router.push({ pathname: '/health-action/[ref]', params: { ref: action.action_ref } } as any)) : null}
        </View>)}
        {!data.actions.length ? <Text style={{ color: c.labelSecondary }}>当前没有可分享行动；健康细节请在 Health 中核对。</Text> : null}
      </> : null}
      {button(updating ? '正在更新…' : '更新今日健康行动', () => { void update(); }, updating)}
      <Text style={{ color: c.labelTertiary }}>更新会重新生成今日行动并核对安全条件；查看摘要不会自动生成行动。</Text>
      {button('查看长期健康进展', () => router.push('/my-progress' as any))}
      <Text style={{ color: c.labelPrimary, fontWeight: '700' }}>LifeNav 连接授权</Text>
      {grantError ? <Text style={{ color: c.labelSecondary }}>{grantError}</Text> : grants.length ? grants.map(grant => <View key={grant.grant_id} style={{ gap: 8 }}>
        <Text style={{ color: c.labelSecondary }}>{grant.recipient_id} · {grant.revoked_at ? '已撤销' : grant.connected ? '已连接' : '未连接或已到期'} · 到期 {grant.expires_at}</Text>
        {!grant.revoked_at ? button('撤销此连接', () => revoke(grant)) : <Text style={{ color: c.labelSecondary }}>已撤销</Text>}
      </View>) : <Text style={{ color: c.labelSecondary }}>暂无连接授权。接收端完成核验后才能连接。</Text>}
    </ScrollView>
  </>;
}
