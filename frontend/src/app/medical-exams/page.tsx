'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// 体检类型映射
const examTypeLabels: Record<string, string> = {
  blood_routine: '血常规',
  lipid_profile: '血脂',
  urine_routine: '尿常规',
  immune: '免疫',
  liver_function: '肝功能',
  kidney_function: '肾功能',
  thyroid: '甲状腺',
  other: '其他',
};

// 身体系统映射
const bodySystemLabels: Record<string, string> = {
  nervous: '神经系统',
  circulatory: '循环系统',
  respiratory: '呼吸系统',
  digestive: '消化系统',
  urinary: '泌尿系统',
  endocrine: '内分泌系统',
  immune: '免疫系统',
  skeletal: '骨骼系统',
  muscular: '肌肉系统',
  other: '其他',
};

// 异常状态样式
const abnormalStyles: Record<string, string> = {
  normal: 'bg-green-100 text-green-800',
  abnormal: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  low: 'bg-blue-100 text-blue-800',
};

const abnormalLabels: Record<string, string> = {
  normal: '正常',
  abnormal: '异常',
  high: '偏高',
  low: '偏低',
};

interface MedicalExamItem {
  id: number;
  item_name: string;
  item_code?: string;
  value?: number;
  unit?: string;
  reference_range?: string;
  result?: string;
  is_abnormal?: string;
  notes?: string;
}

interface MedicalExam {
  id: number;
  user_id: number;
  exam_date: string;
  exam_type: string;
  body_system?: string;
  hospital_name?: string;
  doctor_name?: string;
  overall_assessment?: string;
  notes?: string;
  items: MedicalExamItem[];
}

export default function MedicalExamsPage() {
  const [userId] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [showPdfUpload, setShowPdfUpload] = useState(false);
  const [expandedExam, setExpandedExam] = useState<number | null>(null);
  const [showItemForm, setShowItemForm] = useState(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfPreview, setPdfPreview] = useState<any>(null);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const queryClient = useQueryClient();
  const today = format(new Date(), 'yyyy-MM-dd');

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

  // 获取体检记录
  const { data: examsResponse, isLoading } = useQuery({
    queryKey: ['medical-exams', userId],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/medical-exams/user/${userId}`);
      return res.json();
    },
  });

  const exams: MedicalExam[] = Array.isArray(examsResponse) ? examsResponse : [];

  // 创建体检记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/medical-exams/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('创建失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
      setShowForm(false);
      setFormData({
        exam_date: today,
        exam_type: 'blood_routine',
        body_system: '',
        hospital_name: '',
        doctor_name: '',
        overall_assessment: '',
        notes: '',
      });
      setItems([]);
      alert('✅ 体检记录创建成功！');
    },
    onError: () => {
      alert('❌ 创建失败，请重试');
    },
  });

  // PDF预览解析
  const previewPdfMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/medical-exams/parse-pdf-preview`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '解析失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      setPdfPreview(data);
      setUploadProgress('解析完成，请确认结果');
    },
    onError: (error: any) => {
      setUploadProgress('');
      alert(`❌ PDF解析失败: ${error.message}`);
    },
  });

  // PDF上传导入
  const uploadPdfMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${API_BASE}/medical-exams/import/pdf?user_id=${userId}`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || '导入失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
      setShowPdfUpload(false);
      setPdfFile(null);
      setPdfPreview(null);
      setUploadProgress('');
      alert(`✅ PDF导入成功！已解析 ${data.items_count} 个检查项目`);
    },
    onError: (error: any) => {
      alert(`❌ PDF导入失败: ${error.message}`);
    },
  });

  const handlePdfSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('请选择PDF格式文件');
        return;
      }
      setPdfFile(file);
      setPdfPreview(null);
      setUploadProgress('正在解析PDF...');
      previewPdfMutation.mutate(file);
    }
  };

  const handlePdfImport = () => {
    if (pdfFile) {
      setUploadProgress('正在导入...');
      uploadPdfMutation.mutate(pdfFile);
    }
  };

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

  // 统计异常项目数量
  const getAbnormalCount = (exam: MedicalExam) => {
    return exam.items.filter((item) => item.is_abnormal && item.is_abnormal !== 'normal').length;
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="text-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-800 text-lg font-medium">加载中...</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-24 pb-8 px-8">
      <div className="max-w-6xl mx-auto">
        {/* 头部 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <p className="text-gray-600 text-sm">管理您的体检报告和检查项目</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => { setShowPdfUpload(!showPdfUpload); setShowForm(false); }}
              className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 shadow-md transition-all flex items-center gap-2"
            >
              📄 {showPdfUpload ? '取消上传' : '上传PDF'}
            </button>
            <button
              onClick={() => { setShowForm(!showForm); setShowPdfUpload(false); }}
              className="px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-600 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-700 shadow-md transition-all"
            >
            {showForm ? '取消' : '+ 添加体检记录'}
            </button>
          </div>
        </div>

        {/* PDF上传区域 */}
        {showPdfUpload && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-purple-200">
            <h3 className="text-xl font-bold text-gray-900 mb-4">📄 上传体检报告PDF</h3>
            <p className="text-gray-600 text-sm mb-4">
              上传体检报告PDF文件，系统将使用AI自动解析并提取检查项目数据。
            </p>
            
            {/* 文件选择 */}
            <div className="border-2 border-dashed border-purple-300 rounded-lg p-8 text-center mb-4 hover:border-purple-500 transition-colors">
              <input
                type="file"
                accept=".pdf"
                onChange={handlePdfSelect}
                className="hidden"
                id="pdf-upload"
              />
              <label htmlFor="pdf-upload" className="cursor-pointer">
                <div className="text-5xl mb-3">📁</div>
                <p className="text-gray-700 font-medium mb-2">
                  {pdfFile ? pdfFile.name : '点击或拖拽PDF文件到这里'}
                </p>
                <p className="text-gray-500 text-sm">支持 .pdf 格式</p>
              </label>
            </div>

            {/* 进度提示 */}
            {uploadProgress && (
              <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-200 text-blue-800">
                <div className="flex items-center gap-2">
                  {(previewPdfMutation.isPending || uploadPdfMutation.isPending) && (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600"></div>
                  )}
                  {uploadProgress}
                </div>
              </div>
            )}

            {/* 预览结果 */}
            {pdfPreview && (
              <div className="mb-4">
                <h4 className="font-bold text-gray-800 mb-3">📋 解析预览</h4>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">体检日期</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.exam_date || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">体检类型</div>
                    <div className="font-medium text-gray-900">{examTypeLabels[pdfPreview.parsed_data?.exam_type] || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">医院</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.hospital_name || '-'}</div>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <div className="text-xs text-gray-500">检查项目</div>
                    <div className="font-medium text-gray-900">{pdfPreview.parsed_data?.items?.length || 0} 项</div>
                  </div>
                </div>

                {/* 项目预览列表 */}
                {pdfPreview.parsed_data?.items?.length > 0 && (
                  <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-100 sticky top-0">
                        <tr>
                          <th className="text-left p-2 font-semibold text-gray-700">项目</th>
                          <th className="text-right p-2 font-semibold text-gray-700">检测值</th>
                          <th className="text-left p-2 font-semibold text-gray-700">单位</th>
                          <th className="text-left p-2 font-semibold text-gray-700">参考范围</th>
                          <th className="text-center p-2 font-semibold text-gray-700">状态</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pdfPreview.parsed_data.items.map((item: any, idx: number) => (
                          <tr key={idx} className="border-b border-gray-100">
                            <td className="p-2 text-gray-900">{item.item_name}</td>
                            <td className="p-2 text-right font-mono text-gray-900">{item.value ?? '-'}</td>
                            <td className="p-2 text-gray-600">{item.unit || '-'}</td>
                            <td className="p-2 text-gray-600">{item.reference_range || '-'}</td>
                            <td className="p-2 text-center">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal || 'normal']}`}>
                                {abnormalLabels[item.is_abnormal || 'normal']}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {pdfPreview.parsed_data?.overall_assessment && (
                  <div className="mt-3 p-3 bg-blue-50 rounded-lg border border-blue-100">
                    <div className="text-sm font-semibold text-blue-800 mb-1">总体评价</div>
                    <div className="text-gray-800 text-sm">{pdfPreview.parsed_data.overall_assessment}</div>
                  </div>
                )}
              </div>
            )}

            {/* 操作按钮 */}
            {pdfPreview && (
              <div className="flex gap-3">
                <button
                  onClick={handlePdfImport}
                  disabled={uploadPdfMutation.isPending}
                  className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 disabled:opacity-50 shadow-md"
                >
                  {uploadPdfMutation.isPending ? '导入中...' : '✓ 确认导入'}
                </button>
                <button
                  onClick={() => { setPdfFile(null); setPdfPreview(null); setUploadProgress(''); }}
                  className="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300"
                >
                  重新选择
                </button>
              </div>
            )}
          </div>
        )}

        {/* 统计卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl shadow-md border border-teal-100">
            <p className="text-sm text-gray-600 mb-1">总体检次数</p>
            <p className="text-3xl font-bold text-teal-600">{exams.length}</p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-blue-100">
            <p className="text-sm text-gray-600 mb-1">检查项目</p>
            <p className="text-3xl font-bold text-blue-600">
              {exams.reduce((sum, exam) => sum + exam.items.length, 0)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-orange-100">
            <p className="text-sm text-gray-600 mb-1">异常项目</p>
            <p className="text-3xl font-bold text-orange-600">
              {exams.reduce((sum, exam) => sum + getAbnormalCount(exam), 0)}
            </p>
          </div>
          <div className="bg-white p-4 rounded-xl shadow-md border border-green-100">
            <p className="text-sm text-gray-600 mb-1">最近体检</p>
            <p className="text-lg font-bold text-green-600">
              {exams.length > 0 ? exams[0].exam_date : '-'}
            </p>
          </div>
        </div>

        {/* 添加体检记录表单 */}
        {showForm && (
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
        )}

        {/* 体检记录列表 */}
        <div className="space-y-4">
          {exams.length === 0 ? (
            <div className="bg-white rounded-xl shadow-md p-12 text-center">
              <div className="text-6xl mb-4">🏥</div>
              <h3 className="text-xl font-bold text-gray-800 mb-2">暂无体检记录</h3>
              <p className="text-gray-600">点击上方按钮添加您的第一条体检记录</p>
            </div>
          ) : (
            exams.map((exam) => (
              <div key={exam.id} className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
                {/* 记录头部 */}
                <div
                  className="p-4 cursor-pointer hover:bg-gray-50 transition-colors"
                  onClick={() => setExpandedExam(expandedExam === exam.id ? null : exam.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center">
                        <span className="text-2xl">🩺</span>
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-gray-900">{exam.exam_date}</span>
                          <span className="px-2 py-0.5 bg-teal-100 text-teal-700 rounded text-sm font-medium">
                            {examTypeLabels[exam.exam_type] || exam.exam_type}
                          </span>
                          {exam.body_system && (
                            <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-sm">
                              {bodySystemLabels[exam.body_system] || exam.body_system}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-600 mt-1">
                          {exam.hospital_name && <span>{exam.hospital_name}</span>}
                          {exam.doctor_name && <span className="ml-2">• {exam.doctor_name}</span>}
                          <span className="ml-2">• {exam.items.length} 项检查</span>
                          {getAbnormalCount(exam) > 0 && (
                            <span className="ml-2 text-orange-600 font-medium">
                              ⚠️ {getAbnormalCount(exam)} 项异常
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="text-gray-400 text-2xl">
                      {expandedExam === exam.id ? '▲' : '▼'}
                    </div>
                  </div>
                </div>

                {/* 展开的详情 */}
                {expandedExam === exam.id && (
                  <div className="border-t border-gray-100 p-4 bg-gray-50">
                    {exam.overall_assessment && (
                      <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
                        <div className="text-sm font-semibold text-blue-800 mb-1">📋 总体评价</div>
                        <div className="text-gray-800">{exam.overall_assessment}</div>
                      </div>
                    )}

                    {exam.items.length > 0 ? (
                      <div>
                        <h4 className="font-bold text-gray-800 mb-3">检查项目明细</h4>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-gray-100">
                                <th className="text-left p-2 font-semibold text-gray-700">项目名称</th>
                                <th className="text-right p-2 font-semibold text-gray-700">检测值</th>
                                <th className="text-left p-2 font-semibold text-gray-700">单位</th>
                                <th className="text-left p-2 font-semibold text-gray-700">参考范围</th>
                                <th className="text-center p-2 font-semibold text-gray-700">状态</th>
                                <th className="text-left p-2 font-semibold text-gray-700">备注</th>
                              </tr>
                            </thead>
                            <tbody>
                              {exam.items.map((item) => (
                                <tr key={item.id} className="border-b border-gray-100 hover:bg-white">
                                  <td className="p-2 font-medium text-gray-900">{item.item_name}</td>
                                  <td className="p-2 text-right font-mono text-gray-900">
                                    {item.value !== null && item.value !== undefined ? item.value : '-'}
                                  </td>
                                  <td className="p-2 text-gray-600">{item.unit || '-'}</td>
                                  <td className="p-2 text-gray-600">{item.reference_range || '-'}</td>
                                  <td className="p-2 text-center">
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${abnormalStyles[item.is_abnormal || 'normal']}`}>
                                      {abnormalLabels[item.is_abnormal || 'normal']}
                                    </span>
                                  </td>
                                  <td className="p-2 text-gray-600 text-xs">{item.notes || '-'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      <p className="text-gray-500 text-center py-4">暂无检查项目明细</p>
                    )}

                    {exam.notes && (
                      <div className="mt-4 p-3 bg-yellow-50 rounded-lg border border-yellow-100">
                        <div className="text-sm font-semibold text-yellow-800 mb-1">📝 备注</div>
                        <div className="text-gray-800">{exam.notes}</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </main>
  );
}

