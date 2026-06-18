/**
 * 今日时间轴 —— timing-solver 求解的当日药/补剂/动作时点(GET /schedule/today)。
 * 顶部可设上下班时间;保存后浮动提醒会避开工作时段,时间轴随之动态变。
 * 渲染 disclaimer hedge(后端随响应带出):时点为建议,遵医嘱,不替代处方。
 */
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { revaColors as C } from '../constants/revaTheme';
import {
  getTodaySchedule, getWorkHours, updateWorkHours, formatPrescription,
  type TodaySchedule, type WorkHours, type ScheduleItem,
} from '../services/schedule';
import { logMedication } from '../services/medications';

// 时间轴上可「已服」打卡的域(写依从,走 DB 兜底的 /medication/logs 幂等路径)。
const CONFIRMABLE = new Set(['medication', 'supplement']);

const DOMAIN_LABEL: Record<string, string> = {
  medication: '药', supplement: '补剂', diet: '饮食',
  movement: '运动', sleep: '睡眠', checkup: '复查',
};
const DOMAIN_COLOR: Record<string, string> = {
  medication: C.green500, supplement: '#1F8A5B', diet: '#C98A1E',
  movement: '#2A6FDB', sleep: '#7A5AF0', checkup: '#D5503A',
};

const HHMM = /^([01]?\d|2[0-3]):[0-5]\d$/;

export default function DayScheduleScreen() {
  const qc = useQueryClient();
  const schedQ = useQuery<TodaySchedule>({ queryKey: ['schedule', 'today'], queryFn: getTodaySchedule });
  const whQ = useQuery<WorkHours>({ queryKey: ['work-hours'], queryFn: getWorkHours });

  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  useEffect(() => {
    if (whQ.data) {
      setStart(whQ.data.work_start_time ?? '');
      setEnd(whQ.data.work_end_time ?? '');
    }
  }, [whQ.data]);

  const startValid = start === '' || HHMM.test(start);
  const endValid = end === '' || HHMM.test(end);
  const save = useMutation({
    mutationFn: () => updateWorkHours(start || null, end || null),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['work-hours'] });
      qc.invalidateQueries({ queryKey: ['schedule', 'today'] });
    },
  });

  // 已服打卡:点时间轴上的药/补剂项 → 在其计划时点记一笔已服(幂等,DB 兜底)。
  const [done, setDone] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<string | null>(null);
  const confirmTaken = async (it: ScheduleItem) => {
    const mid = Number(it.id.split(':')[1]);
    if (!mid || done.has(it.id) || pending) return;
    setPending(it.id);
    try {
      await logMedication({ medication_id: mid, taken_time: it.time, status: 'taken' });
      setDone((p) => new Set(p).add(it.id));
    } catch {
      // 写依从失败 → 不标已服(不假装成功);用户可重试
    } finally {
      setPending(null);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.paper }} edges={['top']}>
      <Stack.Screen options={{ title: '今日时间轴' }} />
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        {/* 上下班设置 */}
        <View style={{ backgroundColor: C.surface, borderRadius: 14, padding: 14, marginBottom: 16 }}>
          <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 15, color: C.ink1 }}>工作时间</Text>
          <Text style={{ fontSize: 12.5, color: C.ink2, marginTop: 4, lineHeight: 18 }}>
            设了上下班,浮动提醒会避开工作时段(药/补剂/餐的锚点时点不受影响)。
          </Text>
          <View style={{ flexDirection: 'row', gap: 12, marginTop: 12 }}>
            <TimeField label="上班" value={start} onChange={setStart} valid={startValid} />
            <TimeField label="下班" value={end} onChange={setEnd} valid={endValid} />
          </View>
          <Pressable
            disabled={!startValid || !endValid || save.isPending}
            onPress={() => save.mutate()}
            style={({ pressed }) => [{
              marginTop: 12, backgroundColor: (!startValid || !endValid) ? C.ink3 : C.green500,
              borderRadius: 10, paddingVertical: 10, alignItems: 'center', opacity: pressed ? 0.8 : 1,
            }]}
          >
            <Text style={{ color: '#fff', fontWeight: '700', fontSize: 14 }}>
              {save.isPending ? '保存中…' : '保存'}
            </Text>
          </Pressable>
          {save.isError ? <Text style={{ color: '#D5503A', fontSize: 12, marginTop: 6 }}>保存失败,请重试</Text> : null}
        </View>

        {/* 时间轴 */}
        <Text style={{ fontFamily: 'NotoSansSC', fontWeight: '700', fontSize: 15, color: C.ink1, marginBottom: 8 }}>
          今日时点
        </Text>
        {schedQ.isLoading ? (
          <ActivityIndicator style={{ marginTop: 24 }} />
        ) : schedQ.isError ? (
          <Text style={{ color: C.ink2, fontSize: 13 }}>暂时取不到日程,稍后重试。</Text>
        ) : (schedQ.data?.scheduled?.length ?? 0) === 0 ? (
          <Text style={{ color: C.ink2, fontSize: 13, lineHeight: 20 }}>
            还没有可排的时点 —— 添加在服的药/补剂后,这里会按药代/餐锚/工作时间排出当日时间轴。
          </Text>
        ) : (
          <View style={{ backgroundColor: C.surface, borderRadius: 14, overflow: 'hidden' }}>
            {schedQ.data!.scheduled.map((it: ScheduleItem, i: number) => (
              <View
                key={it.id}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 14,
                  borderTopWidth: i === 0 ? 0 : 1, borderTopColor: C.line,
                }}
              >
                <Text style={{ fontFamily: 'IBMPlexMono', fontSize: 15, fontWeight: '700', color: C.ink1, width: 52 }}>
                  {it.time}
                </Text>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: DOMAIN_COLOR[it.domain] ?? C.ink3 }} />
                <View style={{ flex: 1 }}>
                  <Text
                    style={{ fontSize: 14, color: done.has(it.id) ? C.ink3 : C.ink1,
                             textDecorationLine: done.has(it.id) ? 'line-through' : 'none' }}
                    numberOfLines={1}
                  >
                    {it.title}
                  </Text>
                  {(() => {
                    const { primary, geneNote } = formatPrescription(it.domain, it.prescription);
                    if (!primary && !geneNote) return null;
                    return (
                      <Text style={{ fontSize: 11.5, color: C.ink2, marginTop: 2, lineHeight: 16 }} numberOfLines={3}>
                        {primary}
                        {geneNote ? `${primary ? '\n' : ''}${geneNote}` : ''}
                      </Text>
                    );
                  })()}
                </View>
                {CONFIRMABLE.has(it.domain) ? (
                  done.has(it.id) ? (
                    <Text style={{ fontSize: 13, color: C.green500, fontWeight: '700' }}>✓ 已服</Text>
                  ) : (
                    <Pressable
                      onPress={() => confirmTaken(it)}
                      disabled={pending === it.id}
                      hitSlop={8}
                      style={({ pressed }) => [{
                        borderWidth: 1, borderColor: C.green500, borderRadius: 8,
                        paddingHorizontal: 10, paddingVertical: 5, opacity: pressed || pending === it.id ? 0.6 : 1,
                      }]}
                    >
                      <Text style={{ fontSize: 12.5, color: C.green500, fontWeight: '600' }}>
                        {pending === it.id ? '…' : '已服'}
                      </Text>
                    </Pressable>
                  )
                ) : (
                  <Text style={{ fontSize: 11, color: C.ink2 }}>{DOMAIN_LABEL[it.domain] ?? it.domain}</Text>
                )}
              </View>
            ))}
          </View>
        )}

        {/* 顺延项 */}
        {(schedQ.data?.deferred?.length ?? 0) > 0 ? (
          <View style={{ marginTop: 14 }}>
            <Text style={{ fontSize: 12.5, color: C.ink2, marginBottom: 6 }}>顺延(静默窗/配额)</Text>
            {schedQ.data!.deferred.map((d) => (
              <Text key={d.id} style={{ fontSize: 12.5, color: C.ink2, lineHeight: 18 }}>· {d.title} —— {d.reason}</Text>
            ))}
          </View>
        ) : null}

        {/* disclaimer hedge */}
        {schedQ.data?.disclaimer ? (
          <Text style={{ fontSize: 11, color: C.ink3, lineHeight: 16, marginTop: 18 }}>{schedQ.data.disclaimer}</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function TimeField({ label, value, onChange, valid }: {
  label: string; value: string; onChange: (v: string) => void; valid: boolean;
}) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ fontSize: 12, color: C.ink2, marginBottom: 4 }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder="09:00"
        placeholderTextColor={C.ink3}
        keyboardType="numbers-and-punctuation"
        maxLength={5}
        style={{
          borderWidth: 1, borderColor: valid ? C.line : '#D5503A', borderRadius: 10,
          paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, color: C.ink1,
          fontFamily: 'IBMPlexMono', backgroundColor: C.paper,
        }}
      />
    </View>
  );
}
