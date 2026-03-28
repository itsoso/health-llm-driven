'use client';

import { useState, useEffect } from 'react';

const API_BASE = '/api';

interface UserApiKey {
  id: number;
  name: string;
  api_key: string | null;
  scopes: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface ApiKeySectionProps {
  token: string | null;
  setMessage: (msg: { type: 'success' | 'error'; text: string } | null) => void;
}

export default function ApiKeySection({ token, setMessage }: ApiKeySectionProps) {
  const [apiKeys, setApiKeys] = useState<UserApiKey[]>([]);
  const [showApiKeySection, setShowApiKeySection] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);

  const loadApiKeys = async () => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/user-api-keys`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        setApiKeys(await res.json());
      }
    } catch (error) {
      console.error('获取 API Keys 失败:', error);
    }
  };

  const handleCreateApiKey = async () => {
    if (!token || !newKeyName.trim()) {
      setMessage({ type: 'error', text: 'API Key 名称不能为空' });
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/user-api-keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ name: newKeyName.trim() }),
      });

      if (res.ok) {
        const newKey = await res.json();
        if (newKey.api_key) {
          setNewlyCreatedKey(newKey.api_key);
          try {
            await navigator.clipboard.writeText(newKey.api_key);
            setMessage({ type: 'success', text: 'API Key 已创建并复制到剪贴板！请妥善保存，此密钥只显示一次。' });
          } catch {
            setMessage({ type: 'success', text: 'API Key 已创建！请复制保存，此密钥只显示一次。' });
          }
        } else {
          setMessage({ type: 'error', text: '创建成功但未返回密钥，请联系管理员' });
        }
        setNewKeyName('');
        loadApiKeys();
      } else {
        let errorMessage = '创建失败';
        try {
          const error = await res.json();
          errorMessage = error.detail || errorMessage;
        } catch {
          errorMessage = `创建失败 (HTTP ${res.status})`;
        }
        setMessage({ type: 'error', text: errorMessage });
      }
    } catch (error: any) {
      console.error('创建 API Key 失败:', error);
      setMessage({ type: 'error', text: error.message || '网络错误，请检查连接' });
    }
  };

  const handleDeleteApiKey = async (keyId: number, keyName: string) => {
    if (!confirm(`确定要删除 API Key "${keyName}" 吗？删除后使用此 Key 的外部系统将无法访问您的数据。`)) {
      return;
    }
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/user-api-keys/${keyId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setMessage({ type: 'success', text: 'API Key 已删除' });
        loadApiKeys();
      } else {
        setMessage({ type: 'error', text: '删除失败' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: '删除失败' });
    }
  };

  // 展开 API Key 部分时加载数据
  useEffect(() => {
    if (showApiKeySection && token) {
      loadApiKeys();
    }
  }, [showApiKeySection, token]);

  return (
    <div className="bg-white rounded-xl shadow-md p-6 mb-6 border border-gray-200">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setShowApiKeySection(!showApiKeySection)}
      >
        <div className="flex items-center gap-3">
          <span className="text-3xl">{'\u{1F511}'}</span>
          <div>
            <h2 className="text-xl font-bold text-gray-900">开发者接口</h2>
            <p className="text-sm text-gray-600">允许外部 AI 系统访问您的健康数据</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {apiKeys.length > 0 && (
            <span className="px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm">
              {apiKeys.length} 个 Key
            </span>
          )}
          <span className="text-gray-400 text-2xl">
            {showApiKeySection ? '\u{25BC}' : '\u{203A}'}
          </span>
        </div>
      </div>

      {showApiKeySection && (
        <div className="mt-6 space-y-6">
          {/* 说明 */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
            <p className="font-semibold mb-2">{'\u{1F4A1}'} 什么是 API Key？</p>
            <p>API Key 允许外部 AI 健康助手（如 Browser-LLM-Driven、GPT Health 等）访问您的健康数据并提供个性化建议。这些建议会显示在「外部健康建议」页面。</p>
          </div>

          {/* API Key 列表 */}
          {apiKeys.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-800">已创建的 API Key</h3>
                <span className="text-sm text-gray-500">{apiKeys.length} / 10</span>
              </div>
              {apiKeys.map((key) => (
                <div key={key.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                  <div>
                    <p className="font-medium text-gray-900">{key.name}</p>
                    <p className="text-xs text-gray-500">
                      {key.scopes} · {key.last_used_at ? `最后使用: ${new Date(key.last_used_at).toLocaleDateString()}` : '从未使用'}
                    </p>
                  </div>
                  <button
                    onClick={() => handleDeleteApiKey(key.id, key.name)}
                    className="px-3 py-1 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 text-sm"
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 新创建的 Key 展示 */}
          {newlyCreatedKey && (
            <div className="bg-green-50 border-2 border-green-400 rounded-lg p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{'\u{1F511}'}</span>
                <h3 className="font-bold text-green-800">API Key 创建成功！</h3>
              </div>
              <p className="text-sm text-green-700">请立即复制并妥善保存此密钥，它只会显示这一次：</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 p-3 bg-white border border-green-300 rounded-lg font-mono text-sm text-gray-900 break-all select-all">
                  {newlyCreatedKey}
                </code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(newlyCreatedKey);
                    setMessage({ type: 'success', text: '已复制到剪贴板' });
                  }}
                  className="px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium whitespace-nowrap"
                >
                  复制
                </button>
              </div>
              <button
                onClick={() => setNewlyCreatedKey(null)}
                className="w-full px-4 py-2 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 text-sm"
              >
                我已保存，关闭此提示
              </button>
            </div>
          )}

          {/* 创建新 Key */}
          <div className="space-y-3">
            <h3 className="font-semibold text-gray-800">创建新的 API Key</h3>
            {apiKeys.length >= 10 ? (
              <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-800">
                <p className="font-semibold">⚠️ 已达到最大限制</p>
                <p className="mt-1">您已创建 10 个 API Key，这是允许的最大数量。请删除不需要的 Key 后再创建新的。</p>
              </div>
            ) : (
              <div className="flex gap-3">
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="输入名称（如：Browser-LLM-Driven）"
                  className="flex-1 p-3 border border-gray-300 rounded-lg text-gray-900 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <button
                  onClick={handleCreateApiKey}
                  disabled={!newKeyName.trim()}
                  className="px-6 py-3 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-lg hover:from-indigo-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-semibold whitespace-nowrap"
                >
                  + 创建
                </button>
              </div>
            )}
          </div>

          {/* 使用说明 */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 text-sm text-gray-700 space-y-4">
            <div>
              <p className="font-semibold mb-2">{'\u{1F4DD}'} 使用方法：</p>
              <ol className="list-decimal list-inside space-y-1">
                <li>创建 API Key 后，复制并保存（Key 只显示一次）</li>
                <li>在外部 AI 系统中配置此 API Key</li>
                <li>外部系统将通过 <code className="bg-gray-200 px-1 rounded">X-API-Key</code> 头部访问您的数据</li>
                <li>外部系统写入的健康建议将显示在「外部健康建议」页面</li>
              </ol>
            </div>

            <div>
              <p className="font-semibold mb-2">{'\u{1F517}'} API 端点：</p>
              <div className="space-y-2 font-mono text-xs">
                <div className="bg-white p-2 rounded border">
                  <span className="text-green-600 font-bold">GET</span>
                  <span className="ml-2 text-gray-800">https://health.executor.life/api/v1/external/health-data</span>
                  <p className="text-gray-500 mt-1 font-sans">获取健康数据（支持 ?date=2024-01-25 或 ?start_date=...&end_date=...）</p>
                </div>
                <div className="bg-white p-2 rounded border">
                  <span className="text-blue-600 font-bold">POST</span>
                  <span className="ml-2 text-gray-800">https://health.executor.life/api/v1/external/recommendations</span>
                  <p className="text-gray-500 mt-1 font-sans">写入健康建议（JSON Body）</p>
                </div>
              </div>
            </div>

            <div>
              <p className="font-semibold mb-2">{'\u{1F4E6}'} GET 请求示例（读取健康数据）：</p>
              <pre className="bg-gray-800 text-green-400 p-3 rounded-lg text-xs overflow-x-auto">
{`curl -X GET "https://health.executor.life/api/v1/external/health-data?date=2024-01-25" \\
  -H "X-API-Key: 你的API密钥"`}
              </pre>
            </div>

            <div>
              <p className="font-semibold mb-2">{'\u{1F4E4}'} POST 请求示例（写入健康建议）：</p>
              <pre className="bg-gray-800 text-green-400 p-3 rounded-lg text-xs overflow-x-auto whitespace-pre-wrap">
{`curl -X POST "https://health.executor.life/api/v1/external/recommendations" \\
  -H "X-API-Key: 你的API密钥" \\
  -H "Content-Type: application/json" \\
  -d '{
    "category": "exercise",
    "title": "今日运动建议",
    "content": "根据睡眠数据，建议进行30分钟有氧运动",
    "source_name": "我的AI助手",
    "recommendation_date": "2024-01-25"
  }'`}
              </pre>
              <div className="mt-2 text-xs text-gray-600">
                <p className="font-semibold">POST 请求字段说明：</p>
                <ul className="mt-1 space-y-1 list-disc list-inside">
                  <li><code className="bg-gray-200 px-1 rounded">category</code>: 建议类别 - <code className="text-blue-600">exercise</code>(运动) / <code className="text-blue-600">diet</code>(饮食) / <code className="text-blue-600">sleep</code>(睡眠) / <code className="text-blue-600">supplement</code>(补剂) / <code className="text-blue-600">general</code>(综合)</li>
                  <li><code className="bg-gray-200 px-1 rounded">title</code>: 建议标题</li>
                  <li><code className="bg-gray-200 px-1 rounded">content</code>: 建议内容（支持 Markdown 格式）</li>
                  <li><code className="bg-gray-200 px-1 rounded">source_name</code>: 来源名称（如 &quot;GPT Health&quot;）</li>
                  <li><code className="bg-gray-200 px-1 rounded">recommendation_date</code>: 建议日期（可选，默认今天）</li>
                </ul>
              </div>
            </div>
          </div>

          {/* 跳转外部建议页面 */}
          <a
            href="/external-advice"
            className="block w-full text-center px-4 py-3 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 font-medium"
          >
            {'\u{1F4E1}'} 查看外部健康建议 {'\u{2192}'}
          </a>
        </div>
      )}
    </div>
  );
}
