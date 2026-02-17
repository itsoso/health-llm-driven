import { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, Input, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, put, del } from '../../services/request';
import './index.scss';

const ITEM_TYPES = [
  { value: 'flight', label: '航班', icon: '✈️' },
  { value: 'train', label: '高铁/火车', icon: '🚄' },
  { value: 'bus', label: '大巴', icon: '🚌' },
  { value: 'taxi', label: '出租车', icon: '🚗' },
  { value: 'hotel', label: '住宿', icon: '🏨' },
  { value: 'activity', label: '游览', icon: '🎯' },
  { value: 'other', label: '其他', icon: '📌' },
];

function getItemIcon(type: string) {
  return ITEM_TYPES.find(t => t.value === type)?.icon || '📌';
}

interface TripItemData {
  id?: number;
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

interface TripData {
  id: number;
  trip_name: string;
  start_date: string;
  end_date: string;
  destination?: string;
  notes?: string;
  items?: TripItemData[];
}

function emptyItem(itemDate: string, order: number): TripItemData {
  return { item_date: itemDate, item_order: order, item_type: 'activity', title: '' };
}

// 生成日期范围
function getDateRange(start: string, end: string): string[] {
  if (!start || !end) return [];
  const dates: string[] = [];
  const s = new Date(start);
  const e = new Date(end);
  if (s > e) return [];
  const d = new Date(s);
  while (d <= e) {
    dates.push(d.toISOString().slice(0, 10));
    d.setDate(d.getDate() + 1);
  }
  return dates;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
  return `${d.getMonth() + 1}月${d.getDate()}日 周${weekdays[d.getDay()]}`;
}

export default function TripPage() {
  const [loading, setLoading] = useState(true);
  const [trips, setTrips] = useState<TripData[]>([]);
  const [view, setView] = useState<'list' | 'create' | 'detail' | 'edit'>('list');
  const [selectedTrip, setSelectedTrip] = useState<TripData | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // 表单状态
  const [formName, setFormName] = useState('');
  const [formDest, setFormDest] = useState('');
  const [formStart, setFormStart] = useState('');
  const [formEnd, setFormEnd] = useState('');
  const [formNotes, setFormNotes] = useState('');
  const [formItems, setFormItems] = useState<TripItemData[]>([]);

  const loadTrips = useCallback(async () => {
    try {
      setLoading(true);
      const data = await get<TripData[]>('/trip/trips?days=3650');
      setTrips(data || []);
    } catch (e) {
      console.error('加载行程失败:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    try {
      const data = await get<TripData>(`/trip/trips/${id}`);
      setSelectedTrip(data);
    } catch (e) {
      console.error('加载详情失败:', e);
    }
  }, []);

  useEffect(() => {
    loadTrips();
  }, [loadTrips]);

  function resetForm() {
    setFormName('');
    setFormDest('');
    setFormStart('');
    setFormEnd('');
    setFormNotes('');
    setFormItems([]);
    setError('');
  }

  function openCreate() {
    resetForm();
    setView('create');
  }

  function openDetail(trip: TripData) {
    setSelectedTrip(null);
    loadDetail(trip.id);
    setView('detail');
  }

  function openEdit() {
    if (!selectedTrip) return;
    setFormName(selectedTrip.trip_name);
    setFormDest(selectedTrip.destination || '');
    setFormStart(selectedTrip.start_date);
    setFormEnd(selectedTrip.end_date);
    setFormNotes(selectedTrip.notes || '');
    setFormItems(selectedTrip.items || []);
    setView('edit');
  }

  async function handleSubmit() {
    if (!formName.trim() || !formStart || !formEnd) {
      Taro.showToast({ title: '请填写名称和日期', icon: 'none' });
      return;
    }
    const validItems = formItems.filter(i => i.title.trim());
    try {
      setSubmitting(true);
      setError('');
      await post('/trip/trips', {
        trip_name: formName,
        start_date: formStart,
        end_date: formEnd,
        destination: formDest || undefined,
        notes: formNotes || undefined,
        items: validItems.length > 0 ? validItems : undefined,
      });
      Taro.showToast({ title: '创建成功', icon: 'success' });
      resetForm();
      setView('list');
      loadTrips();
    } catch (e: any) {
      setError(e?.message || '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdate() {
    if (!selectedTrip || !formName.trim() || !formStart || !formEnd) return;
    try {
      setSubmitting(true);
      await put(`/trip/trips/${selectedTrip.id}`, {
        trip_name: formName,
        start_date: formStart,
        end_date: formEnd,
        destination: formDest || undefined,
        notes: formNotes || undefined,
      });
      // 添加新明细
      const newItems = formItems.filter(i => !i.id && i.title.trim());
      for (const item of newItems) {
        await post(`/trip/trips/${selectedTrip.id}/items`, item);
      }
      Taro.showToast({ title: '更新成功', icon: 'success' });
      loadDetail(selectedTrip.id);
      setView('detail');
      loadTrips();
    } catch (e: any) {
      setError(e?.message || '更新失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!selectedTrip) return;
    Taro.showModal({
      title: '确认删除',
      content: `确定删除"${selectedTrip.trip_name}"？`,
      success: async (res) => {
        if (res.confirm) {
          try {
            await del(`/trip/trips/${selectedTrip.id}`);
            Taro.showToast({ title: '已删除', icon: 'success' });
            setView('list');
            setSelectedTrip(null);
            loadTrips();
          } catch (e) {
            console.error('删除失败:', e);
          }
        }
      },
    });
  }

  async function handleDeleteItem(itemId: number) {
    Taro.showModal({
      title: '确认',
      content: '删除此项？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await del(`/trip/items/${itemId}`);
            Taro.showToast({ title: '已删除', icon: 'success' });
            if (selectedTrip) loadDetail(selectedTrip.id);
          } catch (e) {
            console.error('删除失败:', e);
          }
        }
      },
    });
  }

  function addItemToDay(dateStr: string) {
    const order = formItems.filter(i => i.item_date === dateStr).length;
    setFormItems([...formItems, emptyItem(dateStr, order)]);
  }

  function updateFormItem(index: number, key: string, value: string) {
    const items = [...formItems];
    (items[index] as any)[key] = value;
    setFormItems(items);
  }

  function removeFormItem(index: number) {
    setFormItems(formItems.filter((_, i) => i !== index));
  }

  function groupByDate(items: TripItemData[]) {
    const groups: Record<string, TripItemData[]> = {};
    for (const item of items) {
      if (!groups[item.item_date]) groups[item.item_date] = [];
      groups[item.item_date].push(item);
    }
    return groups;
  }

  // =====================================================
  // 列表视图
  // =====================================================
  if (view === 'list') {
    return (
      <ScrollView className="trip-page" scrollY>
        <View className="header-bar">
          <Text className="header-title">行程记录</Text>
          <Text className="add-btn" onClick={openCreate}>+ 新建</Text>
        </View>

        {loading ? (
          <View className="loading">
            <Text className="loading-text">加载中...</Text>
          </View>
        ) : trips.length === 0 ? (
          <View className="empty-state">
            <Text className="empty-icon">✈️</Text>
            <Text className="empty-text">还没有行程记录</Text>
            <Text className="empty-sub">点击"新建"开始记录旅行</Text>
          </View>
        ) : (
          <View className="trip-list">
            {trips.map(trip => {
              const today = new Date().toISOString().slice(0, 10);
              const isOngoing = trip.start_date <= today && trip.end_date >= today;
              const isUpcoming = trip.start_date > today;
              const s = new Date(trip.start_date);
              const e = new Date(trip.end_date);
              const days = Math.ceil((e.getTime() - s.getTime()) / 86400000) + 1;

              return (
                <View key={trip.id} className="trip-card" onClick={() => openDetail(trip)}>
                  <View className="trip-card-header">
                    <Text className="trip-name">{trip.trip_name}</Text>
                    {isOngoing && <Text className="trip-badge ongoing">进行中</Text>}
                    {isUpcoming && <Text className="trip-badge upcoming">即将出发</Text>}
                    {!isOngoing && !isUpcoming && <Text className="trip-badge past">已结束</Text>}
                  </View>
                  <Text className="trip-date">
                    {formatDate(trip.start_date)} - {formatDate(trip.end_date)} · {days}天
                  </Text>
                  {trip.destination && <Text className="trip-destination">📍 {trip.destination}</Text>}
                  <Text className="trip-arrow">›</Text>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
    );
  }

  // =====================================================
  // 详情视图
  // =====================================================
  if (view === 'detail') {
    const grouped = selectedTrip?.items ? groupByDate(selectedTrip.items) : {};
    const dates = Object.keys(grouped).sort();

    return (
      <ScrollView className="trip-page" scrollY>
        <View className="detail-header">
          <Text className="back-btn" onClick={() => setView('list')}>← 返回</Text>
          <Text className="detail-title">{selectedTrip?.trip_name || '加载中...'}</Text>
          {selectedTrip && (
            <View className="detail-actions">
              <Text className="action-btn edit" onClick={openEdit}>编辑</Text>
              <Text className="action-btn delete" onClick={handleDelete}>删除</Text>
            </View>
          )}
        </View>

        {selectedTrip && (
          <>
            <View className="detail-info">
              <View className="info-row">
                <Text className="info-item">
                  📅 {formatDate(selectedTrip.start_date)} - {formatDate(selectedTrip.end_date)}
                </Text>
                {selectedTrip.destination && (
                  <Text className="info-item">📍 {selectedTrip.destination}</Text>
                )}
              </View>
              {selectedTrip.notes && <Text className="info-notes">{selectedTrip.notes}</Text>}
            </View>

            {dates.length > 0 ? (
              <View className="timeline">
                {dates.map(dateStr => {
                  const items = grouped[dateStr];
                  const d = new Date(dateStr);
                  return (
                    <View key={dateStr} className="day-card">
                      <View className="day-header">
                        <View className="day-badge">
                          <Text className="day-num">{d.getDate()}</Text>
                        </View>
                        <Text className="day-date">{formatDate(dateStr)}</Text>
                      </View>
                      <View className="day-items">
                        {items.map((item, idx) => (
                          <View key={item.id || idx} className="item-row">
                            <Text className="item-icon">{getItemIcon(item.item_type)}</Text>
                            <View className="item-content">
                              <Text className="item-title">
                                {item.title}
                                {item.transport_number && (
                                  <Text className="item-transport">
                                    ({item.carrier || ''}{item.transport_number})
                                  </Text>
                                )}
                              </Text>
                              {['flight', 'train', 'bus', 'taxi'].includes(item.item_type) && (
                                <Text className="item-route">
                                  {item.origin}{item.departure_terminal && `(${item.departure_terminal})`}
                                  {item.departure_time && ` ${item.departure_time}`}
                                  {' → '}
                                  {item.destination}{item.arrival_terminal && `(${item.arrival_terminal})`}
                                  {item.arrival_time && ` ${item.arrival_time}`}
                                </Text>
                              )}
                              {item.location && <Text className="item-location">📍 {item.location}</Text>}
                              {item.description && <Text className="item-desc">{item.description}</Text>}
                            </View>
                            {item.id && (
                              <Text className="item-delete" onClick={() => handleDeleteItem(item.id!)}>删除</Text>
                            )}
                          </View>
                        ))}
                      </View>
                    </View>
                  );
                })}
              </View>
            ) : (
              <View className="empty-state">
                <Text className="empty-text">暂无行程明细</Text>
                <Text className="add-item-btn" onClick={openEdit}>添加明细</Text>
              </View>
            )}
          </>
        )}
      </ScrollView>
    );
  }

  // =====================================================
  // 创建/编辑表单
  // =====================================================
  const isEdit = view === 'edit';
  const dateRange = getDateRange(formStart, formEnd);

  return (
    <ScrollView className="trip-page" scrollY>
      <View className="detail-header">
        <Text className="back-btn" onClick={() => setView(isEdit ? 'detail' : 'list')}>← 返回</Text>
        <Text className="detail-title">{isEdit ? '编辑行程' : '新建行程'}</Text>
      </View>

      {/* 基本信息 */}
      <View className="form-section">
        <Text className="form-title">基本信息</Text>
        <View className="form-group">
          <Text className="form-label">行程名称 *</Text>
          <Input
            className="form-input"
            placeholder="如：成都之旅"
            value={formName}
            onInput={e => setFormName(e.detail.value)}
          />
        </View>
        <View className="form-group">
          <Text className="form-label">主要目的地</Text>
          <Input
            className="form-input"
            placeholder="如：成都"
            value={formDest}
            onInput={e => setFormDest(e.detail.value)}
          />
        </View>
        <View className="form-row">
          <View className="form-group">
            <Text className="form-label">开始日期 *</Text>
            <Picker mode="date" value={formStart} onChange={e => setFormStart(e.detail.value)}>
              <Text className={`date-picker ${!formStart ? 'date-placeholder' : ''}`}>
                {formStart || '选择日期'}
              </Text>
            </Picker>
          </View>
          <View className="form-group">
            <Text className="form-label">结束日期 *</Text>
            <Picker mode="date" value={formEnd} onChange={e => setFormEnd(e.detail.value)}>
              <Text className={`date-picker ${!formEnd ? 'date-placeholder' : ''}`}>
                {formEnd || '选择日期'}
              </Text>
            </Picker>
          </View>
        </View>
        <View className="form-group">
          <Text className="form-label">备注</Text>
          <Input
            className="form-input"
            placeholder="可选"
            value={formNotes}
            onInput={e => setFormNotes(e.detail.value)}
          />
        </View>
      </View>

      {/* 每日明细 */}
      {dateRange.length > 0 && (
        <View>
          <Text className="form-title" style={{ marginBottom: '12px' }}>每日行程明细</Text>
          {dateRange.map(dateStr => {
            const dayItems = formItems
              .map((item, idx) => ({ item, idx }))
              .filter(({ item }) => item.item_date === dateStr);

            return (
              <View key={dateStr} className="day-form-card">
                <View className="day-form-header">
                  <Text className="day-form-title">{formatDate(dateStr)}</Text>
                  <Text className="add-item-btn" onClick={() => addItemToDay(dateStr)}>+ 添加</Text>
                </View>

                {dayItems.length === 0 ? (
                  <Text className="empty-items">点击"添加"记录当天行程</Text>
                ) : (
                  dayItems.map(({ item, idx }) => {
                    const isTransport = ['flight', 'train', 'bus', 'taxi'].includes(item.item_type);
                    return (
                      <View key={idx} className="item-form">
                        <View className="item-form-top">
                          <Picker
                            mode="selector"
                            range={ITEM_TYPES}
                            rangeKey="label"
                            value={ITEM_TYPES.findIndex(t => t.value === item.item_type)}
                            onChange={e => {
                              const selected = ITEM_TYPES[Number(e.detail.value)];
                              updateFormItem(idx, 'item_type', selected.value);
                            }}
                          >
                            <Text className="type-picker">
                              {getItemIcon(item.item_type)} {ITEM_TYPES.find(t => t.value === item.item_type)?.label}
                            </Text>
                          </Picker>
                          <Input
                            className="item-title-input"
                            placeholder="标题"
                            value={item.title}
                            onInput={e => updateFormItem(idx, 'title', e.detail.value)}
                          />
                          <Text className="remove-item-btn" onClick={() => removeFormItem(idx)}>删除</Text>
                        </View>

                        {isTransport && (
                          <View className="item-form-fields">
                            <Input
                              className="field-input"
                              placeholder="承运方"
                              value={item.carrier || ''}
                              onInput={e => updateFormItem(idx, 'carrier', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="航班号/车次"
                              value={item.transport_number || ''}
                              onInput={e => updateFormItem(idx, 'transport_number', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="出发地"
                              value={item.origin || ''}
                              onInput={e => updateFormItem(idx, 'origin', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="出发航站楼"
                              value={item.departure_terminal || ''}
                              onInput={e => updateFormItem(idx, 'departure_terminal', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="出发时间 09:30"
                              value={item.departure_time || ''}
                              onInput={e => updateFormItem(idx, 'departure_time', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="到达时间 12:40"
                              value={item.arrival_time || ''}
                              onInput={e => updateFormItem(idx, 'arrival_time', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="目的地"
                              value={item.destination || ''}
                              onInput={e => updateFormItem(idx, 'destination', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="到达航站楼"
                              value={item.arrival_terminal || ''}
                              onInput={e => updateFormItem(idx, 'arrival_terminal', e.detail.value)}
                            />
                          </View>
                        )}

                        {!isTransport && (
                          <View className="item-form-fields">
                            <Input
                              className="field-input"
                              placeholder="地点"
                              value={item.location || ''}
                              onInput={e => updateFormItem(idx, 'location', e.detail.value)}
                            />
                            <Input
                              className="field-input"
                              placeholder="描述"
                              value={item.description || ''}
                              onInput={e => updateFormItem(idx, 'description', e.detail.value)}
                            />
                          </View>
                        )}
                      </View>
                    );
                  })
                )}
              </View>
            );
          })}
        </View>
      )}

      {/* 提交 */}
      <Text
        className={`submit-btn ${submitting ? 'disabled' : ''}`}
        onClick={isEdit ? handleUpdate : handleSubmit}
      >
        {submitting ? '保存中...' : '保存行程'}
      </Text>
      {error && <Text className="error-text">{error}</Text>}
    </ScrollView>
  );
}
