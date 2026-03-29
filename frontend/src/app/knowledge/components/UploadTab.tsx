'use client';

import { RefObject, LegacyRef } from 'react';
import { UseMutationResult } from '@tanstack/react-query';

interface Category {
  value: string;
  label: string;
}

interface UploadTabProps {
  // Course upload state
  courseTitle: string;
  setCourseTitle: (v: string) => void;
  courseAuthor: string;
  setCourseAuthor: (v: string) => void;
  courseSource: string;
  setCourseSource: (v: string) => void;
  courseDifficulty: string;
  setCourseDifficulty: (v: string) => void;
  courseTargetAudience: string[];
  setCourseTargetAudience: (v: string[]) => void;
  audienceInput: string;
  setAudienceInput: (v: string) => void;
  addAudience: () => void;
  removeAudience: (audience: string) => void;
  // Upload mode
  uploadMode: 'text' | 'files';
  setUploadMode: (v: 'text' | 'files') => void;
  // Text mode
  courseContent: string;
  setCourseContent: (v: string) => void;
  uploadCourseMutation: UseMutationResult<any, any, void, unknown>;
  // File mode
  selectedFiles: File[];
  setSelectedFiles: (v: File[] | ((prev: File[]) => File[])) => void;
  courseFileInputRef: RefObject<HTMLInputElement | null>;
  uploadCourseFilesMutation: UseMutationResult<any, any, void, unknown>;
  // Simple file upload
  fileInputRef: RefObject<HTMLInputElement | null>;
  uploadSource: string;
  setUploadSource: (v: string) => void;
  uploadCategory: string;
  setUploadCategory: (v: string) => void;
  uploadFileMutation: UseMutationResult<any, any, File, unknown>;
  handleFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  // Text add
  textInput: string;
  setTextInput: (v: string) => void;
  textTitle: string;
  setTextTitle: (v: string) => void;
  textCategory: string;
  setTextCategory: (v: string) => void;
  textSource: string;
  setTextSource: (v: string) => void;
  addTextMutation: UseMutationResult<any, any, void, unknown>;
  categories: Category[];
}

export function UploadTab(props: UploadTabProps) {
  const {
    courseTitle, setCourseTitle, courseAuthor, setCourseAuthor,
    courseSource, setCourseSource, courseDifficulty, setCourseDifficulty,
    courseTargetAudience, setCourseTargetAudience, audienceInput, setAudienceInput,
    addAudience, removeAudience,
    uploadMode, setUploadMode,
    courseContent, setCourseContent, uploadCourseMutation,
    selectedFiles, setSelectedFiles, courseFileInputRef, uploadCourseFilesMutation,
    fileInputRef, uploadSource, setUploadSource, uploadCategory, setUploadCategory,
    uploadFileMutation, handleFileUpload,
    textInput, setTextInput, textTitle, setTextTitle,
    textCategory, setTextCategory, textSource, setTextSource,
    addTextMutation, categories,
  } = props;

  return (
    <div className="space-y-6">
      {/* 上传课程（增强版） */}
      <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border-2 border-indigo-200 rounded-2xl shadow-lg p-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-3xl">🎓</span>
          <div>
            <h2 className="text-xl font-bold text-indigo-900">上传专业课程</h2>
            <p className="text-sm text-indigo-700">专为运动科学课程优化，支持完整的 Markdown 层级结构</p>
          </div>
        </div>

        <div className="space-y-4">
          {/* 基本信息 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                课程标题 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={courseTitle}
                onChange={(e) => setCourseTitle(e.target.value)}
                placeholder="例如：心率区间训练法"
                className="w-full px-4 py-2 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                作者
              </label>
              <input
                type="text"
                value={courseAuthor}
                onChange={(e) => setCourseAuthor(e.target.value)}
                placeholder="张展晖"
                className="w-full px-4 py-2 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                来源标识 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={courseSource}
                onChange={(e) => setCourseSource(e.target.value)}
                placeholder="例如：zhang_zhanhui_01"
                className="w-full px-4 py-2 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
              />
              <p className="text-xs text-indigo-600 mt-1">用于标识和检索，建议使用英文+数字</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                难度级别
              </label>
              <select
                value={courseDifficulty}
                onChange={(e) => setCourseDifficulty(e.target.value)}
                className="w-full px-4 py-2 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
              >
                <option value="beginner">初级 (Beginner)</option>
                <option value="intermediate">中级 (Intermediate)</option>
                <option value="advanced">高级 (Advanced)</option>
              </select>
            </div>
          </div>

          {/* 目标人群 */}
          <div>
            <label className="block text-sm font-medium text-indigo-900 mb-1">
              目标人群
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={audienceInput}
                onChange={(e) => setAudienceInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addAudience())}
                placeholder="输入目标人群，按回车添加"
                className="flex-1 px-4 py-2 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white"
              />
              <button
                onClick={addAudience}
                className="px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors"
              >
                添加
              </button>
            </div>
            {courseTargetAudience.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {courseTargetAudience.map((audience, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm"
                  >
                    {audience}
                    <button
                      onClick={() => removeAudience(audience)}
                      className="hover:text-indigo-900"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-indigo-600 mt-1">
              例如：跑步爱好者、减脂人群、马拉松备赛者
            </p>
          </div>

          {/* 上传模式切换 */}
          <div className="border-t-2 border-indigo-200 pt-4">
            <label className="block text-sm font-medium text-indigo-900 mb-3">
              📝 上传方式
            </label>
            <div className="flex gap-4 mb-4">
              <button
                onClick={() => setUploadMode('text')}
                className={`flex-1 px-4 py-3 rounded-lg font-medium transition-all ${
                  uploadMode === 'text'
                    ? 'bg-gradient-to-r from-purple-500 to-indigo-600 text-white shadow-lg'
                    : 'bg-white text-indigo-600 border-2 border-indigo-200 hover:border-indigo-400'
                }`}
              >
                📄 粘贴文本
              </button>
              <button
                onClick={() => setUploadMode('files')}
                className={`flex-1 px-4 py-3 rounded-lg font-medium transition-all ${
                  uploadMode === 'files'
                    ? 'bg-gradient-to-r from-purple-500 to-indigo-600 text-white shadow-lg'
                    : 'bg-white text-indigo-600 border-2 border-indigo-200 hover:border-indigo-400'
                }`}
              >
                📁 上传文件
              </button>
            </div>
          </div>

          {/* 文本输入模式 */}
          {uploadMode === 'text' && (
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                课程内容 (Markdown 格式) <span className="text-red-500">*</span>
              </label>
              <textarea
                value={courseContent}
                onChange={(e) => setCourseContent(e.target.value)}
                placeholder={"粘贴 Markdown 格式的课程内容...\n\n支持：\n# 一级标题\n## 二级标题\n### 三级标题\n\n系统会自动：\n✓ 保留标题层级结构\n✓ 生成面包屑导航\n✓ 提取关键概念\n✓ 智能分块（1800-2000字符）"}
                rows={12}
                className="w-full px-4 py-3 border-2 border-indigo-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none font-mono text-sm bg-white"
              />
              <div className="flex items-center justify-between mt-2">
                <p className="text-xs text-indigo-600">
                  {courseContent.length} 字符
                  {courseContent.length > 0 && ` (预计生成 ${Math.ceil(courseContent.length / 1800)} 个文档块)`}
                </p>
              </div>
            </div>
          )}

          {/* 文件上传模式 */}
          {uploadMode === 'files' && (
            <div>
              <label className="block text-sm font-medium text-indigo-900 mb-1">
                选择 Markdown 文件 <span className="text-red-500">*</span>
              </label>
              <input
                ref={courseFileInputRef as LegacyRef<HTMLInputElement>}
                type="file"
                multiple
                accept=".md,.markdown"
                onChange={(e) => {
                  const files = Array.from(e.target.files || []);
                  console.log('✅ 文件选择变化:', files.length, '个文件');
                  files.forEach((f, i) => {
                    console.log(`  ${i+1}. ${f.name} (${(f.size/1024).toFixed(1)} KB)`);
                  });
                  setSelectedFiles(files);
                }}
                className="hidden"
                id="course-file-upload"
              />
              <div
                className="border-2 border-dashed border-indigo-300 rounded-lg p-8 text-center hover:border-indigo-500 hover:bg-indigo-50/50 transition-all"
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  console.log('📥 拖拽文件', e.dataTransfer.files.length, '个');
                  const droppedFiles = Array.from(e.dataTransfer.files).filter(
                    file => file.name.endsWith('.md') || file.name.endsWith('.markdown')
                  );
                  if (droppedFiles.length > 0) {
                    console.log('✅ 有效的 Markdown 文件:', droppedFiles.length, '个');
                    setSelectedFiles(droppedFiles);
                  } else {
                    console.log('❌ 没有有效的 Markdown 文件');
                    alert('请拖拽 .md 或 .markdown 文件');
                  }
                }}
              >
                <div className="text-4xl mb-2">📁</div>
                <p className="text-indigo-900 font-medium mb-2">
                  点击下方按钮选择文件或拖拽文件到此处
                </p>
                <button
                  type="button"
                  onClick={() => {
                    console.log('🖱️ 点击选择文件按钮');
                    document.getElementById('course-file-upload')?.click();
                  }}
                  className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors inline-block"
                >
                  📂 选择文件
                </button>
                <p className="text-sm text-indigo-600 mt-2">
                  支持多个 .md 或 .markdown 文件
                </p>
              </div>

              {selectedFiles.length > 0 && (
                <div className="mt-4 space-y-2">
                  <p className="text-sm font-medium text-indigo-900">
                    已选择 {selectedFiles.length} 个文件:
                  </p>
                  <div className="bg-white rounded-lg border-2 border-indigo-200 p-3 max-h-40 overflow-y-auto">
                    {selectedFiles.map((file, i) => (
                      <div key={i} className="flex items-center justify-between py-2 border-b border-indigo-100 last:border-0">
                        <div className="flex items-center gap-2">
                          <span className="text-indigo-600">📄</span>
                          <span className="text-sm text-indigo-900">{file.name}</span>
                          <span className="text-xs text-indigo-500">
                            ({(file.size / 1024).toFixed(1)} KB)
                          </span>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedFiles((files: File[]) => files.filter((_: File, idx: number) => idx !== i));
                          }}
                          className="text-red-500 hover:text-red-700 font-bold"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-indigo-600">
                    总大小: {(selectedFiles.reduce((sum, f) => sum + f.size, 0) / 1024).toFixed(1)} KB
                  </p>
                </div>
              )}
            </div>
          )}

          {/* 功能说明 */}
          <div className="bg-white/50 rounded-lg p-4 border border-indigo-200">
            <h4 className="font-medium text-indigo-900 mb-2">✨ 增强版特性</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-indigo-700">
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>保留 Markdown 标题层级结构</span>
              </div>
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>自动生成面包屑导航</span>
              </div>
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>智能提取关键概念</span>
              </div>
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>更大的分块大小（1800-2000字符）</span>
              </div>
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>丰富的元数据（作者、难度、人群）</span>
              </div>
              <div className="flex items-start gap-2">
                <span>✓</span>
                <span>运动科学专用分类识别</span>
              </div>
            </div>
          </div>

          {/* 上传按钮 */}
          <div className="flex gap-3">
            {uploadMode === 'text' ? (
              <>
                <button
                  onClick={() => uploadCourseMutation.mutate()}
                  disabled={!courseContent.trim() || !courseTitle.trim() || !courseSource.trim() || uploadCourseMutation.isPending}
                  className="flex-1 px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg font-medium hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg"
                >
                  {uploadCourseMutation.isPending ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full"></div>
                      上传中...
                    </span>
                  ) : (
                    '🚀 上传课程'
                  )}
                </button>
                <button
                  onClick={() => {
                    setCourseContent('');
                    setCourseTitle('');
                    setCourseSource('');
                    setCourseTargetAudience([]);
                  }}
                  className="px-6 py-3 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-all"
                >
                  清空
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => uploadCourseFilesMutation.mutate()}
                  disabled={selectedFiles.length === 0 || !courseTitle.trim() || !courseSource.trim() || uploadCourseFilesMutation.isPending}
                  className="flex-1 px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg font-medium hover:from-indigo-700 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg"
                >
                  {uploadCourseFilesMutation.isPending ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full"></div>
                      上传中...
                    </span>
                  ) : (
                    `🚀 上传 ${selectedFiles.length} 个文件`
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedFiles([]);
                    setCourseTitle('');
                    setCourseSource('');
                    setCourseTargetAudience([]);
                    if (courseFileInputRef.current) {
                      courseFileInputRef.current.value = '';
                    }
                  }}
                  className="px-6 py-3 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-all"
                >
                  清空
                </button>
              </>
            )}
          </div>
        </div>
      </div>

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
              ref={fileInputRef as LegacyRef<HTMLInputElement>}
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
  );
}
