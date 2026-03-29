'use client';

import React, { useState } from 'react';
import { UseMutationResult } from '@tanstack/react-query';
import { examTypeLabels, bodySystemLabels, examPackages, abnormalStyles, abnormalLabels } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */

interface ExamFormProps {
  userId: number | undefined;
  createMutation: UseMutationResult<any, any, any, unknown>;
}

export function ExamForm({ userId, createMutation }: ExamFormProps) {
  const today = new Date().toISOString().split('T')[0];

  const [formData, setFormData] = useState({
    exam_date: today,
    exam_type: 'blood_routine',
    body_system: '',
    hospital_name: '',
    doctor_name: '',
    overall_assessment: '',
    notes: '',
  });

  const [items, setItems] = useState<Array<{
    item_name: string;
    value: string;
    unit: string;
    reference_range: string;
    is_abnormal: string;
    notes: string;
  }>>([]);

  const [newItem, setNewItem] = useState({
    item_name: '',
    value: '',
    unit: '',
    reference_range: '',
    is_abnormal: 'normal',
    notes: '',
  });

  const [showItemForm, setShowItemForm] = useState(false);
  const [selectedPackage, setSelectedPackage] = useState<string>('');

  const handleAddItem = () => {
    if (!newItem.item_name) {
      alert('请输入检查项目名称');
      return;
    }
    setItems([...items, { ...newItem }]);
    setNewItem({
      item_name: '',
      value: '',
      unit: '',
      reference_range: '',
      is_abnormal: 'normal',
      notes: '',
    });
    setShowItemForm(false);
  };

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate({
      user_id: userId,
      exam_date: formData.exam_date,
      exam_type: formData.exam_type,
      body_system: formData.body_system || null,
      hospital_name: formData.hospital_name || null,
      doctor_name: formData.doctor_name || null,
      overall_assessment: formData.overall_assessment || null,
      notes: formData.notes || null,
      items: items.map((item) => ({
        item_name: item.item_name,
        value: item.value ? parseFloat(item.value) : null,
        unit: item.unit || null,
        reference_range: item.reference_range || null,
        is_abnormal: item.is_abnormal,
        notes: item.notes || null,
      })),
    });
  };

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-teal-200">
      <h3 className="text-xl font-bold text-gray-900 mb-4">🏥 添加体检记录</h3>
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* 基本信息 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-2">体检日期 *</label>
            <input
              type="date"
              required
              value={formData.exam_date}
              onChange={(e) => setFormData({ ...formData, exam_date: e.target.value })}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-2">体检类型 *</label>
            <select
              required
              value={formData.exam_type}
              onChange={(e) => setFormData({ ...formData, exam_type: e.target.value })}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
            >
              {Object.entries(examTypeLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-2">身体系统</label>
            <select
              value={formData.body_system}
              onChange={(e) => setFormData({ ...formData, body_system: e.target.value })}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
            >
              <option value="">选择系统</option>
              {Object.entries(bodySystemLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* 体检套餐快速选择 */}
        <div className="border border-purple-200 rounded-lg p-4 bg-purple-50">
          <label className="block text-sm font-semibold text-purple-800 mb-3">🧪 体检套餐（快速添加检查项目）</label>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
            {Object.entries(examPackages).map(([key, pkg]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  const newItems = pkg.items.map(itemKey => ({
                    item_name: examTypeLabels[itemKey] || itemKey,
                    value: '',
                    unit: '',
                    reference_range: '',
                    is_abnormal: 'normal',
                    notes: '',
                  }));
                  setItems([...items, ...newItems]);
                  setSelectedPackage(key);
                }}
                className={`px-3 py-2 text-xs rounded-lg border transition-all text-left ${
                  selectedPackage === key
                    ? 'bg-purple-600 text-white border-purple-600'
                    : 'bg-white text-purple-700 border-purple-300 hover:bg-purple-100'
                }`}
              >
                <div className="font-medium">{pkg.name}</div>
                <div className="text-[10px] opacity-75 truncate">{pkg.description}</div>
              </button>
            ))}
          </div>
          <p className="text-xs text-purple-600 mt-2">💡 点击套餐可快速添加相关检查项目到列表</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-2">医院名称</label>
            <input
              type="text"
              value={formData.hospital_name}
              onChange={(e) => setFormData({ ...formData, hospital_name: e.target.value })}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
              placeholder="例如：北京协和医院"
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-2">医生姓名</label>
            <input
              type="text"
              value={formData.doctor_name}
              onChange={(e) => setFormData({ ...formData, doctor_name: e.target.value })}
              className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
              placeholder="例如：张医生"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-800 mb-2">总体评价</label>
          <textarea
            value={formData.overall_assessment}
            onChange={(e) => setFormData({ ...formData, overall_assessment: e.target.value })}
            className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
            rows={2}
            placeholder="医生对本次体检的总体评价..."
          />
        </div>

        {/* 检查项目 */}
        <div className="border-t pt-4">
          <div className="flex justify-between items-center mb-3">
            <h4 className="font-bold text-gray-800">📋 检查项目 ({items.length}项)</h4>
            <button
              type="button"
              onClick={() => setShowItemForm(true)}
              className="px-3 py-1 bg-teal-100 text-teal-700 rounded-lg hover:bg-teal-200 text-sm font-medium"
            >
              + 添加项目
            </button>
          </div>

          {/* 添加项目表单 */}
          {showItemForm && (
            <div className="bg-gray-50 p-4 rounded-lg mb-4 border border-gray-200">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">项目名称 *</label>
                  <input
                    type="text"
                    value={newItem.item_name}
                    onChange={(e) => setNewItem({ ...newItem, item_name: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                    placeholder="例如：血红蛋白"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">检测值</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newItem.value}
                    onChange={(e) => setNewItem({ ...newItem, value: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                    placeholder="例如：145"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">单位</label>
                  <input
                    type="text"
                    value={newItem.unit}
                    onChange={(e) => setNewItem({ ...newItem, unit: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                    placeholder="例如：g/L"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">参考范围</label>
                  <input
                    type="text"
                    value={newItem.reference_range}
                    onChange={(e) => setNewItem({ ...newItem, reference_range: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                    placeholder="例如：130-175"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">结果状态</label>
                  <select
                    value={newItem.is_abnormal}
                    onChange={(e) => setNewItem({ ...newItem, is_abnormal: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                  >
                    <option value="normal">正常</option>
                    <option value="high">偏高</option>
                    <option value="low">偏低</option>
                    <option value="abnormal">异常</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">备注</label>
                  <input
                    type="text"
                    value={newItem.notes}
                    onChange={(e) => setNewItem({ ...newItem, notes: e.target.value })}
                    className="w-full p-2 border border-gray-300 rounded text-sm text-gray-900"
                    placeholder="可选备注"
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleAddItem}
                  className="px-3 py-1 bg-teal-600 text-white rounded text-sm hover:bg-teal-700"
                >
                  确认添加
                </button>
                <button
                  type="button"
                  onClick={() => setShowItemForm(false)}
                  className="px-3 py-1 bg-gray-300 text-gray-700 rounded text-sm hover:bg-gray-400"
                >
                  取消
                </button>
              </div>
            </div>
          )}

          {/* 已添加的项目列表 */}
          {items.length > 0 && (
            <div className="space-y-2">
              {items.map((item, index) => (
                <div key={index} className="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                  <div className="flex items-center gap-4">
                    <span className="font-medium text-gray-900">{item.item_name}</span>
                    {item.value && (
                      <span className="text-gray-600">
                        {item.value} {item.unit}
                      </span>
                    )}
                    {item.reference_range && (
                      <span className="text-xs text-gray-500">参考: {item.reference_range}</span>
                    )}
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal]}`}>
                      {abnormalLabels[item.is_abnormal]}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveItem(index)}
                    className="text-red-500 hover:text-red-700"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-800 mb-2">备注</label>
          <textarea
            value={formData.notes}
            onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
            className="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-teal-500 text-gray-900"
            rows={2}
            placeholder="其他备注信息..."
          />
        </div>

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="w-full py-3 bg-gradient-to-r from-teal-500 to-cyan-600 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-700 disabled:opacity-50 shadow-md"
        >
          {createMutation.isPending ? '保存中...' : '保存体检记录'}
        </button>
      </form>
    </div>
  );
}
