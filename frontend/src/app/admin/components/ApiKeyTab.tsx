'use client';

interface NewsApiKey {
  id: number;
  name: string;
  api_key: string | null;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

interface ApiKeyTabProps {
  apiKeys: NewsApiKey[];
  apiKeysLoading: boolean;
  showCreateApiKey: boolean;
  setShowCreateApiKey: (v: boolean) => void;
  newApiKeyName: string;
  setNewApiKeyName: (v: string) => void;
  newApiKey: string | null;
  setNewApiKey: (v: string | null) => void;
  handleCreateApiKey: () => void;
  handleDeleteApiKey: (keyId: number) => void;
  copyToClipboard: (text: string) => void;
  formatDate: (dateStr: string | null) => string;
}

export default function ApiKeyTab({
  apiKeys,
  apiKeysLoading,
  newApiKeyName,
  setNewApiKeyName,
  newApiKey,
  setNewApiKey,
  handleCreateApiKey,
  handleDeleteApiKey,
  copyToClipboard,
  formatDate,
}: ApiKeyTabProps) {
  return (
    <div className="space-y-6">
      {/* Create API Key */}
      <div className="bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
        <h2 className="text-xl font-bold text-white mb-4">🔑 创建 API Key</h2>
        <p className="text-purple-200 text-sm mb-4">
          API Key 用于外部系统（如 browser-llm-orchestrator）向资讯系统写入内容。
        </p>
        <div className="flex gap-4">
          <input
            type="text"
            value={newApiKeyName}
            onChange={(e) => setNewApiKeyName(e.target.value)}
            placeholder="输入 API Key 名称，如：browser-llm-orchestrator"
            className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-purple-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          <button
            onClick={handleCreateApiKey}
            className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
          >
            创建
          </button>
        </div>

        {/* New API Key Display */}
        {newApiKey && (
          <div className="mt-4 p-4 bg-green-500/20 border border-green-500/30 rounded-lg">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-green-400 font-medium mb-1">API Key 创建成功！</p>
                <p className="text-green-200 text-xs mb-2">请立即复制保存，此密钥只显示一次。</p>
                <code className="block p-2 bg-black/30 rounded text-green-300 font-mono text-sm break-all">
                  {newApiKey}
                </code>
              </div>
              <button
                onClick={() => {
                  copyToClipboard(newApiKey);
                  setNewApiKey(null);
                }}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors ml-4"
              >
                复制并关闭
              </button>
            </div>
          </div>
        )}
      </div>

      {/* API Key List */}
      <div className="bg-white/10 backdrop-blur-lg rounded-xl border border-white/20 overflow-hidden">
        <div className="p-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-white">📋 API Key 列表</h2>
        </div>

        {apiKeysLoading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-400 mx-auto"></div>
          </div>
        ) : apiKeys.length === 0 ? (
          <div className="p-8 text-center text-purple-200">
            <p>暂无 API Key</p>
            <p className="text-sm text-gray-400 mt-2">点击上方按钮创建一个新的 API Key</p>
          </div>
        ) : (
          <div className="divide-y divide-white/10">
            {apiKeys.map((key) => (
              <div key={key.id} className="p-4 hover:bg-white/5 transition-colors">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <span className="text-white font-medium">{key.name}</span>
                      <span className={`px-2 py-1 rounded text-xs ${
                        key.is_active
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}>
                        {key.is_active ? '有效' : '已禁用'}
                      </span>
                    </div>
                    <div className="text-gray-400 text-sm mt-1">
                      创建于 {formatDate(key.created_at)}
                      {key.last_used_at && ` · 最后使用: ${formatDate(key.last_used_at)}`}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteApiKey(key.id)}
                    className="px-3 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors text-sm"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Usage Instructions */}
      <div className="bg-white/5 backdrop-blur rounded-xl p-4 border border-white/10">
        <h3 className="text-purple-200 font-medium mb-2">📚 使用说明</h3>
        <div className="text-gray-400 text-sm space-y-2">
          <p>在请求头中添加 <code className="px-1 py-0.5 bg-white/10 rounded text-purple-300">X-API-Key</code> 字段：</p>
          <code className="block p-2 bg-black/30 rounded text-green-300 font-mono text-xs">
            curl -X POST /api/news/external/articles -H &quot;X-API-Key: your-api-key&quot; -d &apos;...&apos;
          </code>
        </div>
      </div>
    </div>
  );
}
