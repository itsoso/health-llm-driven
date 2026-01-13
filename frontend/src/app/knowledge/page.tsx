'use client';

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

interface KnowledgeStats {
  available: boolean;
  total_documents: number;
  collection_name: string;
  persist_directory: string;
  embedding_model: string;
  error?: string;
}

interface SearchResult {
  content: string;
  metadata: {
    title?: string;
    category?: string;
    source?: string;
  };
  relevance_score: number;
}

interface RAGResponse {
  success: boolean;
  answer?: string;
  key_points?: string[];
  action_items?: string[];
  knowledge_used?: boolean;
  confidence?: string;
  disclaimer?: string;
  sources?: Array<{
    title: string;
    category: string;
    relevance: number;
  }>;
  error?: string;
}

function KnowledgeManagement() {
  const { user, token } = useAuth();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 状态
  const [activeTab, setActiveTab] = useState<'stats' | 'upload' | 'search' | 'ask'>('stats');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [askQuestion, setAskQuestion] = useState('');
  const [askResponse, setAskResponse] = useState<RAGResponse | null>(null);
  const [textInput, setTextInput] = useState('');
  const [textTitle, setTextTitle] = useState('');
  const [textCategory, setTextCategory] = useState('general');
  const [textSource, setTextSource] = useState('manual_input');
  const [uploadSource, setUploadSource] = useState('');
  const [uploadCategory, setUploadCategory] = useState('general');

  // 获取知识库统计
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery<KnowledgeStats>({
    queryKey: ['knowledgeStats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/v1/knowledge/stats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: !!token,
  });

  // 初始化基础知识
  const initBasicsMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/v1/knowledge/init/health-basics`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('初始化失败');
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeStats'] });
      alert('基础健康知识已初始化！');
    },
    onError: (error: any) => {
      alert(`初始化失败: ${error.message}`);
    },
  });

  // 添加文本
  const addTextMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/v1/knowledge/documents/text`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          text: textInput,
          title: textTitle,
          category: textCategory,
          source: textSource,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '添加失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeStats'] });
      alert(`成功添加 ${data.added_count} 个文档块！`);
      setTextInput('');
      setTextTitle('');
    },
    onError: (error: any) => {
      alert(`添加失败: ${error.message}`);
    },
  });

  // 上传文件
  const uploadFileMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('source', uploadSource || file.name);
      formData.append('category', uploadCategory);

      const res = await fetch(`${API_BASE}/v1/knowledge/documents/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '上传失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeStats'] });
      alert(`成功上传 ${data.filename}，添加了 ${data.added_count} 个文档块！`);
      if (fileInputRef.current) fileInputRef.current.value = '';
      setUploadSource('');
    },
    onError: (error: any) => {
      alert(`上传失败: ${error.message}`);
    },
  });

  // 搜索
  const searchMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/v1/knowledge/search`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: searchQuery,
          n_results: 10,
        }),
      });
      if (!res.ok) throw new Error('搜索失败');
      return res.json();
    },
    onSuccess: (data) => {
      setSearchResults(data.results || []);
    },
    onError: (error: any) => {
      alert(`搜索失败: ${error.message}`);
    },
  });

  // RAG 问答
  const askMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/v1/knowledge/ask`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: askQuestion,
          include_health_data: true,
        }),
      });
      if (!res.ok) throw new Error('问答失败');
      return res.json();
    },
    onSuccess: (data) => {
      setAskResponse(data);
    },
    onError: (error: any) => {
      alert(`问答失败: ${error.message}`);
      setAskResponse({ success: false, error: error.message });
    },
  });

  // 清空知识库
  const clearAllMutation = useMutation({
    mutationFn: async () => {
      if (!confirm('确定要清空整个知识库吗？此操作不可恢复！')) {
        throw new Error('已取消');
      }
      const res = await fetch(`${API_BASE}/v1/knowledge/documents/all?confirm=true`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '清空失败');
      }
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeStats'] });
      alert('知识库已清空！');
    },
    onError: (error: any) => {
      if (error.message !== '已取消') {
        alert(`清空失败: ${error.message}`);
      }
    },
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      uploadFileMutation.mutate(file);
    }
  };

  // 分类选项
  const categories = [
    { value: 'general', label: '通用' },
    { value: 'sleep', label: '睡眠' },
    { value: 'exercise', label: '运动' },
    { value: 'nutrition', label: '营养' },
    { value: 'mental_health', label: '心理健康' },
    { value: 'chronic_disease', label: '慢性病' },
    { value: 'children_health', label: '儿童健康' },
    { value: 'heart_health', label: '心血管' },
    { value: 'weight_management', label: '体重管理' },
  ];

  // 检查是否是管理员
  if (!user?.is_admin) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 text-center">
            <span className="text-4xl mb-4 block">🔒</span>
            <h2 className="text-xl font-bold text-yellow-800 mb-2">权限不足</h2>
            <p className="text-yellow-700">知识库管理功能仅对管理员开放</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-4 md:p-8">
      <div className="max-w-6xl mx-auto">
        {/* 标题 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
            📚 知识库管理
          </h1>
          <p className="text-gray-600 mt-2">管理健康知识库，为 AI 建议提供专业内容支持</p>
        </div>

        {/* 标签页 */}
        <div className="flex flex-wrap gap-2 mb-6">
          {[
            { key: 'stats', label: '📊 统计概览', icon: '📊' },
            { key: 'upload', label: '📤 上传内容', icon: '📤' },
            { key: 'search', label: '🔍 搜索测试', icon: '🔍' },
            { key: 'ask', label: '💬 问答测试', icon: '💬' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`px-4 py-2 rounded-lg font-medium transition-all ${
                activeTab === tab.key
                  ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg'
                  : 'bg-white text-gray-700 hover:bg-gray-50 border border-gray-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 统计概览 */}
        {activeTab === 'stats' && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4">知识库状态</h2>
              
              {statsLoading ? (
                <div className="text-center py-8">
                  <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto"></div>
                  <p className="text-gray-500 mt-2">加载中...</p>
                </div>
              ) : stats?.available ? (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-xl p-4">
                    <div className="text-3xl font-bold text-indigo-600">{stats.total_documents}</div>
                    <div className="text-sm text-indigo-700">文档总数</div>
                  </div>
                  <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-4">
                    <div className="text-lg font-semibold text-purple-600 truncate">{stats.collection_name}</div>
                    <div className="text-sm text-purple-700">集合名称</div>
                  </div>
                  <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-4">
                    <div className="text-lg font-semibold text-blue-600 truncate">{stats.embedding_model}</div>
                    <div className="text-sm text-blue-700">嵌入模型</div>
                  </div>
                </div>
              ) : (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                  知识库服务不可用: {stats?.error || '未知错误'}
                </div>
              )}

              <div className="flex flex-wrap gap-3 mt-6">
                <button
                  onClick={() => initBasicsMutation.mutate()}
                  disabled={initBasicsMutation.isPending}
                  className="px-4 py-2 bg-gradient-to-r from-green-500 to-emerald-500 text-white rounded-lg font-medium hover:from-green-600 hover:to-emerald-600 disabled:opacity-50 transition-all"
                >
                  {initBasicsMutation.isPending ? '初始化中...' : '🌱 初始化基础健康知识'}
                </button>
                <button
                  onClick={() => refetchStats()}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-all"
                >
                  🔄 刷新统计
                </button>
                <button
                  onClick={() => clearAllMutation.mutate()}
                  disabled={clearAllMutation.isPending}
                  className="px-4 py-2 bg-red-100 text-red-700 rounded-lg font-medium hover:bg-red-200 disabled:opacity-50 transition-all"
                >
                  {clearAllMutation.isPending ? '清空中...' : '🗑️ 清空知识库'}
                </button>
              </div>
            </div>

            {/* 预置知识说明 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4">预置健康知识</h2>
              <p className="text-gray-600 mb-4">点击"初始化基础健康知识"将导入以下内容：</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  '😴 睡眠的重要性',
                  '🏃 有氧运动指南',
                  '❤️ 静息心率与健康',
                  '📊 心率变异性(HRV)解读',
                  '🧘 压力管理与身体电量',
                  '👃 慢性鼻炎的日常管理',
                  '💧 健康饮水指南',
                  '🚶 步数与健康',
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 上传内容 */}
        {activeTab === 'upload' && (
          <div className="space-y-6">
            {/* 上传文件 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4">📁 上传文件</h2>
              <p className="text-gray-600 mb-4">支持 .txt, .md, .json 格式</p>
              
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">来源标识</label>
                    <input
                      type="text"
                      value={uploadSource}
                      onChange={(e) => setUploadSource(e.target.value)}
                      placeholder="例如：冯雪健康课程"
                      className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">分类</label>
                    <select
                      value={uploadCategory}
                      onChange={(e) => setUploadCategory(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    >
                      {categories.map((cat) => (
                        <option key={cat.value} value={cat.value}>{cat.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                <div className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-indigo-400 transition-colors">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.md,.json"
                    onChange={handleFileUpload}
                    className="hidden"
                    id="file-upload"
                  />
                  <label htmlFor="file-upload" className="cursor-pointer">
                    <div className="text-4xl mb-2">📄</div>
                    <p className="text-gray-600">点击选择文件或拖拽到此处</p>
                    <p className="text-sm text-gray-400 mt-1">支持 .txt, .md, .json</p>
                  </label>
                </div>
                
                {uploadFileMutation.isPending && (
                  <div className="text-center text-indigo-600">
                    <div className="animate-spin w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full mx-auto mb-2"></div>
                    上传中...
                  </div>
                )}
              </div>
            </div>

            {/* 添加文本 */}
            <div className="bg-white rounded-2xl shadow-lg p-6">
              <h2 className="text-xl font-bold text-gray-800 mb-4">✍️ 添加文本</h2>
              
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">标题</label>
                    <input
                      type="text"
                      value={textTitle}
                      onChange={(e) => setTextTitle(e.target.value)}
                      placeholder="知识点标题"
                      className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">分类</label>
                    <select
                      value={textCategory}
                      onChange={(e) => setTextCategory(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    >
                      {categories.map((cat) => (
                        <option key={cat.value} value={cat.value}>{cat.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">来源</label>
                    <input
                      type="text"
                      value={textSource}
                      onChange={(e) => setTextSource(e.target.value)}
                      placeholder="内容来源"
                      className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    />
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">内容</label>
                  <textarea
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    placeholder="输入健康知识内容..."
                    rows={8}
                    className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                  />
                </div>
                
                <button
                  onClick={() => addTextMutation.mutate()}
                  disabled={!textInput.trim() || addTextMutation.isPending}
                  className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg font-medium hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 transition-all"
                >
                  {addTextMutation.isPending ? '添加中...' : '添加到知识库'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 搜索测试 */}
        {activeTab === 'search' && (
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">🔍 知识搜索</h2>
            
            <div className="flex gap-3 mb-6">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && searchMutation.mutate()}
                placeholder="输入搜索内容，如：如何改善睡眠"
                className="flex-1 px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                onClick={() => searchMutation.mutate()}
                disabled={!searchQuery.trim() || searchMutation.isPending}
                className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg font-medium hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 transition-all"
              >
                {searchMutation.isPending ? '搜索中...' : '搜索'}
              </button>
            </div>

            {searchResults.length > 0 ? (
              <div className="space-y-4">
                <p className="text-sm text-gray-500">找到 {searchResults.length} 条相关内容</p>
                {searchResults.map((result, index) => (
                  <div key={index} className="border border-gray-200 rounded-xl p-4 hover:border-indigo-300 transition-colors">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-gray-800">{result.metadata.title || '无标题'}</span>
                      <span className="text-sm px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                        相关度: {(result.relevance_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="flex gap-2 mb-2">
                      {result.metadata.category && (
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                          {categories.find(c => c.value === result.metadata.category)?.label || result.metadata.category}
                        </span>
                      )}
                      {result.metadata.source && (
                        <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-600 rounded">
                          {result.metadata.source}
                        </span>
                      )}
                    </div>
                    <p className="text-gray-600 text-sm line-clamp-3">{result.content}</p>
                  </div>
                ))}
              </div>
            ) : searchMutation.isSuccess ? (
              <div className="text-center py-8 text-gray-500">
                <span className="text-4xl block mb-2">🔍</span>
                未找到相关内容
              </div>
            ) : (
              <div className="text-center py-8 text-gray-400">
                <span className="text-4xl block mb-2">💡</span>
                输入关键词搜索知识库内容
              </div>
            )}
          </div>
        )}

        {/* 问答测试 */}
        {activeTab === 'ask' && (
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">💬 RAG 问答</h2>
            <p className="text-gray-600 mb-4">基于知识库和您的个人画像，获取专业健康建议</p>
            
            <div className="flex gap-3 mb-6">
              <input
                type="text"
                value={askQuestion}
                onChange={(e) => setAskQuestion(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && askMutation.mutate()}
                placeholder="输入您的健康问题，如：我最近睡眠不好怎么办？"
                className="flex-1 px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                onClick={() => askMutation.mutate()}
                disabled={!askQuestion.trim() || askMutation.isPending}
                className="px-6 py-2 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-lg font-medium hover:from-indigo-600 hover:to-purple-600 disabled:opacity-50 transition-all"
              >
                {askMutation.isPending ? '思考中...' : '提问'}
              </button>
            </div>

            {askMutation.isPending && (
              <div className="text-center py-8">
                <div className="animate-spin w-8 h-8 border-4 border-indigo-500 border-t-transparent rounded-full mx-auto mb-2"></div>
                <p className="text-indigo-600">AI 正在结合知识库生成回答...</p>
              </div>
            )}

            {askResponse && (
              <div className="space-y-4">
                {askResponse.success ? (
                  <>
                    {/* 主要回答 */}
                    <div className="bg-gradient-to-br from-indigo-50 to-purple-50 rounded-xl p-5">
                      <div className="flex items-start gap-3">
                        <span className="text-2xl">🤖</span>
                        <div className="flex-1">
                          <p className="text-gray-800 whitespace-pre-wrap">{askResponse.answer}</p>
                        </div>
                      </div>
                    </div>

                    {/* 要点 */}
                    {askResponse.key_points && askResponse.key_points.length > 0 && (
                      <div className="bg-blue-50 rounded-xl p-4">
                        <h3 className="font-medium text-blue-800 mb-2">📌 关键要点</h3>
                        <ul className="space-y-1">
                          {askResponse.key_points.map((point, i) => (
                            <li key={i} className="text-blue-700 text-sm flex items-start gap-2">
                              <span className="text-blue-400">•</span>
                              {point}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* 行动建议 */}
                    {askResponse.action_items && askResponse.action_items.length > 0 && (
                      <div className="bg-green-50 rounded-xl p-4">
                        <h3 className="font-medium text-green-800 mb-2">✅ 行动建议</h3>
                        <ul className="space-y-1">
                          {askResponse.action_items.map((item, i) => (
                            <li key={i} className="text-green-700 text-sm flex items-start gap-2">
                              <span className="text-green-400">{i + 1}.</span>
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* 来源和元信息 */}
                    <div className="flex flex-wrap items-center gap-3 text-sm">
                      {askResponse.knowledge_used && (
                        <span className="px-2 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                          ✓ 使用了知识库
                        </span>
                      )}
                      {askResponse.confidence && (
                        <span className={`px-2 py-1 rounded-full ${
                          askResponse.confidence === 'high' 
                            ? 'bg-green-100 text-green-700'
                            : askResponse.confidence === 'medium'
                            ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-700'
                        }`}>
                          置信度: {askResponse.confidence === 'high' ? '高' : askResponse.confidence === 'medium' ? '中' : '低'}
                        </span>
                      )}
                    </div>

                    {/* 免责声明 */}
                    {askResponse.disclaimer && (
                      <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-3">
                        <p className="text-yellow-800 text-sm">⚠️ {askResponse.disclaimer}</p>
                      </div>
                    )}

                    {/* 知识来源 */}
                    {askResponse.sources && askResponse.sources.length > 0 && (
                      <div className="border-t border-gray-200 pt-4">
                        <h4 className="text-sm font-medium text-gray-600 mb-2">📚 参考来源</h4>
                        <div className="flex flex-wrap gap-2">
                          {askResponse.sources.map((source, i) => (
                            <span key={i} className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded">
                              {source.title || '未知来源'}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                    回答生成失败: {askResponse.error}
                  </div>
                )}
              </div>
            )}

            {!askMutation.isPending && !askResponse && (
              <div className="text-center py-8 text-gray-400">
                <span className="text-4xl block mb-2">💬</span>
                输入健康问题，AI 将结合知识库为您解答
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  return (
    <ProtectedRoute>
      <KnowledgeManagement />
    </ProtectedRoute>
  );
}
