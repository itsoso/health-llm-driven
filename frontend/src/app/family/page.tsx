'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api/family';

// ── Types ────────────────────────────────────────────────
interface FamilyMember {
  id: number;
  user_id: number;
  name: string;
  nickname: string;
  relationship_type: string;
  role: string;
  is_managed: boolean;
  gender: string | null;
  birth_date: string | null;
  can_view: boolean;
  can_edit: boolean;
}

interface DashboardMember {
  user_id: number;
  name: string;
  nickname: string;
  relationship_type: string;
  is_managed: boolean;
  latest_weight: number | null;
  today_steps: number | null;
  sleep_score: number | null;
  resting_hr: number | null;
  today_water_ml: number;
  unread_alerts: number;
}

interface DailyCheckReport {
  admin_summary: string;
  admin_alert_count: number;
  member_reports: {
    user_id: number;
    name: string;
    relationship: string;
    alerts: string[];
    todos: string[];
  }[];
  check_date: string;
}

// ── Constants ────────────────────────────────────────────
const RELATIONSHIP_LABELS: Record<string, string> = {
  self: '本人', father: '爸爸', mother: '妈妈',
  spouse: '配偶', child: '子女', sibling: '兄弟姐妹', other: '其他',
};

const RELATIONSHIP_ICONS: Record<string, string> = {
  self: '👤', father: '👨', mother: '👩',
  spouse: '💑', child: '👧', sibling: '👫', other: '👥',
};

// ── Tabs ─────────────────────────────────────────────────
type TabKey = 'dashboard' | 'members' | 'daily-check';

export default function FamilyPage() {
  return (
    <ProtectedRoute>
      <FamilyContent />
    </ProtectedRoute>
  );
}

function FamilyContent() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const [hasGroup, setHasGroup] = useState<boolean | null>(null);
  const [groupName, setGroupName] = useState('');
  const [newGroupName, setNewGroupName] = useState('');

  // 成员
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [dashboard, setDashboard] = useState<DashboardMember[]>([]);
  const [dailyCheck, setDailyCheck] = useState<DailyCheckReport | null>(null);

  // 添加成员表单
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({ name: '', relationship_type: 'father', gender: '男', birth_date: '' });

  // 代管模式
  const [proxyMode, setProxyMode] = useState(false);
  const [proxyName, setProxyName] = useState('');

  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  // ── Init ──────────────────────────────────────────────
  useEffect(() => {
    loadData();
    familyApi.getProxyStatus().then((response) => {
      setProxyMode(Boolean(response.data.is_proxy_mode));
      setProxyName(response.data.acting_as_name || '家庭成员');
    }).catch(() => {});
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const groupRes = await familyApi.getGroups();
      const groups = groupRes.data.groups || [];
      if (groups.length > 0) {
        setHasGroup(true);
        setGroupName(groups[0].name);
        const [dashRes, memberRes] = await Promise.all([
          familyApi.getDashboard(),
          familyApi.getMembers(),
        ]);
        setDashboard(dashRes.data.members || []);
        setMembers(memberRes.data.members || []);
      } else {
        setHasGroup(false);
      }
    } catch {
      setHasGroup(false);
    } finally {
      setLoading(false);
    }
  };

  // ── 创建家庭组 ─────────────────────────────────────────
  const createGroup = async () => {
    if (!newGroupName.trim()) return;
    try {
      await familyApi.createGroup(newGroupName.trim());
      await loadData();
    } catch (e: any) {
      alert(e.response?.data?.detail || '创建失败');
    }
  };

  // ── 添加成员 ──────────────────────────────────────────
  const addMember = async () => {
    if (!addForm.name.trim()) return;
    try {
      await familyApi.addMember({
        name: addForm.name,
        relationship_type: addForm.relationship_type,
        nickname: RELATIONSHIP_LABELS[addForm.relationship_type] || addForm.name,
        gender: addForm.gender,
        birth_date: addForm.birth_date || undefined,
      });
      setShowAddForm(false);
      setAddForm({ name: '', relationship_type: 'father', gender: '男', birth_date: '' });
      await loadData();
    } catch (e: any) {
      alert(e.response?.data?.detail || '添加失败');
    }
  };

  // ── 切换视角 ──────────────────────────────────────────
  const switchToMember = async (userId: number, name: string) => {
    try {
      const res = await familyApi.switchToMember(userId);
      const { acting_as_name } = res.data;
      setProxyMode(true);
      setProxyName(acting_as_name || name);
      // 刷新页面以使用新 token
      window.location.href = '/';
    } catch (e: any) {
      alert(e.response?.data?.detail || '切换失败');
    }
  };

  // ── 切回自己 ──────────────────────────────────────────
  const switchBack = async () => {
    try {
      await familyApi.switchBack();
      setProxyMode(false);
      window.location.href = '/family';
    } catch (e: any) {
      alert(e.response?.data?.detail || '切回失败');
    }
  };

  // ── 每日巡检 ──────────────────────────────────────────
  const runDailyCheck = async () => {
    try {
      const res = await familyApi.getDailyCheck();
      setDailyCheck(res.data);
    } catch (e: any) {
      alert('巡检失败: ' + (e.response?.data?.detail || e.message));
    }
  };

  const sendDailyBrief = async () => {
    setSending(true);
    try {
      await familyApi.sendDailyCheck();
      alert('健康日报已发送');
    } catch (e: any) {
      alert('发送失败: ' + (e.response?.data?.detail || e.message));
    } finally {
      setSending(false);
    }
  };

  // ── Render ────────────────────────────────────────────
  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" /></div>;
  }

  // 代管模式 banner
  const proxyBanner = proxyMode ? (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between">
      <span className="text-amber-800 text-sm">👥 当前代管: <strong>{proxyName}</strong>（所有操作以 TA 的身份执行）</span>
      <button onClick={switchBack} className="text-amber-700 text-sm underline">切回自己</button>
    </div>
  ) : null;

  // 没有家庭组 → 创建
  if (hasGroup === false) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        {proxyBanner}
        <div className="max-w-md mx-auto mt-20 bg-white rounded-2xl shadow-lg p-8 text-center">
          <div className="text-5xl mb-4">👨‍👩‍👧‍👦</div>
          <h2 className="text-xl font-bold mb-2">创建家庭组</h2>
          <p className="text-gray-500 text-sm mb-6">为家人建立健康档案，统一管理体检、用药、复查</p>
          <input
            className="w-full border rounded-lg px-4 py-2 mb-4 text-center"
            placeholder="家庭组名称（如：李家）"
            value={newGroupName}
            onChange={e => setNewGroupName(e.target.value)}
            onKeyDown={e => {
              if (e.nativeEvent.isComposing || e.keyCode === 229) return;
              if (e.key === 'Enter') createGroup();
            }}
          />
          <button onClick={createGroup} className="w-full bg-blue-500 text-white rounded-lg py-2 font-medium hover:bg-blue-600">创建</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {proxyBanner}

      {/* 头部 */}
      <div className="bg-white border-b px-4 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold">{groupName}</h1>
            <p className="text-gray-500 text-xs">{members.length} 位家庭成员</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button onClick={() => router.push('/family/medications')} className="text-xs bg-green-50 text-green-700 px-3 py-1.5 rounded-lg">💊 用药</button>
            <button onClick={() => router.push('/family/reports')} className="text-xs bg-blue-50 text-blue-700 px-3 py-1.5 rounded-lg">📋 体检</button>
            <button onClick={() => router.push('/family/calendar')} className="text-xs bg-purple-50 text-purple-700 px-3 py-1.5 rounded-lg">📅 复查</button>
            <button onClick={() => router.push('/family/bot-test')} className="text-xs bg-amber-50 text-amber-700 px-3 py-1.5 rounded-lg">🤖 Bot测试</button>
            <button onClick={() => router.push('/family/invite')} className="text-xs bg-orange-50 text-orange-700 px-3 py-1.5 rounded-lg">📨 邀请</button>
          </div>
        </div>
      </div>

      {/* Tab */}
      <div className="flex bg-white border-b">
        {[
          { key: 'dashboard' as TabKey, label: '健康概览' },
          { key: 'members' as TabKey, label: '成员管理' },
          { key: 'daily-check' as TabKey, label: '健康巡检' },
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => { setActiveTab(tab.key); if (tab.key === 'daily-check' && !dailyCheck) runDailyCheck(); }}
            className={`flex-1 py-3 text-sm font-medium border-b-2 transition ${activeTab === tab.key ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {activeTab === 'dashboard' && <DashboardTab dashboard={dashboard} onSwitch={switchToMember} proxyMode={proxyMode} />}
        {activeTab === 'members' && <MembersTab members={members} showAddForm={showAddForm} setShowAddForm={setShowAddForm} addForm={addForm} setAddForm={setAddForm} onAdd={addMember} onReload={loadData} />}
        {activeTab === 'daily-check' && <DailyCheckTab report={dailyCheck} onRun={runDailyCheck} onSend={sendDailyBrief} sending={sending} />}
      </div>
    </div>
  );
}

// ── Dashboard Tab ────────────────────────────────────────
function DashboardTab({ dashboard, onSwitch, proxyMode }: { dashboard: DashboardMember[]; onSwitch: (id: number, name: string) => void; proxyMode: boolean }) {
  return (
    <div className="space-y-3">
      {dashboard.map(m => (
        <div key={m.user_id} className="bg-white rounded-xl p-4 shadow-sm border">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">{RELATIONSHIP_ICONS[m.relationship_type] || '👤'}</span>
              <div>
                <h3 className="font-bold">{m.nickname || m.name}</h3>
                <span className="text-xs text-gray-400">{RELATIONSHIP_LABELS[m.relationship_type]}</span>
              </div>
            </div>
            {m.is_managed && !proxyMode && (
              <button
                onClick={() => onSwitch(m.user_id, m.nickname || m.name)}
                className="text-xs bg-blue-50 text-blue-600 px-3 py-1 rounded-full"
              >
                切换视角
              </button>
            )}
          </div>

          <div className="grid grid-cols-3 gap-2 text-center text-xs">
            <div className="bg-gray-50 rounded-lg p-2">
              <div className="text-gray-400">步数</div>
              <div className="font-bold text-base">{m.today_steps?.toLocaleString() ?? '--'}</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2">
              <div className="text-gray-400">睡眠</div>
              <div className="font-bold text-base">{m.sleep_score ?? '--'}<span className="text-xs text-gray-400">分</span></div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2">
              <div className="text-gray-400">心率</div>
              <div className="font-bold text-base">{m.resting_hr ?? '--'}<span className="text-xs text-gray-400">bpm</span></div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2">
              <div className="text-gray-400">体重</div>
              <div className="font-bold text-base">{m.latest_weight ? `${m.latest_weight}kg` : '--'}</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2">
              <div className="text-gray-400">饮水</div>
              <div className="font-bold text-base">{m.today_water_ml}<span className="text-xs text-gray-400">ml</span></div>
            </div>
            <div className={`rounded-lg p-2 ${m.unread_alerts > 0 ? 'bg-red-50' : 'bg-gray-50'}`}>
              <div className="text-gray-400">预警</div>
              <div className={`font-bold text-base ${m.unread_alerts > 0 ? 'text-red-600' : ''}`}>{m.unread_alerts}</div>
            </div>
          </div>
        </div>
      ))}
      {dashboard.length === 0 && (
        <div className="text-center text-gray-400 py-12">暂无家庭成员数据，请先添加成员</div>
      )}
    </div>
  );
}

// ── Members Tab ──────────────────────────────────────────
function MembersTab({ members, showAddForm, setShowAddForm, addForm, setAddForm, onAdd, onReload }: any) {
  const removeMember = async (id: number, name: string) => {
    if (!confirm(`确定移除 ${name}？`)) return;
    try {
      await familyApi.removeMember(id);
      onReload();
    } catch (e: any) {
      alert(e.response?.data?.detail || '移除失败');
    }
  };

  return (
    <div className="space-y-3">
      {members.map((m: FamilyMember) => (
        <div key={m.id} className="bg-white rounded-xl p-4 shadow-sm border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{RELATIONSHIP_ICONS[m.relationship_type] || '👤'}</span>
            <div>
              <h3 className="font-medium">{m.name}</h3>
              <div className="text-xs text-gray-400">
                {RELATIONSHIP_LABELS[m.relationship_type]}
                {m.is_managed && ' · 代管'}
                {m.gender && ` · ${m.gender}`}
                {m.birth_date && ` · ${m.birth_date}`}
              </div>
            </div>
          </div>
          {m.role !== 'owner' && (
            <button onClick={() => removeMember(m.id, m.name)} className="text-xs text-red-400 hover:text-red-600">移除</button>
          )}
        </div>
      ))}

      {!showAddForm ? (
        <button onClick={() => setShowAddForm(true)} className="w-full bg-white rounded-xl p-4 shadow-sm border border-dashed border-gray-300 text-gray-400 hover:text-blue-500 hover:border-blue-300 transition">
          + 添加家庭成员
        </button>
      ) : (
        <div className="bg-white rounded-xl p-4 shadow-sm border space-y-3">
          <h3 className="font-medium">添加家庭成员</h3>
          <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="姓名" value={addForm.name} onChange={e => setAddForm({ ...addForm, name: e.target.value })} />
          <div className="flex gap-2">
            <select className="flex-1 border rounded-lg px-3 py-2 text-sm" value={addForm.relationship_type} onChange={e => setAddForm({ ...addForm, relationship_type: e.target.value })}>
              {Object.entries(RELATIONSHIP_LABELS).filter(([k]) => k !== 'self').map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <select className="w-20 border rounded-lg px-3 py-2 text-sm" value={addForm.gender} onChange={e => setAddForm({ ...addForm, gender: e.target.value })}>
              <option value="男">男</option>
              <option value="女">女</option>
            </select>
          </div>
          <input className="w-full border rounded-lg px-3 py-2 text-sm" type="date" placeholder="出生日期" value={addForm.birth_date} onChange={e => setAddForm({ ...addForm, birth_date: e.target.value })} />
          <div className="flex gap-2">
            <button onClick={() => setShowAddForm(false)} className="flex-1 border rounded-lg py-2 text-sm text-gray-500">取消</button>
            <button onClick={onAdd} className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-sm">添加</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Daily Check Tab ──────────────────────────────────────
function DailyCheckTab({ report, onRun, onSend, sending }: { report: DailyCheckReport | null; onRun: () => void; onSend: () => void; sending: boolean }) {
  if (!report) {
    return (
      <div className="text-center py-12">
        <div className="text-4xl mb-4">🏥</div>
        <p className="text-gray-500 mb-4">点击下方按钮执行家庭健康巡检</p>
        <button onClick={onRun} className="bg-blue-500 text-white px-6 py-2 rounded-lg">开始巡检</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 管理员汇总 */}
      <div className={`rounded-xl p-4 ${report.admin_alert_count > 0 ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
        <pre className="whitespace-pre-wrap text-sm">{report.admin_summary}</pre>
      </div>

      {/* 各成员报告 */}
      {report.member_reports.map(mr => (
        <div key={mr.user_id} className="bg-white rounded-xl p-4 shadow-sm border">
          <h3 className="font-medium mb-2">{RELATIONSHIP_ICONS[mr.relationship] || '👤'} {mr.name}</h3>
          {mr.alerts.length > 0 && (
            <div className="mb-2">
              {mr.alerts.map((a, i) => (
                <div key={i} className="text-sm text-red-600 flex items-start gap-1">
                  <span>⚠️</span><span>{a}</span>
                </div>
              ))}
            </div>
          )}
          {mr.todos.length > 0 && (
            <div>
              {mr.todos.map((t, i) => (
                <div key={i} className="text-sm text-gray-600 flex items-start gap-1">
                  <span>📋</span><span>{t}</span>
                </div>
              ))}
            </div>
          )}
          {mr.alerts.length === 0 && mr.todos.length === 0 && (
            <div className="text-sm text-green-600">✅ 状况良好</div>
          )}
        </div>
      ))}

      {/* 操作按钮 */}
      <div className="flex gap-2">
        <button onClick={onRun} className="flex-1 border rounded-lg py-2 text-sm text-gray-500">刷新巡检</button>
        <button onClick={onSend} disabled={sending} className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-sm disabled:opacity-50">
          {sending ? '发送中...' : '📨 发送日报'}
        </button>
      </div>
      <button
        onClick={async () => {
          try {
            const res = await (await import('@/services/api/family')).familyApi.getWeeklyDigest();
            alert(res.data.digest_text || '暂无周报数据');
          } catch { alert('获取周报失败'); }
        }}
        className="w-full border border-blue-200 text-blue-600 rounded-lg py-2 text-sm"
      >
        📊 查看本周健康周报
      </button>
    </div>
  );
}
