'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

import { MedicalExam } from './components/types';
import { PdfUploadSection } from './components/PdfUploadSection';
import { ExamForm } from './components/ExamForm';
import { ExamRecordCard } from './components/ExamRecordCard';
import { StatsCards } from './components/StatsCards';

// 使用相对路径，通过Next.js代理到后端
const API_BASE = '/api';

/* eslint-disable @typescript-eslint/no-explicit-any */

function MedicalExamsContent() {
  const { user, isAuthenticated } = useAuth();
  const userId = user?.id;
  const [showForm, setShowForm] = useState(false);
  const [showPdfUpload, setShowPdfUpload] = useState(false);
  const [expandedExam, setExpandedExam] = useState<number | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfPreview, setPdfPreview] = useState<any>(null);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const queryClient = useQueryClient();
  const today = format(new Date(), 'yyyy-MM-dd');

  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  // 获取体检记录
  const { data: examsResponse, isLoading } = useQuery({
    queryKey: ['medical-exams'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/medical-exams/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: isAuthenticated,
  });

  const exams: MedicalExam[] = Array.isArray(examsResponse) ? examsResponse : [];

  // 创建体检记录
  const createMutation = useMutation({
    mutationFn: async (data: any) => {
      const res = await fetch(`${API_BASE}/medical-exams/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error('创建失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['medical-exams'] });
      setShowForm(false);
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
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const responseText = await res.text();

      if (!res.ok) {
        try {
          const error = JSON.parse(responseText);
          throw new Error(error.detail || '解析失败');
        } catch (e) {
          if (responseText.startsWith('<')) {
            throw new Error(`服务器返回错误 (${res.status})，请稍后重试`);
          }
          throw new Error(responseText.slice(0, 200) || `解析失败 (${res.status})`);
        }
      }

      try {
        return JSON.parse(responseText);
      } catch (e) {
        throw new Error('服务器返回格式错误');
      }
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
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      });

      const responseText = await res.text();

      if (!res.ok) {
        try {
          const error = JSON.parse(responseText);
          throw new Error(error.detail || '导入失败');
        } catch (e) {
          if (responseText.startsWith('<')) {
            throw new Error(`服务器返回错误 (${res.status})，请稍后重试`);
          }
          throw new Error(responseText.slice(0, 200) || `导入失败 (${res.status})`);
        }
      }

      try {
        return JSON.parse(responseText);
      } catch (e) {
        throw new Error('服务器返回格式错误');
      }
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
      setUploadProgress('');
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

  // 统计异常项目数量
  const getAbnormalCount = (exam: MedicalExam) => {
    return exam.items.filter((item) => item.is_abnormal && item.is_abnormal !== 'normal').length;
  };

  if (isLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
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
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 pt-4 pb-8 px-8">
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
          <PdfUploadSection
            pdfFile={pdfFile}
            pdfPreview={pdfPreview}
            uploadProgress={uploadProgress}
            previewPdfMutation={previewPdfMutation}
            uploadPdfMutation={uploadPdfMutation}
            onPdfSelect={handlePdfSelect}
            onPdfImport={handlePdfImport}
            onReset={() => { setPdfFile(null); setPdfPreview(null); setUploadProgress(''); }}
          />
        )}

        {/* 统计卡片 */}
        <StatsCards exams={exams} getAbnormalCount={getAbnormalCount} />

        {/* 添加体检记录表单 */}
        {showForm && (
          <ExamForm userId={userId} createMutation={createMutation} />
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
              <ExamRecordCard
                key={exam.id}
                exam={exam}
                isExpanded={expandedExam === exam.id}
                onToggle={() => setExpandedExam(expandedExam === exam.id ? null : exam.id)}
                abnormalCount={getAbnormalCount(exam)}
              />
            ))
          )}
        </div>
      </div>
    </main>
  );
}

// 导出受保护的页面
export default function MedicalExamsPage() {
  return (
    <ProtectedRoute>
      <MedicalExamsContent />
    </ProtectedRoute>
  );
}
