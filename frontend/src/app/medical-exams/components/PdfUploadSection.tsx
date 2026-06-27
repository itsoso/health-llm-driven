'use client';

import React from 'react';
import { UseMutationResult } from '@tanstack/react-query';
import { abnormalStyles, abnormalLabels, examTypeLabels } from './types';


interface PdfUploadSectionProps {
  pdfFile: File | null;
  pdfPreview: any;
  textImportValue: string;
  uploadProgress: string;
  previewPdfMutation: UseMutationResult<any, any, File, unknown>;
  uploadPdfMutation: UseMutationResult<any, any, File, unknown>;
  uploadTextMutation: UseMutationResult<any, any, string, unknown>;
  onPdfSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onPdfImport: () => void;
  onTextChange: (text: string) => void;
  onTextImport: () => void;
  onReset: () => void;
}

export function PdfUploadSection({
  pdfFile,
  pdfPreview,
  textImportValue,
  uploadProgress,
  previewPdfMutation,
  uploadPdfMutation,
  uploadTextMutation,
  onPdfSelect,
  onPdfImport,
  onTextChange,
  onTextImport,
  onReset,
}: PdfUploadSectionProps) {
  const fileName = pdfFile?.name.toLowerCase() ?? '';
  const isPdfFile = !!pdfFile && (pdfFile.type === 'application/pdf' || fileName.endsWith('.pdf'));
  const canImportFile = !!pdfFile && (!isPdfFile || !!pdfPreview);

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-6 border border-purple-200">
      <h3 className="text-xl font-bold text-gray-900 mb-4">📄 导入体检报告</h3>
      <p className="text-gray-600 text-sm mb-4">
        上传体检报告 PDF、化验单图片，或粘贴文字结果。解析后会写入体检记录，使用前请复核 OCR/AI 提取值。
      </p>

      {/* 文件选择 */}
      <div className="border-2 border-dashed border-purple-300 rounded-lg p-8 text-center mb-4 hover:border-purple-500 transition-colors">
        <input
          type="file"
          accept=".pdf,image/jpeg,image/png,image/heic,image/webp"
          onChange={onPdfSelect}
          className="hidden"
          id="pdf-upload"
        />
        <label htmlFor="pdf-upload" className="cursor-pointer">
          <div className="text-5xl mb-3">📁</div>
          <p className="text-gray-700 font-medium mb-2">
            {pdfFile ? pdfFile.name : '点击选择 PDF 或图片'}
          </p>
          <p className="text-gray-500 text-sm">支持 .pdf / .jpg / .png / .heic / .webp</p>
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

      {pdfFile && !isPdfFile && (
        <div className="mb-4 p-3 bg-amber-50 rounded-lg border border-amber-200 text-amber-900 text-sm">
          图片会直接进入 OCR 导入流程。导入后请在体检记录里复核项目名、数值、单位和参考范围。
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
            onClick={onPdfImport}
            disabled={uploadPdfMutation.isPending}
            className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 disabled:opacity-50 shadow-md"
          >
            {uploadPdfMutation.isPending ? '导入中...' : '✓ 确认导入'}
          </button>
          <button
            onClick={onReset}
            className="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300"
          >
            重新选择
          </button>
        </div>
      )}

      {canImportFile && !pdfPreview && (
        <div className="flex gap-3">
          <button
            onClick={onPdfImport}
            disabled={uploadPdfMutation.isPending}
            className="flex-1 py-3 bg-gradient-to-r from-purple-500 to-pink-600 text-white font-semibold rounded-lg hover:from-purple-600 hover:to-pink-700 disabled:opacity-50 shadow-md"
          >
            {uploadPdfMutation.isPending ? '导入中...' : '确认导入图片'}
          </button>
          <button
            onClick={onReset}
            className="px-6 py-3 bg-gray-200 text-gray-700 font-semibold rounded-lg hover:bg-gray-300"
          >
            重新选择
          </button>
        </div>
      )}

      <div className="mt-6 border-t border-gray-100 pt-5">
        <h4 className="font-bold text-gray-800 mb-2">文字兜底</h4>
        <p className="text-gray-600 text-sm mb-3">
          OCR 失败或只有复制文本时，把指标、数值、单位和参考范围粘贴在这里。
        </p>
        <textarea
          value={textImportValue}
          onChange={(e) => onTextChange(e.target.value)}
          rows={5}
          maxLength={4000}
          className="w-full rounded-lg border border-gray-200 p-3 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-purple-200"
          placeholder={'例如:\nLDL 3.8 mmol/L 参考 <3.4\nALT 42 U/L 参考 9-50\n血压 130/85 mmHg'}
        />
        <div className="mt-3 flex justify-end">
          <button
            onClick={onTextImport}
            disabled={uploadTextMutation.isPending || !textImportValue.trim()}
            className="px-5 py-2 bg-gray-900 text-white font-semibold rounded-lg hover:bg-gray-800 disabled:opacity-50"
          >
            {uploadTextMutation.isPending ? '导入中...' : '导入文字'}
          </button>
        </div>
      </div>
    </div>
  );
}
