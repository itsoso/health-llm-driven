'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, eachDayOfInterval, parseISO } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const API_BASE = '/api';

const ITEM_TYPES = [
  { value: 'flight', label: '航班', icon: '✈️' },
  { value: 'train', label: '高铁/火车', icon: '🚄' },
  { value: 'bus', label: '大巴', icon: '🚌' },
  { value: 'taxi', label: '出租/网约车', icon: '🚗' },
  { value: 'hotel', label: '住宿', icon: '🏨' },
  { value: 'activity', label: '游览/活动', icon: '🎯' },
  { value: 'other', label: '其他', icon: '📌' },
];

function getItemIcon(type: string) {
  return ITEM_TYPES.find(t => t.value === type)?.icon || '📌';
}

interface TripItem {
  id?: number;
  trip_id?: number;
  user_id?: number;
  item_date: string;
  item_order: number;
  item_type: string;
  title: string;
  origin?: string;
  destination?: string;
  departure_time?: string;
  arrival_time?: string;
  transport_number?: string;
  carrier?: string;
  departure_terminal?: string;
  arrival_terminal?: string;
  location?: string;
  description?: string;
}

interface Trip {
  id: number;
  user_id: number;
  trip_name: string;
  start_date: string;
  end_date: string;
  destination?: string;
  notes?: string;
  items?: TripItem[];
  created_at?: string;
  updated_at?: string;
}

// =====================================================
// 空行程明细模板
// =====================================================
function emptyItem(itemDate: string, order: number): TripItem {
  return {
    item_date: itemDate,
    item_order: order,
    item_type: 'activity',
    title: '',
  };
}

// =====================================================
// 行程明细编辑组件
// =====================================================
function TripItemForm({
  item,
  onChange,
  onRemove,
}: {
  item: TripItem;
  onChange: (updated: TripItem) => void;
  onRemove: () => void;
}) {
  const isTransport = ['flight', 'train', 'bus', 'taxi'].includes(item.item_type);

  return (
    <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 space-y-3">
      <div className="flex items-center gap-2">
        <select
          value={item.item_type}
          onChange={e => onChange({ ...item, item_type: e.target.value })}
          className="p-2 border border-gray-300 rounded-lg text-sm"
        >
          {ITEM_TYPES.map(t => (
            <option key={t.value} value={t.value}>
              {t.icon} {t.label}
            </option>
          ))}
        </select>
        <input
          value={item.title}
          onChange={e => onChange({ ...item, title: e.target.value })}
          placeholder="标题，如：杭州飞成都"
          className="flex-1 p-2 border border-gray-300 rounded-lg text-sm"
        />
        <button onClick={onRemove} className="text-red-400 hover:text-red-600 text-sm px-2">
          删除
        </button>
      </div>

      {isTransport && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input
              value={item.carrier || ''}
              onChange={e => onChange({ ...item, carrier: e.target.value })}
              placeholder="承运方（国航）"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.transport_number || ''}
              onChange={e => onChange({ ...item, transport_number: e.target.value })}
              placeholder="航班号/车次"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.departure_time || ''}
              onChange={e => onChange({ ...item, departure_time: e.target.value })}
              placeholder="出发时间 09:30"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.arrival_time || ''}
              onChange={e => onChange({ ...item, arrival_time: e.target.value })}
              placeholder="到达时间 12:40"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input
              value={item.origin || ''}
              onChange={e => onChange({ ...item, origin: e.target.value })}
              placeholder="出发地"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.departure_terminal || ''}
              onChange={e => onChange({ ...item, departure_terminal: e.target.value })}
              placeholder="出发航站楼 T4"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.destination || ''}
              onChange={e => onChange({ ...item, destination: e.target.value })}
              placeholder="目的地"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              value={item.arrival_terminal || ''}
              onChange={e => onChange({ ...item, arrival_terminal: e.target.value })}
              placeholder="到达航站楼 T2"
              className="p-2 border border-gray-300 rounded-lg text-sm"
            />
          </div>
        </>
      )}

      {!isTransport && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <input
            value={item.location || ''}
            onChange={e => onChange({ ...item, location: e.target.value })}
            placeholder="地点"
            className="p-2 border border-gray-300 rounded-lg text-sm"
          />
          <input
            value={item.description || ''}
            onChange={e => onChange({ ...item, description: e.target.value })}
            placeholder="描述/备注"
            className="p-2 border border-gray-300 rounded-lg text-sm"
          />
        </div>
      )}
    </div>
  );
}

// =====================================================
// 主页面内容
// =====================================================
function TripContent() {
  const { token } = useAuth();
  const queryClient = useQueryClient();

  const [view, setView] = useState<'list' | 'create' | 'detail' | 'edit'>('list');
  const [selectedTripId, setSelectedTripId] = useState<number | null>(null);

  // 创建/编辑表单状态
  const [formName, setFormName] = useState('');
  const [formDestination, setFormDestination] = useState('');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [formItems, setFormItems] = useState<TripItem[]>([]);

  const headers = { Authorization: `Bearer ${token}` };

  // 查询行程列表
  const { data: trips = [], isLoading } = useQuery<Trip[]>({
    queryKey: ['trips'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/trip/trips?days=3650`, { headers });
      if (!res.ok) throw new Error('获取行程失败');
      return res.json();
    },
    enabled: !!token,
  });

  // 查询行程详情
  const { data: tripDetail } = useQuery<Trip>({
    queryKey: ['trip-detail', selectedTripId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/trip/trips/${selectedTripId}`, { headers });
      if (!res.ok) throw new Error('获取行程详情失败');
      return res.json();
    },
    enabled: !!token && !!selectedTripId,
  });

  // 创建行程
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/trip/trips`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || '创建失败');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] });
      resetForm();
      setView('list');
    },
  });

  // 更新行程
  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: any }) => {
      const res = await fetch(`${API_BASE}/trip/trips/${id}`, {
        method: 'PUT',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('更新失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] });
      queryClient.invalidateQueries({ queryKey: ['trip-detail'] });
    },
  });

  // 删除行程
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await fetch(`${API_BASE}/trip/trips/${id}`, {
        method: 'DELETE',
        headers,
      });
      if (!res.ok) throw new Error('删除失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trips'] });
      setView('list');
      setSelectedTripId(null);
    },
  });

  // 添加明细
  const addItemMutation = useMutation({
    mutationFn: async ({ tripId, data }: { tripId: number; data: any }) => {
      const res = await fetch(`${API_BASE}/trip/trips/${tripId}/items`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('添加失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trip-detail'] });
    },
  });

  // 删除明细
  const deleteItemMutation = useMutation({
    mutationFn: async (itemId: number) => {
      const res = await fetch(`${API_BASE}/trip/items/${itemId}`, {
        method: 'DELETE',
        headers,
      });
      if (!res.ok) throw new Error('删除失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['trip-detail'] });
    },
  });

  function resetForm() {
    setFormName('');
    setFormDestination('');
    setFormStartDate('');
    setFormEndDate('');
    setFormNotes('');
    setFormItems([]);
  }

  function handleCreateSubmit() {
    if (!formName.trim() || !formStartDate || !formEndDate) {
      alert('请填写行程名称和起止日期');
      return;
    }
    const validItems = formItems.filter(i => i.title.trim());
    createMutation.mutate({
      trip_name: formName,
      start_date: formStartDate,
      end_date: formEndDate,
      destination: formDestination || undefined,
      notes: formNotes || undefined,
      items: validItems.length > 0 ? validItems : undefined,
    });
  }

  function handleEditSubmit() {
    if (!selectedTripId || !formName.trim() || !formStartDate || !formEndDate) return;
    updateMutation.mutate({
      id: selectedTripId,
      data: {
        trip_name: formName,
        start_date: formStartDate,
        end_date: formEndDate,
        destination: formDestination || undefined,
        notes: formNotes || undefined,
      },
    });
    // 处理明细：添加新的，保持已有的
    const newItems = formItems.filter(i => !i.id && i.title.trim());
    for (const item of newItems) {
      addItemMutation.mutate({ tripId: selectedTripId, data: item });
    }
    setView('detail');
  }

  function openDetail(tripId: number) {
    setSelectedTripId(tripId);
    setView('detail');
  }

  function openEdit(trip: Trip) {
    setSelectedTripId(trip.id);
    setFormName(trip.trip_name);
    setFormDestination(trip.destination || '');
    setFormStartDate(trip.start_date);
    setFormEndDate(trip.end_date);
    setFormNotes(trip.notes || '');
    setFormItems(trip.items || []);
    setView('edit');
  }

  function addItemToDay(dateStr: string) {
    const order = formItems.filter(i => i.item_date === dateStr).length;
    setFormItems([...formItems, emptyItem(dateStr, order)]);
  }

  function updateFormItem(index: number, updated: TripItem) {
    const newItems = [...formItems];
    newItems[index] = updated;
    setFormItems(newItems);
  }

  function removeFormItem(index: number) {
    setFormItems(formItems.filter((_, i) => i !== index));
  }

  // 按日期分组明细
  function groupItemsByDate(items: TripItem[]) {
    const groups: Record<string, TripItem[]> = {};
    for (const item of items) {
      const d = item.item_date;
      if (!groups[d]) groups[d] = [];
      groups[d].push(item);
    }
    return groups;
  }

  // 生成日期范围
  function getDateRange() {
    if (!formStartDate || !formEndDate) return [];
    try {
      return eachDayOfInterval({
        start: parseISO(formStartDate),
        end: parseISO(formEndDate),
      }).map(d => format(d, 'yyyy-MM-dd'));
    } catch {
      return [];
    }
  }

  // =====================================================
  // 列表视图
  // =====================================================
  if (view === 'list') {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-800">行程记录</h1>
          <button
            onClick={() => { resetForm(); setView('create'); }}
            className="px-4 py-2 bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-lg hover:from-blue-600 hover:to-indigo-600 text-sm font-medium"
          >
            + 新建行程
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-10 text-gray-500">加载中...</div>
        ) : trips.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            <p className="text-5xl mb-4">✈️</p>
            <p className="text-lg">还没有行程记录</p>
            <p className="text-sm mt-2">点击"新建行程"开始记录你的旅行</p>
          </div>
        ) : (
          <div className="space-y-4">
            {trips.map(trip => {
              const start = parseISO(trip.start_date);
              const end = parseISO(trip.end_date);
              const days = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
              const today = new Date();
              const isOngoing = start <= today && end >= today;
              const isUpcoming = start > today;

              return (
                <div
                  key={trip.id}
                  onClick={() => openDetail(trip.id)}
                  className="bg-white rounded-xl shadow-md p-5 cursor-pointer hover:shadow-lg transition-all border border-gray-100"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-lg font-bold text-gray-800">{trip.trip_name}</h3>
                        {isOngoing && (
                          <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full font-medium">
                            进行中
                          </span>
                        )}
                        {isUpcoming && (
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                            即将出发
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-500">
                        {format(start, 'M月d日', { locale: zhCN })} - {format(end, 'M月d日', { locale: zhCN })}
                        <span className="ml-2 text-gray-400">共{days}天</span>
                      </p>
                      {trip.destination && (
                        <p className="text-sm text-gray-600 mt-1">
                          📍 {trip.destination}
                        </p>
                      )}
                    </div>
                    <span className="text-gray-400 text-xl">›</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  // =====================================================
  // 详情视图
  // =====================================================
  if (view === 'detail' && tripDetail) {
    const grouped = groupItemsByDate(tripDetail.items || []);
    const dates = Object.keys(grouped).sort();

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <button onClick={() => setView('list')} className="text-gray-500 hover:text-gray-700">
            ← 返回
          </button>
          <h1 className="text-2xl font-bold text-gray-800 flex-1">{tripDetail.trip_name}</h1>
          <button
            onClick={() => openEdit(tripDetail)}
            className="px-3 py-1.5 text-sm text-blue-600 border border-blue-300 rounded-lg hover:bg-blue-50"
          >
            编辑
          </button>
          <button
            onClick={() => {
              if (confirm('确定删除此行程？')) deleteMutation.mutate(tripDetail.id);
            }}
            className="px-3 py-1.5 text-sm text-red-600 border border-red-300 rounded-lg hover:bg-red-50"
          >
            删除
          </button>
        </div>

        <div className="bg-white rounded-xl shadow-md p-5 border border-gray-100">
          <div className="flex flex-wrap gap-4 text-sm text-gray-600">
            <span>
              📅 {format(parseISO(tripDetail.start_date), 'yyyy年M月d日', { locale: zhCN })} -{' '}
              {format(parseISO(tripDetail.end_date), 'M月d日', { locale: zhCN })}
            </span>
            {tripDetail.destination && <span>📍 {tripDetail.destination}</span>}
          </div>
          {tripDetail.notes && <p className="text-sm text-gray-500 mt-2">{tripDetail.notes}</p>}
        </div>

        {/* 时间线 */}
        {dates.length > 0 ? (
          <div className="space-y-4">
            {dates.map(dateStr => {
              const items = grouped[dateStr];
              const d = parseISO(dateStr);
              return (
                <div key={dateStr} className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
                  <h3 className="text-base font-bold text-gray-700 mb-3 flex items-center gap-2">
                    <span className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-sm font-bold">
                      {format(d, 'd')}
                    </span>
                    {format(d, 'M月d日 EEEE', { locale: zhCN })}
                  </h3>
                  <div className="space-y-2 ml-10">
                    {items.map((item, idx) => (
                      <div key={item.id || idx} className="flex items-start gap-2">
                        <span className="text-lg">{getItemIcon(item.item_type)}</span>
                        <div className="flex-1">
                          <p className="text-sm font-medium text-gray-800">
                            {item.title}
                            {item.transport_number && (
                              <span className="ml-1 text-gray-500">
                                ({item.carrier || ''}{item.transport_number})
                              </span>
                            )}
                          </p>
                          {['flight', 'train', 'bus', 'taxi'].includes(item.item_type) && (
                            <p className="text-xs text-gray-500 mt-0.5">
                              {item.origin}
                              {item.departure_terminal && `(${item.departure_terminal})`}
                              {item.departure_time && ` ${item.departure_time}`}
                              {' → '}
                              {item.destination}
                              {item.arrival_terminal && `(${item.arrival_terminal})`}
                              {item.arrival_time && ` ${item.arrival_time}`}
                            </p>
                          )}
                          {item.location && (
                            <p className="text-xs text-gray-500 mt-0.5">📍 {item.location}</p>
                          )}
                          {item.description && (
                            <p className="text-xs text-gray-400 mt-0.5">{item.description}</p>
                          )}
                        </div>
                        {item.id && (
                          <button
                            onClick={() => {
                              if (confirm('删除此项？')) deleteItemMutation.mutate(item.id!);
                            }}
                            className="text-gray-300 hover:text-red-500 text-xs"
                          >
                            删除
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            <p>暂无行程明细</p>
            <button
              onClick={() => openEdit(tripDetail)}
              className="mt-2 text-blue-500 hover:text-blue-700 text-sm"
            >
              添加明细
            </button>
          </div>
        )}
      </div>
    );
  }

  // =====================================================
  // 创建/编辑表单
  // =====================================================
  const isEdit = view === 'edit';
  const dateRange = getDateRange();

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => { setView(isEdit ? 'detail' : 'list'); }}
          className="text-gray-500 hover:text-gray-700"
        >
          ← 返回
        </button>
        <h1 className="text-2xl font-bold text-gray-800">
          {isEdit ? '编辑行程' : '新建行程'}
        </h1>
      </div>

      {/* 基本信息 */}
      <div className="bg-white rounded-xl shadow-md p-5 border border-gray-100 space-y-4">
        <h2 className="font-bold text-gray-700">基本信息</h2>
        <input
          value={formName}
          onChange={e => setFormName(e.target.value)}
          placeholder="行程名称，如：成都之旅"
          className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <input
          value={formDestination}
          onChange={e => setFormDestination(e.target.value)}
          placeholder="主要目的地，如：成都"
          className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-600 mb-1">开始日期</label>
            <input
              type="date"
              value={formStartDate}
              onChange={e => setFormStartDate(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">结束日期</label>
            <input
              type="date"
              value={formEndDate}
              onChange={e => setFormEndDate(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
        <textarea
          value={formNotes}
          onChange={e => setFormNotes(e.target.value)}
          placeholder="备注（可选）"
          rows={2}
          className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>

      {/* 每日明细 */}
      {dateRange.length > 0 && (
        <div className="space-y-4">
          <h2 className="font-bold text-gray-700">每日行程明细</h2>
          {dateRange.map(dateStr => {
            const dayItems = formItems
              .map((item, idx) => ({ item, idx }))
              .filter(({ item }) => item.item_date === dateStr);

            return (
              <div key={dateStr} className="bg-white rounded-xl shadow-sm p-5 border border-gray-100">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-medium text-gray-700">
                    {format(parseISO(dateStr), 'M月d日 EEEE', { locale: zhCN })}
                  </h3>
                  <button
                    onClick={() => addItemToDay(dateStr)}
                    className="text-sm text-blue-500 hover:text-blue-700"
                  >
                    + 添加项目
                  </button>
                </div>
                {dayItems.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-2">
                    点击"添加项目"记录当天行程
                  </p>
                ) : (
                  <div className="space-y-3">
                    {dayItems.map(({ item, idx }) => (
                      <TripItemForm
                        key={idx}
                        item={item}
                        onChange={updated => updateFormItem(idx, updated)}
                        onRemove={() => removeFormItem(idx)}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 提交按钮 */}
      <button
        onClick={isEdit ? handleEditSubmit : handleCreateSubmit}
        disabled={createMutation.isPending || updateMutation.isPending}
        className="w-full py-3 bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-lg hover:from-blue-600 hover:to-indigo-600 font-medium disabled:opacity-50"
      >
        {(createMutation.isPending || updateMutation.isPending) ? '保存中...' : '保存行程'}
      </button>
      {createMutation.isError && (
        <p className="text-sm text-red-500 text-center">{(createMutation.error as Error).message}</p>
      )}
    </div>
  );
}

export default function TripPage() {
  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <TripContent />
        </div>
      </main>
    </ProtectedRoute>
  );
}
