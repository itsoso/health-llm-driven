'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi, type FamilyInvitation } from '@/services/api/family';

const RELATIONSHIPS: Record<string, string> = {
  father: '爸爸', mother: '妈妈', spouse: '配偶', child: '子女', daughter: '女儿', son: '儿子', sibling: '兄弟姐妹', other: '其他',
};
function errorText(error: unknown): string {
  const cause = error as { response?: { data?: { detail?: unknown } }; message?: string };
  return typeof cause.response?.data?.detail === 'string' ? cause.response.data.detail : cause.message || '操作失败，请重试';
}
export default function InvitePage() {
  return <ProtectedRoute><InviteContent /></ProtectedRoute>;
}
function InviteContent() {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<{ group_name: string | null; is_owner: boolean } | null>(null);
  const [invitation, setInvitation] = useState<FamilyInvitation | null>(null);
  const [groupName, setGroupName] = useState('我家');
  const [code, setCode] = useState('');
  const [relationship, setRelationship] = useState('other');
  const [nickname, setNickname] = useState('');
  const [consented, setConsented] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [loadError, setLoadError] = useState(false);
  const [success, setSuccess] = useState('');
  const reload = useCallback(async () => {
    setLoadError(false);
    try { setDashboard((await familyApi.getDashboard()).data); }
    catch (cause) { setError(errorText(cause)); setLoadError(true); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  const create = async () => {
    if (!dashboard || pending) return;
    setPending(true); setError(''); setInvitation(null);
    try {
      if (!dashboard.group_name) {
        await familyApi.createGroup(groupName.trim());
        await reload();
      }
      setInvitation((await familyApi.createInvitation()).data);
    } catch (cause) { setError(errorText(cause)); }
    finally { setPending(false); }
  };
  const accept = async () => {
    if (!consented || pending || !/^[A-Z0-9]{6}$/.test(code.trim().toUpperCase())) return;
    setPending(true); setError(''); setSuccess('');
    try {
      const response = await familyApi.acceptInvitation({ code: code.trim().toUpperCase(), relationship_type: relationship, nickname: nickname.trim() });
      setSuccess(`已加入${response.data.group_name}。家庭创建者现在可以只读查看你的共享健康记录。`);
      setCode(''); setConsented(false);
      await reload();
    } catch (cause) { setError(errorText(cause)); }
    finally { setPending(false); }
  };
  return <main className="min-h-screen bg-gray-50 p-4">
    <div className="max-w-xl mx-auto space-y-6">
      <button onClick={() => router.push('/family')} className="text-blue-700">← 家庭健康</button>
      <h1 className="text-xl font-bold">邀请家人或加入家庭</h1>
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {loadError && <button onClick={() => void reload()}>重试加载家庭</button>}
      {success && <p role="status" className="text-green-700">{success}</p>}
      {!dashboard && !loadError && <p>正在读取家庭信息…</p>}
      {dashboard && (!dashboard.group_name || dashboard.is_owner) && <section className="bg-white rounded-xl p-4 space-y-3 border">
        <h2 className="font-semibold">邀请已有账号的家人</h2>
        {!dashboard.group_name && <label className="block">家庭名称<input className="block w-full border rounded p-2" value={groupName} onChange={event => setGroupName(event.target.value)} maxLength={100} /></label>}
        <p className="text-sm text-gray-600">生成邀请码后，让家人在自己的账号打开此页确认加入。已有检查报告仍保留在原账号中。</p>
        <button disabled={pending || (!dashboard.group_name && !groupName.trim())} onClick={() => void create()} className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50">{dashboard.group_name ? '生成邀请码' : '创建家庭并生成邀请码'}</button>
        {invitation && <div className="space-y-2"><p>家庭：{invitation.group_name}</p><p className="text-2xl font-mono tracking-widest">{invitation.code}</p><p className="text-sm">有效期 {Math.floor(invitation.expires_in_seconds / 60)} 分钟。请仅向要邀请的家人提供。</p></div>}
      </section>}
      <form className="bg-white rounded-xl p-4 space-y-4 border" onSubmit={event => { event.preventDefault(); void accept(); }}>
        <h2 className="font-semibold">使用当前账号加入家庭</h2>
        <label className="block">邀请码<input className="block w-full border rounded p-2" value={code} onChange={event => setCode(event.target.value)} maxLength={12} autoComplete="off" /></label>
        <label className="block">我是家庭创建者的<select className="block w-full border rounded p-2" value={relationship} onChange={event => setRelationship(event.target.value)}>{Object.entries(RELATIONSHIPS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
        <label className="block">家庭昵称<input className="block w-full border rounded p-2" value={nickname} onChange={event => setNickname(event.target.value)} maxLength={50} /></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={consented} onChange={event => setConsented(event.target.checked)} />我同意让家庭创建者查看我的健康概况、检查报告和病程记录。仅供查看，不允许修改我的记录或用药。</label>
        <p className="text-sm text-gray-600">请使用本人账号加入；未成年人的账号由监护人协助确认。可在家庭健康页的“我的家庭关联”退出家庭，停止共享。</p>
        <button disabled={pending || !consented || !/^[A-Z0-9]{6}$/.test(code.trim().toUpperCase())} className="bg-blue-600 text-white rounded px-4 py-2 disabled:opacity-50">{pending ? '处理中…' : '同意并加入'}</button>
      </form>
    </div>
  </main>;
}
