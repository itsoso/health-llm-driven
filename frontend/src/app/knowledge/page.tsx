'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

interface DocumentInfo {
  filename: string;
  size: number;
  uploaded_at: string;
  chunks: number;
}

interface RAGResponse {
  answer: string;
  sources: Array<{
    content: string;
    metadata: Record<string, any>;
    relevance_score: number;
  }>;
  query_time: number;
}

export default function KnowledgePage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  
  const [activeTab, setActiveTab] = useState<'query' | 'upload' | 'manage'>('query');
  const [query, setQuery] = useState('');
  const [ragResponse, setRagResponse] = useState<RAGResponse | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [uploadText, setUploadText] = useState('');
  const [uploadTitle, setUploadTitle] = useState('');

  // 获取知识库文档列表
  const { data: documents, isLoading: docsLoading } = useQuery<DocumentInfo[]>({
    queryKey: ['knowledgeDocuments'],
    queryFn: async () => {
      const response = await api.get('/knowledge/documents');
      return response.data;
    },
    enabled: !!user,
  });

  // 上传文档
  const uploadMutation = useMutation({
    mutationFn: async (data: { title: string; content: string }) => {
      const response = await api.post('/knowledge/upload-text', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeDocuments'] });
      setUploadText('');
      setUploadTitle('');
      alert('上传成功！');
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || '上传失败');
    },
  });

  // RAG 查询
  const handleQuery = async () => {
    if (!query.trim()) return;
    
    setQueryLoading(true);
    try {
      const response = await api.post('/knowledge/query', { question: query });
      setRagResponse(response.data);
    } catch (error: any) {
      alert(error.response?.data?.detail || '查询失败');
    } finally {
      setQueryLoading(false);
    }
  };

  // 健康问答（快捷查询）
  const quickQueries = [
    '如何改善睡眠质量？',
    '什么运动适合减脂？',
    '高血压患者饮食注意什么？',
    '如何缓解工作压力？',
    '补剂应该如何选择？',
    '跑步后如何恢复？',
  ];

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-400"></div>
      </div>
    );
  }

  if (!user) {
    router.push('/login');
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* 头部 */}
      <header className="bg-black/20 backdrop-blur-sm border-b border-white/10">
        <div className="max-w-4xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="text-white/70 hover:text-white transition-colors"
            >
              ← 返回
            </button>
            <h1 className="text-xl font-bold text-white">📚 健康知识库</h1>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6">
        {/* Tab 导航 */}
        <div className="flex gap-2 mb-6">
          {[
            { id: 'query', label: '智能问答', icon: '🔍' },
            { id: 'upload', label: '上传知识', icon: '📝' },
            { id: 'manage', label: '知识管理', icon: '📂' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/10 text-white/70 hover:bg-white/20'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* 智能问答 */}
        {activeTab === 'query' && (
          <div className="space-y-6">
            {/* 搜索框 */}
            <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
              <h3 className="text-lg font-semibold text-white mb-4">💡 问我任何健康问题</h3>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyPress={e => e.key === 'Enter' && handleQuery()}
                  placeholder="例如：如何提高睡眠质量？"
                  className="flex-1 bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/40 focus:outline-none focus:border-purple-500"
                />
                <button
                  onClick={handleQuery}
                  disabled={queryLoading}
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
                >
                  {queryLoading ? '查询中...' : '提问'}
                </button>
              </div>
              
              {/* 快捷查询 */}
              <div className="mt-4">
                <span className="text-white/50 text-sm">快捷问题：</span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {quickQueries.map(q => (
                    <button
                      key={q}
                      onClick={() => {
                        setQuery(q);
                        handleQuery();
                      }}
                      className="px-3 py-1 bg-white/10 hover:bg-white/20 text-white/80 rounded-full text-sm transition-colors"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* 回答结果 */}
            {ragResponse && (
              <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">🤖 AI 回答</h3>
                  <span className="text-white/40 text-sm">
                    用时 {ragResponse.query_time.toFixed(2)}s
                  </span>
                </div>
                
                <div className="prose prose-invert max-w-none">
                  <div className="text-white/90 whitespace-pre-wrap leading-relaxed">
                    {ragResponse.answer}
                  </div>
                </div>

                {/* 引用来源 */}
                {ragResponse.sources.length > 0 && (
                  <div className="mt-6 pt-6 border-t border-white/10">
                    <h4 className="text-white/70 text-sm font-medium mb-3">📖 参考来源</h4>
                    <div className="space-y-3">
                      {ragResponse.sources.map((source, idx) => (
                        <div
                          key={idx}
                          className="p-3 bg-white/5 rounded-lg border border-white/5"
                        >
                          <p className="text-white/70 text-sm line-clamp-3">
                            {source.content}
                          </p>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="text-xs text-purple-400">
                              相关度: {(source.relevance_score * 100).toFixed(0)}%
                            </span>
                            {source.metadata.source && (
                              <span className="text-xs text-white/40">
                                来源: {source.metadata.source}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 上传知识 */}
        {activeTab === 'upload' && (
          <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">📝 添加健康知识</h3>
            <p className="text-white/60 text-sm mb-6">
              上传健康知识文章，AI 会学习并用于回答问题。支持纯文本格式。
            </p>
            
            <div className="space-y-4">
              <div>
                <label className="block text-white/70 text-sm mb-2">标题</label>
                <input
                  type="text"
                  value={uploadTitle}
                  onChange={e => setUploadTitle(e.target.value)}
                  placeholder="例如：冯雪-家庭健康讲座笔记"
                  className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/40 focus:outline-none focus:border-purple-500"
                />
              </div>
              
              <div>
                <label className="block text-white/70 text-sm mb-2">内容</label>
                <textarea
                  value={uploadText}
                  onChange={e => setUploadText(e.target.value)}
                  placeholder="粘贴或输入健康知识内容..."
                  rows={12}
                  className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white placeholder:text-white/40 focus:outline-none focus:border-purple-500 resize-none"
                />
              </div>
              
              <button
                onClick={() => uploadMutation.mutate({ title: uploadTitle, content: uploadText })}
                disabled={uploadMutation.isPending || !uploadTitle || !uploadText}
                className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
              >
                {uploadMutation.isPending ? '上传中...' : '📤 上传知识'}
              </button>
            </div>
            
            {/* 预设知识源 */}
            <div className="mt-8 pt-6 border-t border-white/10">
              <h4 className="text-white/70 text-sm font-medium mb-3">推荐知识来源</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {[
                  { name: '冯雪家庭健康讲座', desc: '心血管专家的家庭健康指南' },
                  { name: '皮皮妈妈免疫健康', desc: '免疫系统与日常保健' },
                  { name: '跑步治愈-张展晖', desc: '科学跑步与运动康复' },
                  { name: '得到健康课程', desc: '系统性健康知识' },
                ].map(source => (
                  <div
                    key={source.name}
                    className="p-3 bg-white/5 rounded-lg border border-white/10"
                  >
                    <span className="text-white font-medium text-sm">{source.name}</span>
                    <p className="text-white/50 text-xs mt-1">{source.desc}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 知识管理 */}
        {activeTab === 'manage' && (
          <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">📂 已上传的知识</h3>
            
            {docsLoading ? (
              <div className="text-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-purple-400 mx-auto"></div>
              </div>
            ) : documents && documents.length > 0 ? (
              <div className="space-y-3">
                {documents.map((doc, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10"
                  >
                    <div>
                      <span className="text-white font-medium">{doc.filename}</span>
                      <div className="flex items-center gap-4 mt-1">
                        <span className="text-white/50 text-xs">
                          {(doc.size / 1024).toFixed(1)} KB
                        </span>
                        <span className="text-white/50 text-xs">
                          {doc.chunks} 段落
                        </span>
                        <span className="text-white/50 text-xs">
                          {new Date(doc.uploaded_at).toLocaleDateString('zh-CN')}
                        </span>
                      </div>
                    </div>
                    <button className="text-red-400 hover:text-red-300 text-sm">
                      删除
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <span className="text-6xl mb-4 block">📭</span>
                <p className="text-white/50">还没有上传任何知识</p>
                <button
                  onClick={() => setActiveTab('upload')}
                  className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm transition-colors"
                >
                  去上传
                </button>
              </div>
            )}
            
            {/* 知识库统计 */}
            <div className="mt-6 pt-6 border-t border-white/10">
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-4 bg-white/5 rounded-lg">
                  <div className="text-2xl font-bold text-purple-400">
                    {documents?.length || 0}
                  </div>
                  <div className="text-white/50 text-sm mt-1">文档数</div>
                </div>
                <div className="text-center p-4 bg-white/5 rounded-lg">
                  <div className="text-2xl font-bold text-blue-400">
                    {documents?.reduce((sum, d) => sum + d.chunks, 0) || 0}
                  </div>
                  <div className="text-white/50 text-sm mt-1">知识片段</div>
                </div>
                <div className="text-center p-4 bg-white/5 rounded-lg">
                  <div className="text-2xl font-bold text-green-400">
                    {documents ? (documents.reduce((sum, d) => sum + d.size, 0) / 1024).toFixed(0) : 0} KB
                  </div>
                  <div className="text-white/50 text-sm mt-1">总大小</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
