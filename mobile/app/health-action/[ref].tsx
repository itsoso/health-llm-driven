import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, Pressable, ScrollView, Text, View } from 'react-native';
import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useTheme } from '../../hooks/useTheme';
import { fetchHealthNavigationAction, refreshHealthWeekNavigation, recordHealthNavigationEvent, validHealthActionRef, navigationErrorMessage, navigationStatusLabel, type HealthNavigationActionDetail, type NavigationEventInput } from '../../services/healthNavigation';

// This is an idempotency key, never a credential or a capability.
function operationId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
    const value = Math.floor(Math.random() * 16);
    return (char === 'x' ? value : (value & 3) | 8).toString(16);
  });
}
export default function HealthActionDetailScreen() {
  const params = useLocalSearchParams<{ ref: string }>();
  const ref = typeof params.ref === 'string' ? params.ref : '';
  const router = useRouter();
  const { c } = useTheme();
  const [action, setAction] = useState<HealthNavigationActionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [selected, setSelected] = useState<NavigationEventInput['event_type'] | null>(null);
  const [saving, setSaving] = useState(false);
  const attempt = useRef<NavigationEventInput | null>(null);
  const attemptRef = useRef(ref);
  const mounted = useRef(false);
  const epoch = useRef(0);
  const [reload, setReload] = useState(0);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') setReload(value => value + 1);
      else { epoch.current++; setAction(null); setSelected(null); }
    });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { subscription.remove(); clearInterval(timer); };
  }, []);
  const saveLock = useRef(false);
  const refreshLock = useRef(false);
  useFocusEffect(useCallback(() => {
    if (attemptRef.current !== ref) { attempt.current = null; attemptRef.current = ref; }
    const version = ++epoch.current;
    mounted.current = true;
    setSaving(false); setAction(null); setSelected(attempt.current?.event_type ?? null); setMessage(attempt.current ? '前次结果尚未确认，请核对后使用相同操作重试。' : ''); setLoading(true);
    if (!validHealthActionRef(ref)) {
      setMessage('此行动引用已失效或不可访问。'); setLoading(false);
      return () => { mounted.current = false; epoch.current++; };
    }
    fetchHealthNavigationAction(ref).then(value => { if (mounted.current && version === epoch.current) setAction(value); })
      .catch(error => { if (mounted.current && version === epoch.current) setMessage(navigationErrorMessage(error)); })
      .finally(() => { if (mounted.current && version === epoch.current) setLoading(false); });
    return () => { mounted.current = false; epoch.current++; setAction(null); };
  }, [ref, reload]));
  useEffect(() => {
    if (action?.expires_at && Date.parse(action.expires_at) <= now) {
      setAction(null); setSelected(null); setMessage('行动详情已过期，请更新并重新核对。');
    }
  }, [action, now]);
  const save = async () => {
    if (!action || !selected || saveLock.current || !action.can_confirm || action.safety_state !== 'allowed' || action.requires_health_review || ['withdrawn', 'unknown'].includes(action.execution_status) || (action.expires_at && Date.parse(action.expires_at) <= Date.now())) return;
    const version = epoch.current;
    saveLock.current = true; setSaving(true); setMessage('');
    const input = attempt.current ?? { event_type: selected, expected_revision: action.action_revision, operation_id: operationId() };
    attempt.current = input;
    try {
      await recordHealthNavigationEvent(ref, input);
      const fresh = await fetchHealthNavigationAction(ref);
      if (mounted.current && version === epoch.current) { setAction(fresh); setSelected(null); setMessage('已保存并刷新 Health 状态。'); }
      attempt.current = null;
    } catch (error) {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        attempt.current = null;
        if (mounted.current && version === epoch.current) setSelected(null);
        try {
          const fresh = await fetchHealthNavigationAction(ref);
          if (mounted.current && version === epoch.current) setAction(fresh);
        } catch { if (mounted.current && version === epoch.current) setAction(null); }
      } else if (status && status < 500) {
        attempt.current = null;
        if (mounted.current && version === epoch.current) { setSelected(null); setAction(null); }
      }
      if (mounted.current && version === epoch.current) setMessage(status === 409 ? navigationErrorMessage(error) : status ? navigationErrorMessage(error) : '结果尚未确认。请使用相同操作重试，或重新查看状态。');
    } finally {
      saveLock.current = false;
      if (mounted.current && version === epoch.current) setSaving(false);
    }
  };
  const canRecord = action?.can_confirm === true && action?.safety_state === 'allowed' && !action.requires_health_review
    && !['withdrawn', 'unknown'].includes(action.execution_status)
    && (!action.expires_at || Date.parse(action.expires_at) > now);
  const button = (label: string, onPress: () => void, disabled = false) => (
    <Pressable accessibilityRole="button" accessibilityLabel={label} disabled={disabled} onPress={onPress}
      style={{ padding: 14, borderRadius: 12, backgroundColor: c.bgCard, borderWidth: 1, borderColor: c.separator, opacity: disabled ? 0.5 : 1 }}>
      <Text style={{ color: c.brand }}>{label}</Text>
    </Pressable>
  );
  return <>
    <Stack.Screen options={{ title: 'Health 行动', headerShown: true, headerBackTitle: '返回' }} />
    <ScrollView style={{ flex: 1, backgroundColor: c.bgPrimary }} contentContainerStyle={{ padding: 24, gap: 14 }}>
      {loading ? <ActivityIndicator /> : null}
      {message ? <Text accessibilityRole="alert" style={{ color: c.labelSecondary }}>{message}</Text> : null}
      {action ? <>
        <Text style={{ fontSize: 22, color: c.labelPrimary, fontWeight: '700' }}>{action.title}</Text>
        <Text style={{ color: c.labelSecondary }}>{action.plan_date} · Health 原始行动</Text>
        <Text style={{ color: c.labelSecondary }}>{action.completion_criterion}</Text>
        <Text style={{ color: c.labelPrimary }}>{navigationStatusLabel[action.execution_status]}</Text>
        {!canRecord ? <Text style={{ color: c.labelSecondary }}>此行动需回到 Health 重新核对安全条件，当前仅供查看。</Text> : null}
        {canRecord && !selected ? <>
          {button('记录完成', () => setSelected('completed'))}
          {button('记录跳过', () => setSelected('skipped'))}
          {button('记录延期', () => setSelected('deferred'))}
        </> : null}
        {selected ? <View style={{ gap: 12 }}>
          <Text style={{ color: c.labelPrimary }}>请核对上方行动与完成标准。确认将记录为：{navigationStatusLabel[selected]}</Text>
          {button(saving ? '正在核对…' : '确认记录', () => { void save(); }, saving || !canRecord)}
          {!attempt.current ? button('取消', () => setSelected(null), saving) : null}
        </View> : null}
      </> : null}
      {button('更新并重新核对今日行动', () => {
        if (saveLock.current || refreshLock.current) return;
        refreshLock.current = true;
        const version = epoch.current;
        setLoading(true);
        refreshHealthWeekNavigation().then(() => { if (version === epoch.current) setReload(value => value + 1); })
          .catch(error => { if (version === epoch.current) { setMessage(navigationErrorMessage(error)); setLoading(false); } })
          .finally(() => { refreshLock.current = false; });
      }, saving || loading)}
      {button('返回健康周导航', () => router.push('/my-progress?navigation=week' as any), saving)}
    </ScrollView>
  </>;
}
