'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '@/services/api/client';
import { compressImage } from '@/utils/imageCompress';

interface BeautyResult {
  success: boolean;
  score: number;
  title: string;
  description: string;
  features: string[];
  tips: string;
  remaining?: number;
  error?: string;
}

interface RecognizeResult {
  success: boolean;
  description: string;
  items: string[];
  remaining?: number;
  error?: string;
}

type Mode = 'beauty' | 'recognize';

const DAILY_LIMIT = 10;

export default function KidsBeautyPage() {
  const [mode, setMode] = useState<Mode>('beauty');
  const [loading, setLoading] = useState(false);
  const [beautyResult, setBeautyResult] = useState<BeautyResult | null>(null);
  const [recognizeResult, setRecognizeResult] = useState<RecognizeResult | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [remaining, setRemaining] = useState(DAILY_LIMIT);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const loadUsage = useCallback(async () => {
    try {
      const res = await api.get('/vision/usage');
      setRemaining(res.data.remaining ?? DAILY_LIMIT);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadUsage();
  }, [loadUsage]);

  const handleImage = async (file: File) => {
    if (remaining <= 0) return;
    setLoading(true);
    setBeautyResult(null);
    setRecognizeResult(null);

    try {
      const compressed = await compressImage(file, 800, 0.8);
      const url = URL.createObjectURL(compressed);
      setPreviewUrl(url);

      const reader = new FileReader();
      reader.readAsDataURL(compressed);
      reader.onloadend = async () => {
        const base64 = (reader.result as string).split(',')[1];
        const imageType = compressed.type.split('/')[1] || 'jpeg';

        try {
          if (mode === 'beauty') {
            const res = await api.post('/vision/beauty', {
              image_base64: base64,
              image_type: imageType,
            });
            setBeautyResult(res.data);
            if (res.data.remaining !== undefined) setRemaining(res.data.remaining);
          } else {
            const res = await api.post('/vision/recognize', {
              image_base64: base64,
              image_type: imageType,
            });
            setRecognizeResult(res.data);
            if (res.data.remaining !== undefined) setRemaining(res.data.remaining);
          }
        } catch {
          if (mode === 'beauty') {
            setBeautyResult({ success: false, score: 0, title: '', description: '', features: [], tips: '', error: '分析失败，请重试' });
          } else {
            setRecognizeResult({ success: false, description: '', items: [], error: '识别失败，请重试' });
          }
        } finally {
          setLoading(false);
        }
      };
    } catch {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleImage(file);
    e.target.value = '';
  };

  const handleReset = () => {
    setBeautyResult(null);
    setRecognizeResult(null);
    setPreviewUrl(null);
  };

  const scoreColor = (score: number) => {
    if (score >= 95) return 'text-pink-500';
    if (score >= 90) return 'text-purple-500';
    return 'text-blue-500';
  };

  const isLimitReached = remaining <= 0;

  return (
    <div className="flex flex-col items-center px-6 py-8 min-h-full overflow-y-auto">
      <h1 className="text-3xl font-bold text-purple-600 mb-2">
        {mode === 'beauty' ? '📸 趣味测颜值' : '🔍 图片识别'}
      </h1>
      <p className="text-lg text-gray-500 mb-2">
        {mode === 'beauty' ? '拍张照片看看你有多可爱~' : '拍照或选图，看看AI怎么说~'}
      </p>

      {/* 剩余次数提示 */}
      <div className={`mb-6 px-5 py-2 rounded-full text-base font-bold ${
        isLimitReached
          ? 'bg-red-100 text-red-500 border-2 border-red-200'
          : remaining <= 3
            ? 'bg-orange-100 text-orange-500 border-2 border-orange-200'
            : 'bg-purple-50 text-purple-500 border-2 border-purple-100'
      }`}>
        {isLimitReached
          ? `🚫 今日 ${DAILY_LIMIT} 次已用完，明天再来~`
          : `✨ 今日剩余 ${remaining}/${DAILY_LIMIT} 次`
        }
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-3 mb-8">
        <button
          onClick={() => { setMode('beauty'); handleReset(); }}
          className={`px-6 py-3 rounded-full font-bold text-base transition-all ${
            mode === 'beauty'
              ? 'bg-gradient-to-r from-pink-400 to-purple-400 text-white shadow-lg'
              : 'bg-white border-2 border-pink-200 text-gray-500'
          }`}
        >
          📸 测颜值
        </button>
        <button
          onClick={() => { setMode('recognize'); handleReset(); }}
          className={`px-6 py-3 rounded-full font-bold text-base transition-all ${
            mode === 'recognize'
              ? 'bg-gradient-to-r from-blue-400 to-cyan-400 text-white shadow-lg'
              : 'bg-white border-2 border-blue-200 text-gray-500'
          }`}
        >
          🔍 识别图片
        </button>
      </div>

      {/* Upload Area - show when no result */}
      {!beautyResult && !recognizeResult && !loading && (
        <div className="flex flex-col items-center gap-5 w-full max-w-sm">
          <button
            onClick={() => cameraInputRef.current?.click()}
            disabled={isLimitReached}
            className={`w-full py-6 rounded-3xl font-bold text-xl shadow-xl transition-all flex items-center justify-center gap-3 ${
              isLimitReached
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-gradient-to-r from-pink-400 to-purple-400 text-white hover:shadow-2xl active:scale-95'
            }`}
          >
            <span className="text-3xl">📷</span>
            拍照
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLimitReached}
            className={`w-full py-6 rounded-3xl font-bold text-xl shadow-lg transition-all flex items-center justify-center gap-3 border-2 ${
              isLimitReached
                ? 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-white border-pink-200 text-gray-600 hover:border-pink-400 active:scale-95'
            }`}
          >
            <span className="text-3xl">🖼️</span>
            从相册选
          </button>

          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={handleFileChange}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center gap-4 mt-4">
          {previewUrl && (
            <div className="w-48 h-48 rounded-3xl overflow-hidden shadow-xl border-4 border-pink-200">
              <img src={previewUrl} alt="preview" className="w-full h-full object-cover" />
            </div>
          )}
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 rounded-full bg-pink-400 animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-5 h-5 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-5 h-5 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <p className="text-xl font-bold text-purple-500">
            {mode === 'beauty' ? 'AI 正在分析你的颜值...' : 'AI 正在识别图片...'}
          </p>
        </div>
      )}

      {/* Beauty Result */}
      {beautyResult && !loading && (
        <div className="flex flex-col items-center gap-4 w-full max-w-md">
          {previewUrl && (
            <div className="w-40 h-40 rounded-full overflow-hidden shadow-xl border-4 border-pink-300">
              <img src={previewUrl} alt="photo" className="w-full h-full object-cover" />
            </div>
          )}

          {beautyResult.success && beautyResult.score > 0 ? (
            <>
              {/* Score */}
              <div className="text-center">
                <div className={`text-7xl font-black ${scoreColor(beautyResult.score)}`}>
                  {beautyResult.score}
                </div>
                <div className="text-sm text-gray-400 -mt-1">颜值分</div>
              </div>

              {/* Title */}
              {beautyResult.title && (
                <div className="px-6 py-2 bg-gradient-to-r from-pink-100 to-purple-100 rounded-full">
                  <span className="text-lg font-bold text-purple-600">{beautyResult.title}</span>
                </div>
              )}

              {/* Description */}
              {beautyResult.description && (
                <p className="text-center text-lg text-gray-600 leading-relaxed px-4">
                  {beautyResult.description}
                </p>
              )}

              {/* Features */}
              {beautyResult.features.length > 0 && (
                <div className="flex flex-wrap gap-2 justify-center">
                  {beautyResult.features.map((f, i) => (
                    <span key={i} className="px-4 py-2 bg-pink-50 border border-pink-200 rounded-full text-base font-medium text-pink-600">
                      {f}
                    </span>
                  ))}
                </div>
              )}

              {/* Tips */}
              {beautyResult.tips && (
                <div className="mt-2 px-5 py-3 bg-yellow-50 border-2 border-yellow-200 rounded-2xl">
                  <p className="text-base text-yellow-700 text-center">{beautyResult.tips}</p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center p-6 bg-pink-50 rounded-3xl border-2 border-pink-200">
              <div className="text-5xl mb-3">😅</div>
              <p className="text-lg text-gray-600">
                {beautyResult.error || '没有检测到人脸哦，换张照片试试~'}
              </p>
            </div>
          )}

          <button
            onClick={handleReset}
            disabled={isLimitReached}
            className={`mt-4 px-8 py-3 rounded-full font-bold text-lg shadow-lg transition-all ${
              isLimitReached
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-gradient-to-r from-pink-400 to-purple-400 text-white active:scale-95'
            }`}
          >
            {isLimitReached ? '今日次数已用完' : '再来一次'}
          </button>
        </div>
      )}

      {/* Recognition Result */}
      {recognizeResult && !loading && (
        <div className="flex flex-col items-center gap-4 w-full max-w-md">
          {previewUrl && (
            <div className="w-56 h-56 rounded-3xl overflow-hidden shadow-xl border-4 border-blue-200">
              <img src={previewUrl} alt="photo" className="w-full h-full object-cover" />
            </div>
          )}

          {recognizeResult.success ? (
            <>
              {recognizeResult.description && (
                <div className="w-full p-5 bg-blue-50 border-2 border-blue-200 rounded-3xl">
                  <p className="text-lg text-gray-700 leading-relaxed">{recognizeResult.description}</p>
                </div>
              )}

              {recognizeResult.items.length > 0 && (
                <div className="w-full">
                  <h3 className="text-base font-bold text-gray-500 mb-2 px-1">识别到的内容：</h3>
                  <div className="flex flex-wrap gap-2">
                    {recognizeResult.items.map((item, i) => (
                      <span key={i} className="px-4 py-2 bg-white border-2 border-blue-200 rounded-full text-base font-medium text-blue-600">
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center p-6 bg-blue-50 rounded-3xl border-2 border-blue-200">
              <div className="text-5xl mb-3">🤔</div>
              <p className="text-lg text-gray-600">
                {recognizeResult.error || '识别失败，请重试'}
              </p>
            </div>
          )}

          <button
            onClick={handleReset}
            disabled={isLimitReached}
            className={`mt-4 px-8 py-3 rounded-full font-bold text-lg shadow-lg transition-all ${
              isLimitReached
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-gradient-to-r from-blue-400 to-cyan-400 text-white active:scale-95'
            }`}
          >
            {isLimitReached ? '今日次数已用完' : '再来一次'}
          </button>
        </div>
      )}
    </div>
  );
}
