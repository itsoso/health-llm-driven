'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { familyApi, type FamilyMemberHealth } from '@/services/api/family';
const RELATIONSHIP: Record<string, string> = { self: '本人', father: '爸爸', mother: '妈妈', spouse: '配偶', daughter: '女儿', son: '儿子', child: '子女', sibling: '兄弟姐妹', other: '其他' };
const STATUS: Record<string, string> = { active: '进行中', improving: '好转中', resolved: '已结束' };
const EXAM: Record<string, string> = { blood: '血液检查', blood_routine: '血常规', blood_test: '血液检查', biochemistry: '生化检查', imaging: '影像检查', physical: '体检', other: '其他检查' };
function conclusionText(value: unknown) {
  if (typeof value === 'string') return value;
  if (!value || typeof value !== 'object') return '';
  const item = value as Record<string, unknown>;
  return ['title', 'description', 'content', 'text', 'recommendation'].map(key => item[key]).filter(text => typeof text === 'string').join(' · ');
}
export default function FamilyMemberRecords({ userId, onClose }: { userId: number; onClose: () => void }) {
  const [records, setRecords] = useState<FamilyMemberHealth | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const request = useRef<AbortController | null>(null);
  const load = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(''); setRecords(null);
    try {
      const response = await familyApi.getMemberHealth(userId, controller.signal);
      if (!controller.signal.aborted) setRecords(response.data);
    } catch (cause) {
      if (controller.signal.aborted) return;
      const status = (cause as { response?: { status?: number } }).response?.status;
      setError(status === 403 || status === 404 ? '暂时无法查看，家庭关系或共享权限可能已变更。' : '健康记录加载失败，请检查网络后重试。');
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }, [userId]);
  useEffect(() => {
    void load();
    const refreshVisible = () => { if (document.visibilityState === 'visible') void load(); };
    window.addEventListener('focus', refreshVisible);
    const timer = window.setInterval(refreshVisible, 30_000);
    return () => { request.current?.abort(); window.clearInterval(timer); window.removeEventListener('focus', refreshVisible); };
  }, [load]);
  const member = records?.member;
  const name = member?.name || member?.nickname || '家人';
  return <section role="dialog" aria-modal="true" aria-label="家人健康记录" className="fixed inset-0 z-50 bg-gray-50 overflow-y-auto p-4">
    <div className="max-w-3xl mx-auto space-y-4">
      <button onClick={onClose} className="text-blue-700">关闭健康记录</button>
      <h2 className="font-bold text-xl">{member?.name && member?.nickname && member.name !== member.nickname ? `${name}（${member.nickname}）` : name}</h2>
      <p>{member ? RELATIONSHIP[member.relationship_type] || '家人' : ''} · 只读健康记录</p>
      <p className="text-sm text-gray-600">使用你的当前账号查看家人已共享的原始记录，不修改报告或用药。</p>
      {loading && <p role="status">正在读取共享健康记录…</p>}
      {error && <><p role="alert" className="text-red-700">{error}</p><button onClick={() => void load()}>重试</button></>}
      {records && <>
        <button onClick={() => void load()} className="text-blue-700">刷新记录</button>
        <h3 className="font-semibold">检查报告</h3>
        {!records.reports.length && <p>暂无检查报告</p>}
        {records.reports.map(report => <article key={report.id} className="bg-white border rounded-xl p-4 space-y-3">
          <h4 className="font-medium">{report.exam_date} · {EXAM[report.exam_type || ''] || report.exam_type || '检查报告'}{report.hospital_name ? ` · ${report.hospital_name}` : ''}</h4>
          {report.overall_assessment && <p className="whitespace-pre-wrap">{report.overall_assessment}</p>}
          {report.notes && <p className="whitespace-pre-wrap">{report.notes}</p>}
          {(report.conclusions || []).map((conclusion, index) => <p key={index}>{conclusionText(conclusion)}</p>)}
          <dl className="space-y-3">{report.items.map(item => <div key={item.id} className="border-t pt-2">
            <dt className="font-medium">{item.item_name}</dt><dd>{item.display_value}{item.unit ? ` ${item.unit}` : ''}</dd>
            {item.is_abnormal && item.is_abnormal !== 'normal' && <dd className="text-red-700">{{ high: '偏高', low: '偏低', abnormal: '异常' }[item.is_abnormal] || '异常标记'}</dd>}
            {item.reference_range && <dd className="text-sm text-gray-600">参考范围：{item.reference_range}</dd>}
            {item.notes && <dd>{item.notes}</dd>}
          </div>)}</dl>
        </article>)}
        <h3 className="font-semibold">病程与近况</h3>
        {!records.episodes.length && <p>暂无病程记录</p>}
        {records.episodes.map(episode => <article key={episode.id} className="bg-white border rounded-xl p-4 space-y-3">
          <h4 className="font-medium">{episode.name} · {STATUS[episode.status] || episode.status}</h4>
          <p>{episode.start_date}{episode.end_date ? ` 至 ${episode.end_date}` : ' 起'}</p>
          {episode.notes && <p className="whitespace-pre-wrap">{episode.notes}</p>}
          {episode.updates.map(update => <div key={update.id} className="border-t pt-2"><p>{update.update_date}{update.status ? ` · ${STATUS[update.status] || update.status}` : ''}</p><p className="whitespace-pre-wrap">{update.notes}</p></div>)}
        </article>)}
        {(records.reports.length >= records.limit || records.episodes.length >= records.limit) && <p>当前展示最近 {records.limit} 份报告和 {records.limit} 条病程。</p>}
      </>}
    </div>
  </section>;
}
