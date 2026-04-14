'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api/family';

interface FamilyMember {
  id: number;
  user_id: number;
  name: string;
  nickname: string;
  relationship_type: string;
  is_managed: boolean;
}

const RELATIONSHIP_ICONS: Record<string, string> = {
  self: '👤', father: '👨', mother: '👩', spouse: '💑', child: '👧', sibling: '👫', other: '👥',
};
const RELATIONSHIP_LABELS: Record<string, string> = {
  self: '本人', father: '爸爸', mother: '妈妈', spouse: '配偶', child: '子女', sibling: '兄弟姐妹', other: '其他',
};

export default function InvitePage() {
  return <ProtectedRoute><InviteContent /></ProtectedRoute>;
}

function InviteContent() {
  const router = useRouter();
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedMember, setSelectedMember] = useState<FamilyMember | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    loadMembers();
  }, []);

  const loadMembers = async () => {
    setLoading(true);
    try {
      const res = await familyApi.getMembers();
      // 只显示代管成员（父母等不能自己登录的）
      setMembers((res.data.members || []).filter((m: FamilyMember) => m.is_managed));
    } catch { } finally { setLoading(false); }
  };

  const generateInviteInfo = (member: FamilyMember) => {
    setSelectedMember(member);
    setCopied(false);
  };

  const copyInviteText = () => {
    if (!selectedMember) return;
    const text = `${selectedMember.nickname || selectedMember.name}，我帮你建了一个健康档案。\n\n以后你有体检报告、药盒照片、或者想记录血压血糖，直接在微信上发给健康管家就行，AI 会自动帮你整理归档。\n\n你不需要下载任何App，就在微信里操作。我这边能看到你的健康数据，帮你盯着复查时间和用药。\n\n（这是你的专属健康档案ID: ${selectedMember.user_id}）`;
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-4 py-3 flex items-center gap-3">
        <button onClick={() => router.push('/family')} className="text-gray-500">←</button>
        <h1 className="font-bold text-lg">📨 邀请家人</h1>
      </div>

      <div className="p-4 space-y-4">
        <div className="bg-blue-50 rounded-xl p-4 text-sm text-blue-800">
          <p className="font-medium mb-1">如何让父母使用健康管家？</p>
          <ol className="list-decimal list-inside space-y-1 text-xs">
            <li>选择一个家庭成员</li>
            <li>复制邀请文案发给他们</li>
            <li>等微信 Bot 上线后，他们直接在微信里发消息就行</li>
            <li>目前阶段：你可以在「Bot测试」页面模拟他们的操作</li>
          </ol>
        </div>

        {loading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : members.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-4xl mb-2">👨‍👩‍👧‍👦</div>
            <p>暂无代管的家庭成员</p>
            <p className="text-xs mt-1">请先在家庭管理中添加成员</p>
            <button onClick={() => router.push('/family')} className="mt-4 bg-blue-500 text-white px-4 py-2 rounded-lg text-sm">
              去添加
            </button>
          </div>
        ) : (
          <>
            <h2 className="text-sm font-medium text-gray-500">选择要邀请的家人</h2>
            {members.map(m => (
              <button
                key={m.id}
                onClick={() => generateInviteInfo(m)}
                className={`w-full bg-white rounded-xl p-4 shadow-sm border text-left flex items-center gap-3 transition ${
                  selectedMember?.id === m.id ? 'border-blue-400 bg-blue-50' : 'hover:border-gray-300'
                }`}
              >
                <span className="text-3xl">{RELATIONSHIP_ICONS[m.relationship_type] || '👤'}</span>
                <div>
                  <h3 className="font-medium">{m.nickname || m.name}</h3>
                  <p className="text-xs text-gray-400">{RELATIONSHIP_LABELS[m.relationship_type]} · 档案ID: {m.user_id}</p>
                </div>
              </button>
            ))}
          </>
        )}

        {/* 邀请详情 */}
        {selectedMember && (
          <div className="bg-white rounded-xl p-4 shadow-sm border space-y-3">
            <h3 className="font-medium">
              {RELATIONSHIP_ICONS[selectedMember.relationship_type]} {selectedMember.nickname || selectedMember.name} 的邀请信息
            </h3>

            {/* 邀请文案 */}
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-700 whitespace-pre-wrap">
              {selectedMember.nickname || selectedMember.name}，我帮你建了一个健康档案。{'\n\n'}
              以后你有体检报告、药盒照片、或者想记录血压血糖，直接在微信上发给健康管家就行，AI 会自动帮你整理归档。{'\n\n'}
              你不需要下载任何App，就在微信里操作。我这边能看到你的健康数据，帮你盯着复查时间和用药。
            </div>

            <button
              onClick={copyInviteText}
              className={`w-full rounded-lg py-2.5 text-sm font-medium transition ${
                copied ? 'bg-green-500 text-white' : 'bg-blue-500 text-white hover:bg-blue-600'
              }`}
            >
              {copied ? '✅ 已复制到剪贴板' : '📋 复制邀请文案（发微信）'}
            </button>

            {/* 当前状态 */}
            <div className="bg-amber-50 rounded-lg p-3 text-xs text-amber-700">
              <p className="font-medium">⏳ 微信 Bot 开发中</p>
              <p className="mt-1">企业微信审批通过后，将生成专属二维码。父母扫码添加 Bot 好友即可使用。</p>
              <p className="mt-1">现在可以用「🤖 Bot测试」页面模拟操作验证功能。</p>
            </div>

            <button
              onClick={() => router.push('/family/bot-test')}
              className="w-full border border-amber-300 text-amber-700 rounded-lg py-2 text-sm"
            >
              🤖 去 Bot 测试页面模拟操作
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
