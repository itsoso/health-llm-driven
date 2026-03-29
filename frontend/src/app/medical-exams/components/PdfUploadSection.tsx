'use client';

import React from 'react';
import { UseMutationResult } from '@tanstack/react-query';
import { abnormalStyles, abnormalLabels, examTypeLabels } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */

interface PdfUploadSectionProps {
  pdfFile: File | null;
  pdfPreview: any;
  uploadProgress: string;
  previewPdfMutation: UseMutationResult<any, any, File, unknown>;
  uploadPdfMutation: UseMutationResult<any, any, File, unknown>;
  onPdfSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onPdfImport: () => void;
  onReset: () => void;
}

export function PdfUploadSection({
  pdfFile,
  pdfPreview,
  uploadProgress,
  previewPdfMutation,
  uploadPdfMutation,
  onPdfSelect,
  onPdfImport,
  onReset,
}: PdfUploadSectionProps) {
  return (
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
          onChange={onPdfSelect}
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
    </div>
  );
}
