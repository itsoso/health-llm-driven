/**
 * 日历源管理(Calendar v2 / C2)—— 列出 / 启停 / 删除 / 立即同步 / 添加多源。
 * 添加支持 CalDAV(地址+账号+应用专用密码)与 ICS(只读订阅地址)。地址须 https。
 * 凭据经 HTTPS 传后端加密存,绝不外发、绝不进 AI(只读外部日历,不写回)。
 */
import React, { useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { revaColors as C } from '../constants/revaTheme';
import {
  addCalendarSource, deleteCalendarSource, listCalendarSources, syncCalendar, updateCalendarSource,
  type AddSourceInput, type CalendarProvider, type CalendarSource,
} from '../services/calendar';

export default function CalendarSourcesScreen() {
  const qc = useQueryClient();
  const sourcesQ = useQuery<CalendarSource[]>({ queryKey: ['calendar', 'sources'], queryFn: listCalendarSources });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['calendar', 'sources'] });
    qc.invalidateQueries({ queryKey: ['calendar', 'events'] });
    qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
  };

  const sync = useMutation({ mutationFn: syncCalendar, onSuccess: invalidate });
  const toggle = useMutation({
    mutationFn: (v: { id: number; enabled: boolean }) => updateCalendarSource(v.id, { sync_enabled: v.enabled }),
    onSuccess: invalidate,
  });
  const del = useMutation({
    mutationFn: (id: number) => deleteCalendarSource(id),
    onSuccess: invalidate,
  });

  const confirmDelete = (s: CalendarSource) => {
    Alert.alert('删除日历源', `删除「${s.name}」及其已同步事件?此操作不可撤销。`, [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: () => del.mutate(s.id) },
    ]);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <Stack.Screen options={{ title: '日历源' }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        {/* 同步全部 */}
        <Pressable
          onPress={() => sync.mutate()}
          disabled={sync.isPending}
          style={({ pressed }) => [{
            backgroundColor: C.green500, borderRadius: 10, paddingVertical: 11, alignItems: 'center',
            marginBottom: 16, opacity: pressed || sync.isPending ? 0.7 : 1,
          }]}
        >
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>
            {sync.isPending ? '同步中…' : '立即同步所有源'}
          </Text>
        </Pressable>
        {sync.isError ? (
          <Text style={{ fontSize: 12, color: '#D5503A', marginTop: -8, marginBottom: 12 }}>同步失败,请重试。</Text>
        ) : null}

        {/* 源列表 */}
        {sourcesQ.isLoading ? (
          <ActivityIndicator />
        ) : sourcesQ.isError ? (
          <Text style={{ fontSize: 13, color: C.ink2 }}>取不到日历源,下拉重试。</Text>
        ) : (sourcesQ.data?.length ?? 0) === 0 ? (
          <Text style={{ fontSize: 13, color: C.ink2, lineHeight: 20, marginBottom: 8 }}>
            还没有日历源。下面添加 CalDAV 或 ICS 源,会议会和健康日程并在一条时间轴。
          </Text>
        ) : (
          <View style={{ gap: 10, marginBottom: 8 }}>
            {sourcesQ.data!.map((s) => (
              <SourceCard
                key={s.id}
                source={s}
                onToggle={(enabled) => toggle.mutate({ id: s.id, enabled })}
                onDelete={() => confirmDelete(s)}
                busy={toggle.isPending || del.isPending}
              />
            ))}
          </View>
        )}

        <View style={{ height: 1, backgroundColor: C.line, marginVertical: 18 }} />

        <AddSourceForm onAdded={invalidate} />
      </ScrollView>
    </SafeAreaView>
  );
}

function SourceCard({ source, onToggle, onDelete, busy }: {
  source: CalendarSource; onToggle: (enabled: boolean) => void; onDelete: () => void; busy: boolean;
}) {
  const providerLabel = source.provider === 'ics' ? 'ICS 订阅' : 'CalDAV';
  return (
    <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 14 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: source.color || C.green500 }} />
        <Text style={{ flex: 1, fontSize: 15, fontWeight: '700', color: C.ink1 }} numberOfLines={1}>{source.name}</Text>
        <Switch value={source.sync_enabled} onValueChange={onToggle} disabled={busy} />
      </View>
      <Text style={{ fontSize: 12, color: C.ink2, marginTop: 6 }}>
        {providerLabel} · 只读
        {source.last_sync_at ? ` · 上次同步 ${source.last_sync_at.replace('T', ' ').slice(0, 16)}` : ' · 尚未同步'}
      </Text>
      {source.last_error ? (
        <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 4, lineHeight: 17 }}>上次错误:{source.last_error}</Text>
      ) : null}
      <Pressable onPress={onDelete} hitSlop={8} style={{ marginTop: 10, alignSelf: 'flex-start' }}>
        <Text style={{ fontSize: 13, color: '#D5503A', fontWeight: '600' }}>删除</Text>
      </Pressable>
    </View>
  );
}

function AddSourceForm({ onAdded }: { onAdded: () => void }) {
  const [provider, setProvider] = useState<CalendarProvider>('caldav');
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const urlValid = url === '' || url.startsWith('https://');
  const canAdd =
    name.trim() !== '' &&
    url.startsWith('https://') &&
    (provider === 'ics' || (username.trim() !== '' && password !== ''));

  const add = useMutation({
    mutationFn: () => {
      const input: AddSourceInput = { provider, name: name.trim(), url: url.trim() };
      if (provider === 'caldav') {
        input.username = username.trim();
        input.password = password;
      }
      return addCalendarSource(input);
    },
    onSuccess: () => {
      setName(''); setUrl(''); setUsername(''); setPassword('');
      onAdded();
    },
  });

  return (
    <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 14 }}>
      <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 15, color: C.ink1 }}>添加日历</Text>
      <Text style={{ fontSize: 12, color: C.ink2, marginTop: 4, lineHeight: 18 }}>
        只读外部日历;凭据经 HTTPS 传后端加密存,不外发、不进 AI。地址须 https。
      </Text>

      {/* provider 切换 */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
        <ProviderTab label="CalDAV" active={provider === 'caldav'} onPress={() => setProvider('caldav')} />
        <ProviderTab label="ICS 订阅" active={provider === 'ics'} onPress={() => setProvider('ics')} />
      </View>

      <Field label="名称" value={name} onChange={setName} placeholder="如 工作日历" />
      <Field
        label={provider === 'ics' ? 'ICS 订阅地址' : 'CalDAV 地址'}
        value={url}
        onChange={setUrl}
        placeholder={provider === 'ics' ? 'https://…/calendar.ics' : 'https://caldav.icloud.com'}
        valid={urlValid}
        autoCap={false}
      />
      {provider === 'caldav' ? (
        <>
          <Field label="账号 / 邮箱" value={username} onChange={setUsername} placeholder="you@example.com" autoCap={false} />
          <Field label="应用专用密码" value={password} onChange={setPassword} placeholder="xxxx-xxxx-xxxx-xxxx" secure />
        </>
      ) : null}
      {!urlValid ? <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 6 }}>地址须以 https:// 开头</Text> : null}

      <Pressable
        disabled={!canAdd || add.isPending}
        onPress={() => add.mutate()}
        style={({ pressed }) => [{
          marginTop: 14, backgroundColor: canAdd ? C.green500 : C.ink3, borderRadius: 10,
          paddingVertical: 11, alignItems: 'center', opacity: pressed ? 0.85 : 1,
        }]}
      >
        <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>{add.isPending ? '添加中…' : '添加并同步'}</Text>
      </Pressable>
      {add.isError ? (
        <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 8, lineHeight: 17 }}>
          添加失败:请检查地址、账号、应用专用密码(地址须 https,且不可指向内网)。
        </Text>
      ) : null}
      {add.isSuccess ? <Text style={{ fontSize: 12.5, color: C.green500, marginTop: 8 }}>已添加 ✓</Text> : null}
    </View>
  );
}

function ProviderTab({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [{
        flex: 1, borderRadius: 10, paddingVertical: 8, alignItems: 'center',
        backgroundColor: active ? C.green50 : C.paper,
        borderWidth: 1, borderColor: active ? C.green500 : C.line, opacity: pressed ? 0.8 : 1,
      }]}
    >
      <Text style={{ fontSize: 13, fontWeight: '600', color: active ? C.green600 : C.ink2 }}>{label}</Text>
    </Pressable>
  );
}

function Field({ label, value, onChange, placeholder, secure, valid = true, autoCap = true }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
  secure?: boolean; valid?: boolean; autoCap?: boolean;
}) {
  return (
    <View style={{ marginTop: 12 }}>
      <Text style={{ fontSize: 12, color: C.ink2, marginBottom: 4 }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={C.ink3}
        secureTextEntry={secure}
        autoCapitalize={autoCap ? 'sentences' : 'none'}
        autoCorrect={false}
        style={{
          borderWidth: 1, borderColor: valid ? C.line : '#D5503A', borderRadius: 10,
          paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, color: C.ink1, backgroundColor: C.paper,
        }}
      />
    </View>
  );
}
