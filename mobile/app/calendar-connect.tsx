/**
 * 连接日历(CalDAV)—— 填地址/账号/应用专用密码 → 同步忙碌块,时点日程自动避开会议。
 * 凭据由你自己填、经 HTTPS 传后端加密存(后端绝不存明文、绝不进 LLM)。地址须 https。
 */
import React, { useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { revaColors as C } from '../constants/revaTheme';
import { getCalendarStatus, saveCalendarCredentials, syncCalendar, type CalendarStatus } from '../services/calendar';

export default function CalendarConnectScreen() {
  const qc = useQueryClient();
  const statusQ = useQuery<CalendarStatus>({ queryKey: ['calendar', 'status'], queryFn: getCalendarStatus });

  const [url, setUrl] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  const urlValid = url === '' || url.startsWith('https://');
  const canSave = url.startsWith('https://') && username.trim() !== '' && password !== '';

  const save = useMutation({
    mutationFn: async () => {
      await saveCalendarCredentials(url.trim(), username.trim(), password);
      return syncCalendar();
    },
    onSuccess: () => {
      setPassword('');
      qc.invalidateQueries({ queryKey: ['calendar', 'status'] });
      qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
    },
  });

  const resync = useMutation({
    mutationFn: () => syncCalendar(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calendar', 'status'] });
      qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
    },
  });

  const st = statusQ.data;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <Stack.Screen options={{ title: '连接日历' }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        {/* 状态 */}
        <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 14, marginBottom: 16 }}>
          {statusQ.isLoading ? (
            <ActivityIndicator />
          ) : st?.connected ? (
            <>
              <Text style={{ fontSize: 14, color: C.green500, fontWeight: '700' }}>✓ 已连接</Text>
              <Text style={{ fontSize: 12.5, color: C.ink2, marginTop: 4 }}>
                上次同步:{st.last_sync_at ? st.last_sync_at.replace('T', ' ').slice(0, 16) : '—'} · 今日忙碌 {st.busy_today ?? 0} 块
              </Text>
              {st.last_error ? <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 4 }}>上次错误:{st.last_error}</Text> : null}
              <Pressable
                onPress={() => resync.mutate()}
                disabled={resync.isPending}
                style={({ pressed }) => [{ marginTop: 10, alignSelf: 'flex-start', borderWidth: 1, borderColor: C.green500,
                  borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, opacity: pressed || resync.isPending ? 0.6 : 1 }]}
              >
                <Text style={{ color: C.green500, fontWeight: '600', fontSize: 13 }}>{resync.isPending ? '同步中…' : '立即同步'}</Text>
              </Pressable>
            </>
          ) : (
            <Text style={{ fontSize: 13, color: C.ink2 }}>未连接日历。填下面信息后,时点日程会自动避开你的会议。</Text>
          )}
        </View>

        {/* 凭据表单 */}
        <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 14 }}>
          <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 15, color: C.ink1 }}>
            {st?.connected ? '更新连接' : '连接 CalDAV 日历'}
          </Text>
          <Text style={{ fontSize: 12, color: C.ink2, marginTop: 4, lineHeight: 18 }}>
            用「应用专用密码」(不是主账号密码);地址须 https。凭据经 HTTPS 传后端加密存,不外发、不进 AI。
          </Text>
          <Field label="CalDAV 地址" value={url} onChange={setUrl} placeholder="https://caldav.icloud.com" valid={urlValid} autoCap={false} />
          <Field label="账号 / 邮箱" value={username} onChange={setUsername} placeholder="you@example.com" autoCap={false} />
          <Field label="应用专用密码" value={password} onChange={setPassword} placeholder="xxxx-xxxx-xxxx-xxxx" secure />
          {!urlValid ? <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 6 }}>地址须以 https:// 开头</Text> : null}
          <Pressable
            disabled={!canSave || save.isPending}
            onPress={() => save.mutate()}
            style={({ pressed }) => [{ marginTop: 14, backgroundColor: canSave ? C.green500 : C.ink3, borderRadius: 10,
              paddingVertical: 11, alignItems: 'center', opacity: pressed ? 0.85 : 1 }]}
          >
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>{save.isPending ? '保存并同步中…' : '保存并同步'}</Text>
          </Pressable>
          {save.isError ? (
            <Text style={{ fontSize: 12, color: '#D5503A', marginTop: 8 }}>
              连接/同步失败:请检查地址、账号、应用专用密码是否正确(地址须 https,且不可指向内网)。
            </Text>
          ) : null}
          {save.isSuccess ? <Text style={{ fontSize: 12.5, color: C.green500, marginTop: 8 }}>已连接并同步 ✓</Text> : null}
        </View>
      </ScrollView>
    </SafeAreaView>
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
        style={{ borderWidth: 1, borderColor: valid ? C.line : '#D5503A', borderRadius: 10,
          paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, color: C.ink1, backgroundColor: C.paper }}
      />
    </View>
  );
}
