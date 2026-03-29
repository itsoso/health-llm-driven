'use client';

import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { StatsTab } from './components/StatsTab';
import { UploadTab } from './components/UploadTab';
import { SearchTab } from './components/SearchTab';
import { AskTab } from './components/AskTab';

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
  { value: 'cardio_training', label: '心肺训练' },
  { value: 'strength_training', label: '力量训练' },
  { value: 'exercise_physiology', label: '运动生理学' },
  { value: 'recovery', label: '恢复策略' },
  { value: 'goal_setting', label: '目标设定' },
  { value: 'injury_prevention', label: '损伤预防' },
  { value: 'performance', label: '运动表现' },
];

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

  // 课程上传状态
  const [courseContent, setCourseContent] = useState('');
  const [courseTitle, setCourseTitle] = useState('');
  const [courseAuthor, setCourseAuthor] = useState('张展晖');
  const [courseSource, setCourseSource] = useState('');
  const [courseDifficulty, setCourseDifficulty] = useState('intermediate');
  const [courseTargetAudience, setCourseTargetAudience] = useState<string[]>([]);
  const [audienceInput, setAudienceInput] = useState('');

  // 文件上传状态
  const [uploadMode, setUploadMode] = useState<'text' | 'files'>('text');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const courseFileInputRef = useRef<HTMLInputElement>(null);

  // 获取知识库统计
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery<KnowledgeStats>({
    queryKey: ['knowledgeStats'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/knowledge/stats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.json();
    },
    enabled: !!token,
  });

  // 初始化基础知识
  const initBasicsMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/knowledge/init/health-basics`, {
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
      const res = await fetch(`${API_BASE}/knowledge/documents/text`, {
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

      const res = await fetch(`${API_BASE}/knowledge/documents/upload`, {
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
      const res = await fetch(`${API_BASE}/knowledge/search`, {
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
      const res = await fetch(`${API_BASE}/knowledge/ask`, {
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

  // 上传课程（文本方式）
  const uploadCourseMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/knowledge/documents/course`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: courseContent,
          title: courseTitle,
          author: courseAuthor,
          source: courseSource,
          difficulty: courseDifficulty,
          target_audience: courseTargetAudience,
          course_metadata: {
            platform: '得到',
            course_type: '运动科学',
          },
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '上传失败');
      }
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['knowledgeStats'] });
      alert(`✅ 课程上传成功！\n\n添加了 ${data.documents_added} 个文档块\n向量化了 ${data.embeddings_added} 个文档`);
      setCourseContent('');
      setCourseTitle('');
      setCourseSource('');
      setCourseTargetAudience([]);
    },
    onError: (error: any) => {
      alert(`❌ 上传失败: ${error.message}`);
    },
  });

  // 上传课程文件（多文件方式）
  const uploadCourseFilesMutation = useMutation({
    mutationFn: async () => {
      if (selectedFiles.length === 0) {
        throw new Error('请选择至少一个文件');
      }

      const formData = new FormData();
      selectedFiles.forEach(file => {
        formData.append('files', file);
      });
      formData.append('source', courseSource);
      formData.append('title', courseTitle);
      formData.append('author', courseAuthor);
      formData.append('difficulty', courseDifficulty);
      formData.append('target_audiences', JSON.stringify(courseTargetAudience));

      const res = await fetch(`${API_BASE}/knowledge/documents/course/files`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
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

      const successFiles = data.files.filter((f: any) => f.success);
      const failedFiles = data.files.filter((f: any) => !f.success);

      let message = `✅ 文件上传成功！\n\n`;
      message += `成功: ${successFiles.length} 个文件\n`;
      message += `总文档块: ${data.total_chunks}\n`;
      message += `已添加: ${data.added_count} 个文档块\n\n`;

      if (successFiles.length > 0) {
        message += `成功的文件:\n`;
        successFiles.forEach((f: any) => {
          message += `  • ${f.filename} (${f.chunks} 块, ${f.size_kb} KB)\n`;
        });
      }

      if (failedFiles.length > 0) {
        message += `\n失败的文件:\n`;
        failedFiles.forEach((f: any) => {
          message += `  • ${f.filename}: ${f.error}\n`;
        });
      }

      alert(message);

      setSelectedFiles([]);
      setCourseTitle('');
      setCourseSource('');
      setCourseTargetAudience([]);
      if (courseFileInputRef.current) {
        courseFileInputRef.current.value = '';
      }
    },
    onError: (error: any) => {
      alert(`❌ 上传失败: ${error.message}`);
    },
  });

  // 清空知识库
  const clearAllMutation = useMutation({
    mutationFn: async () => {
      if (!confirm('确定要清空整个知识库吗？此操作不可恢复！')) {
        throw new Error('已取消');
      }
      const res = await fetch(`${API_BASE}/knowledge/documents/all?confirm=true`, {
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

  const addAudience = () => {
    if (audienceInput.trim() && !courseTargetAudience.includes(audienceInput.trim())) {
      setCourseTargetAudience([...courseTargetAudience, audienceInput.trim()]);
      setAudienceInput('');
    }
  };

  const removeAudience = (audience: string) => {
    setCourseTargetAudience(courseTargetAudience.filter(a => a !== audience));
  };

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
            { key: 'stats', label: '📈 统计概览', icon: '📈' },
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

        {activeTab === 'stats' && (
          <StatsTab
            stats={stats}
            statsLoading={statsLoading}
            initBasicsMutation={initBasicsMutation}
            clearAllMutation={clearAllMutation}
            refetchStats={refetchStats}
          />
        )}

        {activeTab === 'upload' && (
          <UploadTab
            courseTitle={courseTitle} setCourseTitle={setCourseTitle}
            courseAuthor={courseAuthor} setCourseAuthor={setCourseAuthor}
            courseSource={courseSource} setCourseSource={setCourseSource}
            courseDifficulty={courseDifficulty} setCourseDifficulty={setCourseDifficulty}
            courseTargetAudience={courseTargetAudience} setCourseTargetAudience={setCourseTargetAudience}
            audienceInput={audienceInput} setAudienceInput={setAudienceInput}
            addAudience={addAudience} removeAudience={removeAudience}
            uploadMode={uploadMode} setUploadMode={setUploadMode}
            courseContent={courseContent} setCourseContent={setCourseContent}
            uploadCourseMutation={uploadCourseMutation}
            selectedFiles={selectedFiles} setSelectedFiles={setSelectedFiles}
            courseFileInputRef={courseFileInputRef}
            uploadCourseFilesMutation={uploadCourseFilesMutation}
            fileInputRef={fileInputRef}
            uploadSource={uploadSource} setUploadSource={setUploadSource}
            uploadCategory={uploadCategory} setUploadCategory={setUploadCategory}
            uploadFileMutation={uploadFileMutation}
            handleFileUpload={handleFileUpload}
            textInput={textInput} setTextInput={setTextInput}
            textTitle={textTitle} setTextTitle={setTextTitle}
            textCategory={textCategory} setTextCategory={setTextCategory}
            textSource={textSource} setTextSource={setTextSource}
            addTextMutation={addTextMutation}
            categories={categories}
          />
        )}

        {activeTab === 'search' && (
          <SearchTab
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchResults={searchResults}
            searchMutation={searchMutation}
            categories={categories}
          />
        )}

        {activeTab === 'ask' && (
          <AskTab
            askQuestion={askQuestion}
            setAskQuestion={setAskQuestion}
            askResponse={askResponse}
            askMutation={askMutation}
          />
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
