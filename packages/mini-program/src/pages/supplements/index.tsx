/**
 * 补剂服用打卡页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Button, Input, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, put } from '../../services/request';
import './index.scss';

interface SupplementDefinition {
  id: number;
  name: string;
  dosage: string;
  timing: string;
  category: string;
  description?: string;
  is_active: boolean;
}

interface SupplementRecord {
  supplement_id: number;
  taken: boolean;
  taken_time?: string;
}

interface SupplementWithStatus {
  supplement: SupplementDefinition;
  record: SupplementRecord | null;
}

interface SupplementStats {
  supplement_id: number;
  supplement_name: string;
  taken_days: number;
  total_days: number;
  completion_rate: number;
}

const TIMING_OPTIONS = [
  { value: 'morning', label: '🌅 早晨', color: 'orange' },
  { value: 'noon', label: '☀️ 中午', color: 'yellow' },
  { value: 'evening', label: '🌆 晚上', color: 'purple' },
  { value: 'bedtime', label: '🌙 睡前', color: 'indigo' },
];

const CATEGORY_OPTIONS = [
  { value: 'vitamin', label: '维生素' },
  { value: 'mineral', label: '矿物质' },
  { value: 'antioxidant', label: '抗氧化' },
  { value: 'amino', label: '氨基酸' },
  { value: 'herb', label: '草药/中药' },
  { value: 'other', label: '其他' },
];

export default function SupplementsPage() {
  const [loading, setLoading] = useState(true);
  const [supplements, setSupplements] = useState<SupplementWithStatus[]>([]);
  const [stats, setStats] = useState<SupplementStats[]>([]);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showActionSheet, setShowActionSheet] = useState(false);
  const [selectedSupplement, setSelectedSupplement] = useState<SupplementDefinition | null>(null);
  
  // 新增/编辑补剂表单
  const [formData, setFormData] = useState({
    name: '',
    dosage: '',
    timing: 'morning',
    category: 'vitamin',
    description: '',
  });

  useEffect(() => {
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      Taro.switchTab({ url: '/pages/index/index' });
      return;
    }
    loadData();
    loadStats();
  }, [selectedDate]);

  const loadData = async () => {
    setLoading(true);
    try {
      // 使用与 Web 端一致的接口：/supplements/me/date/{date}
      const data = await get<{ data: SupplementWithStatus[] }>(`/supplements/me/date/${selectedDate}`);
      setSupplements(data?.data || []);
    } catch (error) {
      console.error('加载补剂数据失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const loadStats = async () => {
    try {
      // 使用与 Web 端一致的接口：/supplements/me/stats?days=7
      const data = await get<{ data: SupplementStats[] }>('/supplements/me/stats?days=7');
      setStats(data?.data || []);
    } catch (error) {
      console.error('加载统计数据失败:', error);
    }
  };

  const handleToggle = async (supplementId: number, currentTaken: boolean) => {
    try {
      // 使用与 Web 端一致的批量打卡接口：/supplements/records/batch
      await post('/supplements/records/batch', {
        record_date: selectedDate,
        checkins: [{ supplement_id: supplementId, taken: !currentTaken }],
      });
      
      Taro.showToast({ 
        title: currentTaken ? '已取消' : '已服用 ✓', 
        icon: 'success' 
      });
      loadData();
    } catch (error) {
      Taro.showToast({ title: '操作失败', icon: 'none' });
    }
  };

  const handleAddSupplement = async () => {
    if (!formData.name.trim()) {
      Taro.showToast({ title: '请输入补剂名称', icon: 'none' });
      return;
    }
    
    setSubmitting(true);
    try {
      if (editingId) {
        // 编辑模式：使用 PUT 接口
        await put(`/supplements/definitions/${editingId}`, formData);
        Taro.showToast({ title: '更新成功', icon: 'success' });
      } else {
        // 新增模式：使用 POST 接口
        await post('/supplements/definitions', formData);
        Taro.showToast({ title: '添加成功', icon: 'success' });
      }
      
      setShowAddForm(false);
      setEditingId(null);
      setFormData({
        name: '',
        dosage: '',
        timing: 'morning',
        category: 'vitamin',
        description: '',
      });
      loadData();
      loadStats();
    } catch (error) {
      Taro.showToast({ title: editingId ? '更新失败' : '添加失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditSupplement = (supplement: SupplementDefinition) => {
    setEditingId(supplement.id);
    setFormData({
      name: supplement.name,
      dosage: supplement.dosage || '',
      timing: supplement.timing,
      category: supplement.category,
      description: supplement.description || '',
    });
    setShowAddForm(true);
    setShowActionSheet(false);
  };

  const handleDeleteSupplement = async (supplementId: number) => {
    const res = await Taro.showModal({
      title: '确认删除',
      content: '删除后将无法恢复，确定要删除这个补剂吗？',
    });
    
    if (!res.confirm) return;
    
    try {
      await post(`/supplements/definitions/${supplementId}`, {}, 'DELETE');
      Taro.showToast({ title: '删除成功', icon: 'success' });
      setShowActionSheet(false);
      loadData();
      loadStats();
    } catch (error) {
      Taro.showToast({ title: '删除失败', icon: 'none' });
    }
  };

  const handleToggleActive = async (supplement: SupplementDefinition) => {
    try {
      await put(`/supplements/definitions/${supplement.id}`, {
        ...supplement,
        is_active: !supplement.is_active,
      });
      Taro.showToast({ 
        title: supplement.is_active ? '已停用' : '已启用', 
        icon: 'success' 
      });
      setShowActionSheet(false);
      loadData();
      loadStats();
    } catch (error) {
      Taro.showToast({ title: '操作失败', icon: 'none' });
    }
  };

  const handleShowActionSheet = (supplement: SupplementDefinition, e: any) => {
    e.stopPropagation();
    setSelectedSupplement(supplement);
    setShowActionSheet(true);
  };

  // 按时间段分组
  const groupedSupplements = TIMING_OPTIONS.map(timing => ({
    ...timing,
    items: supplements.filter(s => s.supplement.timing === timing.value),
  }));

  // 计算完成率
  const totalCount = supplements.length;
  const takenCount = supplements.filter(s => s.record?.taken).length;
  const completionRate = totalCount > 0 ? Math.round((takenCount / totalCount) * 100) : 0;

  if (loading) {
    return (
      <View className="supplements-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <View className="supplements-page">
      {/* 头部统计 */}
      <View className="header-stats">
        <View className="stat-left">
          <Text className="stat-title">💊 今日补剂打卡</Text>
          <Picker
            mode="date"
            value={selectedDate}
            onChange={e => setSelectedDate(e.detail.value)}
          >
            <View className="date-picker">
              <Text className="date-text">{selectedDate}</Text>
              <Text className="date-icon">📅</Text>
            </View>
          </Picker>
        </View>
        <View className="stat-right">
          <Text className="stat-value">{takenCount}/{totalCount}</Text>
          <Text className="stat-label">完成率 {completionRate}%</Text>
          <View className="progress-bar">
            <View className="progress-fill" style={`width: ${completionRate}%`} />
          </View>
        </View>
      </View>

      {/* 补剂列表和统计 */}
      <ScrollView scrollY className="supplements-scroll" enhanced showScrollbar={false}>
        {supplements.length === 0 ? (
          <View className="empty-state">
            <Text className="empty-icon">💊</Text>
            <Text className="empty-title">还没有添加补剂</Text>
            <Text className="empty-desc">点击下方按钮添加你的补剂清单</Text>
          </View>
        ) : (
          groupedSupplements.map(group => (
            group.items.length > 0 && (
              <View key={group.value} className="timing-group">
                <View className={`timing-header ${group.color}`}>
                  <Text className="timing-label">{group.label}</Text>
                  <Text className="timing-count">
                    {group.items.filter(s => s.record?.taken).length}/{group.items.length}
                  </Text>
                </View>
                
                {group.items.map(item => (
                  <View 
                    key={item.supplement.id} 
                    className={`supplement-card ${item.record?.taken ? 'taken' : ''} ${!item.supplement.is_active ? 'inactive' : ''}`}
                  >
                    <View 
                      className="supplement-main"
                      onClick={() => handleToggle(item.supplement.id, item.record?.taken || false)}
                    >
                      <View className="supplement-info">
                        <View className="supplement-name-row">
                          <Text className="supplement-name">{item.supplement.name}</Text>
                          {!item.supplement.is_active && (
                            <Text className="inactive-badge">已停用</Text>
                          )}
                        </View>
                        {item.supplement.dosage && (
                          <Text className="supplement-dosage">{item.supplement.dosage}</Text>
                        )}
                        {item.supplement.description && (
                          <Text className="supplement-desc">{item.supplement.description}</Text>
                        )}
                      </View>
                      <View className={`check-box ${item.record?.taken ? 'checked' : ''}`}>
                        {item.record?.taken && <Text className="check-icon">✓</Text>}
                      </View>
                    </View>
                    <View 
                      className="supplement-more"
                      onClick={(e) => handleShowActionSheet(item.supplement, e)}
                    >
                      <Text className="more-icon">⋯</Text>
                    </View>
                  </View>
                ))}
              </View>
            )
          ))
        )}

        {/* 最近7天统计 */}
        {stats.length > 0 && (
          <View className="stats-section">
            <Text className="stats-title">📊 最近7天统计</Text>
            {stats.map(stat => (
              <View key={stat.supplement_id} className="stat-item-row">
                <View className="stat-info">
                  <Text className="stat-name">{stat.supplement_name}</Text>
                  <Text className="stat-days">{stat.taken_days}/7天</Text>
                </View>
                <View className="stat-progress">
                  <View className="stat-progress-bar">
                    <View 
                      className={`stat-progress-fill ${
                        stat.completion_rate >= 80 ? 'green' :
                        stat.completion_rate >= 50 ? 'yellow' : 'red'
                      }`}
                      style={`width: ${stat.completion_rate}%`}
                    />
                  </View>
                  <Text className="stat-percentage">{stat.completion_rate}%</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* 添加按钮 */}
      <View className="add-btn-container">
        <Button className="add-btn" onClick={() => setShowAddForm(true)}>
          + 添加补剂
        </Button>
      </View>

      {/* 添加/编辑补剂弹窗 */}
      {showAddForm && (
        <View className="modal-mask" onClick={() => {
          setShowAddForm(false);
          setEditingId(null);
          setFormData({
            name: '',
            dosage: '',
            timing: 'morning',
            category: 'vitamin',
            description: '',
          });
        }}>
          <View className="modal-content" onClick={e => e.stopPropagation()}>
            <View className="modal-header">
              <Text className="modal-title">{editingId ? '编辑补剂' : '添加补剂'}</Text>
            </View>
            
            <View className="form-group">
              <Text className="form-label">补剂名称 *</Text>
              <Input
                className="form-input"
                value={formData.name}
                onInput={e => setFormData({ ...formData, name: e.detail.value })}
                placeholder="如：维生素D3"
              />
            </View>
            
            <View className="form-group">
              <Text className="form-label">剂量</Text>
              <Input
                className="form-input"
                value={formData.dosage}
                onInput={e => setFormData({ ...formData, dosage: e.detail.value })}
                placeholder="如：5000IU"
              />
            </View>
            
            <View className="form-group">
              <Text className="form-label">服用时间</Text>
              <View className="timing-options">
                {TIMING_OPTIONS.map(opt => (
                  <View
                    key={opt.value}
                    className={`timing-option ${formData.timing === opt.value ? 'active' : ''}`}
                    onClick={() => setFormData({ ...formData, timing: opt.value })}
                  >
                    <Text>{opt.label}</Text>
                  </View>
                ))}
              </View>
            </View>
            
            <View className="form-group">
              <Text className="form-label">分类</Text>
              <View className="category-options">
                {CATEGORY_OPTIONS.map(opt => (
                  <View
                    key={opt.value}
                    className={`category-option ${formData.category === opt.value ? 'active' : ''}`}
                    onClick={() => setFormData({ ...formData, category: opt.value })}
                  >
                    <Text>{opt.label}</Text>
                  </View>
                ))}
              </View>
            </View>
            
            <View className="form-group">
              <Text className="form-label">描述（选填）</Text>
              <Input
                className="form-input"
                value={formData.description}
                onInput={e => setFormData({ ...formData, description: e.detail.value })}
                placeholder="如：促进钙吸收"
              />
            </View>
            
            <View className="modal-actions">
              <Button className="modal-btn cancel" onClick={() => {
                setShowAddForm(false);
                setEditingId(null);
                setFormData({
                  name: '',
                  dosage: '',
                  timing: 'morning',
                  category: 'vitamin',
                  description: '',
                });
              }}>
                取消
              </Button>
              <Button 
                className="modal-btn confirm" 
                onClick={handleAddSupplement}
                loading={submitting}
              >
                {editingId ? '保存' : '添加'}
              </Button>
            </View>
          </View>
        </View>
      )}

      {/* 操作菜单 */}
      {showActionSheet && selectedSupplement && (
        <View className="modal-mask" onClick={() => setShowActionSheet(false)}>
          <View className="action-sheet" onClick={e => e.stopPropagation()}>
            <View className="action-sheet-header">
              <Text className="action-sheet-title">{selectedSupplement.name}</Text>
            </View>
            <View className="action-sheet-body">
              <View 
                className="action-item"
                onClick={() => handleEditSupplement(selectedSupplement)}
              >
                <Text className="action-icon">✏️</Text>
                <Text className="action-text">编辑补剂</Text>
              </View>
              <View 
                className="action-item"
                onClick={() => handleToggleActive(selectedSupplement)}
              >
                <Text className="action-icon">{selectedSupplement.is_active ? '⏸️' : '▶️'}</Text>
                <Text className="action-text">{selectedSupplement.is_active ? '停用补剂' : '启用补剂'}</Text>
              </View>
              <View 
                className="action-item danger"
                onClick={() => handleDeleteSupplement(selectedSupplement.id)}
              >
                <Text className="action-icon">🗑️</Text>
                <Text className="action-text">删除补剂</Text>
              </View>
            </View>
            <View className="action-sheet-footer">
              <Button 
                className="action-cancel"
                onClick={() => setShowActionSheet(false)}
              >
                取消
              </Button>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
