'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { familyApi } from '@/services/api';

interface Report { id: number; report_date: string; hospital: string | null; title: string | null; status: string; abnormal_count: number; ai_summary: string | null; }

export default function ReportsPage() {
  return <ProtectedRoute><ReportsContent /></ProtectedRoute>;
}

function ReportsContent() {
  const router = useRouter();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadForm, setUploadForm] = useState({ report_date: new Date().toISOString().split('T')[0], hospital: '', title: '' });
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [trendName, setTrendName] = useState('');
  const [trendData, setTrendData] = useState<any>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { loadReports(); }, []);

  const loadReports = async () => {
    setLoading(true);
    try { const res = await familyApi.getReports(20); setReports(res.data); } catch { } finally { setLoading(false); }
  };

  const uploadReport = async () => {
    if (selectedFiles.length === 0) { alert('请选择报告文件'); return; }
    setUploading(true);
    try {
      // 分离 PDF 和图片
      const pdfFiles = selectedFiles.filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
      const imageFiles = selectedFiles.filter(f => !f.type.includes('pdf') && !f.name.endsWith('.pdf'));

      const imageBase64List = imageFiles.length > 0 ? await Promise.all(imageFiles.map(fileToBase64)) : undefined;
      const pdfBase64 = pdfFiles.length > 0 ? await fileToBase64(pdfFiles[0]) : undefined;

      const res = await familyApi.uploadReport({
        report_date: uploadForm.report_date,
        hospital: uploadForm.hospital || undefined,
        title: uploadForm.title || undefined,
        image_base64_list: imageBase64List,
        pdf_base64: pdfBase64,
      });
      setShowUpload(false);
      setSelectedFiles([]);

      // 异步处理模式：轮询状态直到完成
      if (res.data.status === 'processing' && res.data.id) {
        setUploadResult({ ...res.data, ai_summary: 'AI 正在后台提取指标，请稍候...' });
        const reportId = res.data.id;
        const poll = setInterval(async () => {
          try {
            const detail = await familyApi.getReportDetail(reportId);
            if (detail.data.status !== 'processing') {
              clearInterval(poll);
              setUploadResult(detail.data);
              await loadReports();
            }
          } catch { clearInterval(poll); }
        }, 3000); // 每 3 秒轮询
        // 最长轮询 5 分钟
        setTimeout(() => clearInterval(poll), 300000);
      } else {
        setUploadResult(res.data);
        await loadReports();
      }
    } catch (e: any) {
      alert('上传失败: ' + (e.response?.data?.detail || e.message));
    } finally { setUploading(false); }
  };

  const viewTrend = async (name: string) => {
    try {
      const res = await familyApi.getIndicatorTrend(name);
      setTrendData(res.data);
      setTrendName(name);
    } catch (e: any) { alert('查询失败'); }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white border-b px-4 py-3 flex items-center gap-3">
        <button onClick={() => router.push('/family')} className="text-gray-500">←</button>
        <h1 className="font-bold text-lg">📋 体检报告</h1>
      </div>

      <div className="p-4 space-y-3">
        <button onClick={() => setShowUpload(true)} className="w-full bg-blue-500 text-white rounded-xl py-3 text-sm font-medium">
          📸 上传体检报告（AI 提取）
        </button>

        {/* 上传表单 */}
        {showUpload && (
          <div className="bg-white rounded-xl p-4 shadow-sm border space-y-3">
            <input type="date" className="w-full border rounded-lg px-3 py-2 text-sm" value={uploadForm.report_date} onChange={e => setUploadForm({ ...uploadForm, report_date: e.target.value })} />
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="医院名称" value={uploadForm.hospital} onChange={e => setUploadForm({ ...uploadForm, hospital: e.target.value })} />
            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="报告标题" value={uploadForm.title} onChange={e => setUploadForm({ ...uploadForm, title: e.target.value })} />
            <div>
              <button onClick={() => fileRef.current?.click()} className="border border-dashed rounded-lg px-4 py-6 w-full text-gray-400 text-sm hover:border-blue-400">
                {selectedFiles.length > 0 ? `已选 ${selectedFiles.length} 个文件` : '点击选择报告（支持图片和 PDF）'}
              </button>
              <input ref={fileRef} type="file" accept="image/*,.pdf,application/pdf" multiple className="hidden" onChange={e => { if (e.target.files) setSelectedFiles(Array.from(e.target.files)); }} />
            </div>
            <div className="flex gap-2">
              <button onClick={() => { setShowUpload(false); setSelectedFiles([]); }} className="flex-1 border rounded-lg py-2 text-sm">取消</button>
              <button onClick={uploadReport} disabled={uploading} className="flex-1 bg-blue-500 text-white rounded-lg py-2 text-sm disabled:opacity-50">
                {uploading ? 'AI 分析中...' : '上传并分析'}
              </button>
            </div>
          </div>
        )}

        {/* 上传结果 */}
        {uploadResult && (
          <div className="bg-green-50 rounded-xl p-4 border border-green-200">
            <h3 className="font-medium text-green-800 mb-2">AI 提取完成</h3>
            <p className="text-sm">提取 {uploadResult.extracted_count} 项指标，其中 {uploadResult.abnormal_count} 项异常</p>
            {uploadResult.ai_summary && <p className="text-sm mt-2 text-gray-700">{uploadResult.ai_summary}</p>}
            {uploadResult.abnormal_items?.map((item: any, i: number) => (
              <div key={i} className="mt-1 text-sm text-red-600 cursor-pointer hover:underline" onClick={() => viewTrend(item.name)}>
                ⚠️ {item.name}: {item.value}{item.unit || ''} ({item.severity})
              </div>
            ))}
            <button onClick={() => setUploadResult(null)} className="text-xs text-gray-400 mt-2">关闭</button>
          </div>
        )}

        {/* 指标趋势 */}
        {trendData && (
          <div className="bg-white rounded-xl p-4 shadow-sm border">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-medium">📈 {trendName} 趋势</h3>
              <button onClick={() => setTrendData(null)} className="text-xs text-gray-400">关闭</button>
            </div>
            {trendData.data_points?.length > 0 ? (
              <div className="space-y-1">
                {trendData.data_points.map((p: any, i: number) => (
                  <div key={i} className={`flex justify-between text-sm px-2 py-1 rounded ${p.is_abnormal ? 'bg-red-50 text-red-700' : 'bg-gray-50'}`}>
                    <span>{p.date}</span>
                    <span className="font-mono">{p.value} {p.unit || ''}</span>
                    <span className="text-xs">{p.reference_low && p.reference_high ? `(${p.reference_low}-${p.reference_high})` : ''}</span>
                  </div>
                ))}
              </div>
            ) : <p className="text-sm text-gray-400">暂无历史数据</p>}
          </div>
        )}

        {/* 报告列表 */}
        {loading ? (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        ) : reports.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <div className="text-4xl mb-2">📋</div>
            <p>暂无体检报告</p>
          </div>
        ) : (
          reports.map(r => (
            <div key={r.id} className="bg-white rounded-xl p-4 shadow-sm border" onClick={() => router.push(`/family/reports/${r.id}`)}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium">{r.title || `${r.report_date} 体检报告`}</h3>
                  <div className="text-xs text-gray-400 mt-1">
                    {r.report_date} {r.hospital && `· ${r.hospital}`}
                  </div>
                </div>
                <div className="text-right">
                  {r.abnormal_count > 0 ? (
                    <span className="text-xs bg-red-100 text-red-600 px-2 py-1 rounded-full">{r.abnormal_count} 项异常</span>
                  ) : r.status === 'completed' ? (
                    <span className="text-xs bg-green-100 text-green-600 px-2 py-1 rounded-full">正常</span>
                  ) : (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded-full">{r.status}</span>
                  )}
                </div>
              </div>
              {r.ai_summary && <p className="text-xs text-gray-500 mt-2 line-clamp-2">{r.ai_summary}</p>}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => { resolve((reader.result as string).split(',')[1]); };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
