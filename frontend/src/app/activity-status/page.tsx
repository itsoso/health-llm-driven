'use client';
import { useQuery } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';
interface ActivityRecord {
  id: number; status_text: string; category: string; start_time: string;
  actual_end_time?: string | null; is_active: boolean;
}
const categories: Record<string, string> = {
  studying: '学习', working: '工作', exercising: '运动', resting: '休息', entertainment: '娱乐', other: '其他',
};
function timestamp(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '时间未提供' : date.toLocaleString('zh-CN');
}
function ActivityContent() {
  const { user } = useAuth();
  const current = useQuery({
    queryKey: ['activity-status', 'current', user?.id],
    queryFn: async () => (await api.get<ActivityRecord | null>('/activity-status/records/me/current')).data,
    enabled: !!user?.id,
  });
  const history = useQuery({
    queryKey: ['activity-status', 'history', user?.id],
    queryFn: async () => (await api.get<ActivityRecord[]>('/activity-status/records/me', { params: { limit: 20 } })).data,
    enabled: !!user?.id,
  });
  return <main className="min-h-screen bg-gray-50 p-4 md:p-8"><div className="max-w-4xl mx-auto">
    <h1 className="text-2xl font-bold mb-6">活动状态</h1>
    <section className="bg-white rounded-2xl p-6 shadow-sm mb-6">
      <h2 className="text-lg font-semibold mb-3">当前记录</h2>
      {current.isLoading ? <p role="status">加载当前活动…</p> : current.isError ? <div role="alert">当前活动加载失败。<button className="underline ml-2" onClick={() => current.refetch()}>重试当前活动</button></div>
        : current.data ? <><p className="text-xl">{current.data.status_text}</p><p className="text-gray-500 mt-2">开始时间：{timestamp(current.data.start_time)}</p></> : <p className="text-gray-500">暂无进行中的活动记录</p>}
    </section>
    <section className="bg-white rounded-2xl p-6 shadow-sm">
      <h2 className="text-lg font-semibold mb-3">最近活动记录</h2>
      {history.isLoading ? <p role="status">加载活动记录…</p> : history.isError ? <div role="alert">活动记录加载失败。<button className="underline ml-2" onClick={() => history.refetch()}>重试活动记录</button></div>
        : !history.data?.length ? <p className="text-gray-500">暂无活动记录</p> : <ul className="divide-y">{history.data.map(record => <li key={record.id} className="py-4">
          <div className="flex justify-between gap-3"><span className="font-medium">{record.status_text}</span><span className="text-gray-500">{categories[record.category] || '其他'}</span></div>
          <p className="text-sm text-gray-500 mt-2">{timestamp(record.start_time)} · {record.is_active ? '进行中' : record.actual_end_time ? `结束于 ${timestamp(record.actual_end_time)}` : '结束时间未记录'}</p>
        </li>)}</ul>}
    </section>
  </div></main>;
}
export default function ActivityStatusPage() { return <ProtectedRoute><ActivityContent /></ProtectedRoute>; }
