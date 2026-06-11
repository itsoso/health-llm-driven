'use client';

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, Pill, Check, X, Loader2, FileImage, Info } from 'lucide-react';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  recognizePrescription,
  getOriginatorRecommendations,
  setRecommendationStatus,
  RecognizeResponse,
  OriginatorRecommendation,
} from '@/services/api/prescriptions';

const DISCLAIMER =
  '原研药信息仅供参考,是否换药请以药师 / 医生意见为准。';

function PrescriptionsContent() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<RecognizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recognizeMutation = useMutation({
    mutationFn: (file: File) => recognizePrescription(file),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: any) => {
      setError(err?.response?.data?.detail || '识别失败,请换一张更清晰的处方图片再试。');
      setResult(null);
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    recognizeMutation.mutate(file);
  };

  const {
    data: recommendationsData,
    isLoading: recsLoading,
    isError: recsError,
  } = useQuery({
    queryKey: ['originator-recommendations'],
    queryFn: getOriginatorRecommendations,
  });

  const statusMutation = useMutation({
    mutationFn: (payload: {
      generic_name: string;
      status: 'adopted' | 'dismissed';
      brand?: string;
      manufacturer?: string;
    }) => setRecommendationStatus(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['originator-recommendations'] });
    },
  });

  const recommendations: OriginatorRecommendation[] =
    recommendationsData?.recommendations ?? [];

  return (
    <main className="min-h-screen bg-gradient-to-br from-sky-50 via-white to-rose-50 pt-4 pb-12 px-4 sm:px-8">
      <div className="max-w-3xl mx-auto">
        {/* 标题 */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <Pill className="w-6 h-6 text-indigo-600" />
            处方查原研药
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            上传处方图片,识别在用药并匹配对应原研药。{DISCLAIMER}
          </p>
        </div>

        {/* 上传区 */}
        <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 mb-8">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={recognizeMutation.isPending}
            className="w-full border-2 border-dashed border-gray-200 rounded-xl py-8 flex flex-col items-center justify-center gap-2 text-gray-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors disabled:opacity-60"
          >
            {recognizeMutation.isPending ? (
              <>
                <Loader2 className="w-7 h-7 animate-spin" />
                <span className="text-sm">识别中…</span>
              </>
            ) : (
              <>
                <Upload className="w-7 h-7" />
                <span className="text-sm font-medium">点击上传处方图片</span>
                <span className="text-xs text-gray-400">支持 JPG / PNG,识别处方上的药品</span>
              </>
            )}
          </button>

          {preview && (
            <div className="mt-4 flex items-center gap-3 text-sm text-gray-500">
              <FileImage className="w-4 h-4 flex-shrink-0" />
              {/* eslint-disable-next-line @next/next/no-img-element -- 本地 blob 预览,无需 next/image 优化 */}
              <img
                src={preview}
                alt="处方预览"
                className="h-16 w-16 object-cover rounded-lg border border-gray-200"
              />
              <span>已选择处方图片</span>
            </div>
          )}

          {error && (
            <p className="mt-4 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
          )}
        </section>

        {/* 识别结果 */}
        {result && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-800">识别结果</h2>
              <span className="text-xs text-gray-400">
                共 {result.items.length} 种药品 · 匹配到原研 {result.matched_originators} 种
              </span>
            </div>

            {result.note && (
              <p className="text-xs text-gray-500 mb-3 flex items-start gap-1.5">
                <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                {result.note}
              </p>
            )}

            <div className="space-y-3">
              {result.items.map((item, idx) => (
                <div
                  key={`${item.raw_name}-${idx}`}
                  className="bg-white rounded-xl border border-gray-100 shadow-sm p-4"
                >
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <span className="font-semibold text-gray-800">{item.raw_name}</span>
                    {item.generic_name && (
                      <span className="text-sm text-gray-500">通用名:{item.generic_name}</span>
                    )}
                  </div>
                  {(item.dosage || item.frequency) && (
                    <p className="text-xs text-gray-400 mt-0.5">
                      {[item.dosage, item.frequency].filter(Boolean).join(' · ')}
                    </p>
                  )}

                  <div className="mt-3 pt-3 border-t border-gray-50">
                    {item.has_originator && item.originator ? (
                      <div className="flex items-start gap-2">
                        <Pill className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                        <div className="text-sm">
                          <span className="font-medium text-gray-800">
                            原研药:{item.originator.brand}
                          </span>
                          <span className="text-gray-500 ml-1">
                            ({item.originator.manufacturer})
                          </span>
                        </div>
                      </div>
                    ) : (
                      <span className="text-sm text-gray-400">暂无原研数据</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-4 text-xs text-gray-400">{DISCLAIMER}</p>
          </section>
        )}

        {/* 原研药建议 */}
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-1">原研药建议</h2>
          <p className="text-xs text-gray-400 mb-4">
            根据你的在用药,以下可考虑换用原研药。{DISCLAIMER}
          </p>

          {recsLoading ? (
            <div className="flex items-center gap-2 text-sm text-gray-400 py-6 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> 加载中…
            </div>
          ) : recsError ? (
            <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
              建议加载失败,请稍后重试。
            </p>
          ) : recommendations.length === 0 ? (
            <p className="text-sm text-gray-400 bg-gray-50 rounded-xl px-4 py-6 text-center">
              暂无原研药建议。
            </p>
          ) : (
            <div className="space-y-3">
              {recommendations.map((rec) => {
                const pending =
                  statusMutation.isPending &&
                  statusMutation.variables?.generic_name === rec.generic_name;
                return (
                  <div
                    key={rec.generic_key}
                    className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-800 truncate">
                        {rec.med_name}
                        <span className="text-sm font-normal text-gray-500 ml-2">
                          通用名:{rec.generic_name}
                        </span>
                      </p>
                      <p className="text-sm text-gray-500 mt-0.5">
                        建议原研:{rec.brand}
                        <span className="text-gray-400 ml-1">({rec.manufacturer})</span>
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={() =>
                          statusMutation.mutate({
                            generic_name: rec.generic_name,
                            status: 'adopted',
                            brand: rec.brand,
                            manufacturer: rec.manufacturer,
                          })
                        }
                        disabled={pending}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-60"
                      >
                        {pending ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Check className="w-4 h-4" />
                        )}
                        采纳
                      </button>
                      <button
                        onClick={() =>
                          statusMutation.mutate({
                            generic_name: rec.generic_name,
                            status: 'dismissed',
                          })
                        }
                        disabled={pending}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-500 border border-gray-200 hover:bg-gray-50 transition-colors disabled:opacity-60"
                      >
                        <X className="w-4 h-4" />
                        不需要
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

export default function PrescriptionsPage() {
  return (
    <ProtectedRoute>
      <PrescriptionsContent />
    </ProtectedRoute>
  );
}
