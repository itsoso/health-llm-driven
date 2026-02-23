'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { vocabularyApi, VocabularyWord } from '@/services/api';
import { useKidsTheme } from '@/contexts/KidsThemeContext';

type TabKey = 'all' | 'review' | 'mastered';

export default function KidsVocabPage() {
  const router = useRouter();
  const { theme } = useKidsTheme();
  const [tab, setTab] = useState<TabKey>('all');
  const [words, setWords] = useState<VocabularyWord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  // 复习模式
  const [reviewMode, setReviewMode] = useState(false);
  const [reviewWords, setReviewWords] = useState<VocabularyWord[]>([]);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  // 详情展开
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // 多选
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const loadWords = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === 'review') {
        const res = await vocabularyApi.getReviewWords(20);
        setWords(res.data.words);
        setTotal(res.data.total);
      } else {
        const mastered = tab === 'mastered' ? true : undefined;
        const res = await vocabularyApi.getWords(page, 20, mastered);
        setWords(res.data.words);
        setTotal(res.data.total);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [tab, page]);

  useEffect(() => {
    setPage(1);
    setExpandedId(null);
    setSelectedIds(new Set());
  }, [tab]);

  useEffect(() => {
    loadWords();
  }, [loadWords]);

  const handleDelete = async (wordId: number) => {
    if (!confirm('确定要从单词本中删除这个单词吗？')) return;
    try {
      await vocabularyApi.deleteWord(wordId);
      loadWords();
    } catch {
      // ignore
    }
  };

  const startReview = async () => {
    try {
      const res = await vocabularyApi.getReviewWords(10);
      if (res.data.words.length === 0) {
        alert('暂时没有需要复习的单词');
        return;
      }
      setReviewWords(res.data.words);
      setReviewIndex(0);
      setShowAnswer(false);
      setReviewMode(true);
    } catch {
      // ignore
    }
  };

  // 复习指定单词（单个或多选）
  const startReviewWithWords = (wordsToReview: VocabularyWord[]) => {
    if (wordsToReview.length === 0) return;
    setReviewWords(wordsToReview);
    setReviewIndex(0);
    setShowAnswer(false);
    setReviewMode(true);
    setSelectedIds(new Set());
  };

  const toggleSelect = (wordId: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(wordId)) next.delete(wordId);
      else next.add(wordId);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === words.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(words.map(w => w.id)));
    }
  };

  const handleReviewAnswer = async (isCorrect: boolean) => {
    const word = reviewWords[reviewIndex];
    setReviewSubmitting(true);
    try {
      await vocabularyApi.submitReview(word.id, isCorrect);
    } catch {
      // ignore
    }
    setReviewSubmitting(false);

    if (reviewIndex < reviewWords.length - 1) {
      setReviewIndex(i => i + 1);
      setShowAnswer(false);
    } else {
      setReviewMode(false);
      loadWords();
    }
  };

  const parseMeanings = (meanings?: string): { pos: string; def: string }[] => {
    if (!meanings) return [];
    try {
      return JSON.parse(meanings);
    } catch {
      return [{ pos: '', def: meanings }];
    }
  };

  const parseExamples = (examples?: string): { en: string; zh: string }[] => {
    if (!examples) return [];
    try {
      return JSON.parse(examples);
    } catch {
      return [];
    }
  };

  const masteryStars = (level: number) => {
    return '★'.repeat(level) + '☆'.repeat(5 - level);
  };

  // 复习模式 UI
  if (reviewMode && reviewWords.length > 0) {
    const word = reviewWords[reviewIndex];
    const meanings = parseMeanings(word.meanings);
    const examples = parseExamples(word.example_sentences);
    return (
      <div className={`min-h-screen ${theme.bg} p-4 pb-24`}>
        <div className="max-w-lg mx-auto">
          <div className="flex items-center justify-between mb-6">
            <button
              onClick={() => setReviewMode(false)}
              className="text-gray-500 text-sm"
            >
              ← 返回
            </button>
            <span className="text-gray-500 text-sm">
              {reviewIndex + 1} / {reviewWords.length}
            </span>
          </div>

          <div className="bg-white rounded-2xl shadow-lg p-6 text-center">
            <div className="text-4xl font-bold text-gray-800 mb-2">{word.word}</div>
            {word.phonetic_us && (
              <div className="text-gray-400 text-sm mb-4">
                美 {word.phonetic_us}
                {word.phonetic_uk && ` | 英 ${word.phonetic_uk}`}
              </div>
            )}
            <div className="text-sm text-gray-400 mb-6">
              {masteryStars(word.mastery_level)}
            </div>

            {!showAnswer ? (
              <button
                onClick={() => setShowAnswer(true)}
                className={`w-full py-3 rounded-xl text-white font-medium ${theme.btnGrad}`}
              >
                显示答案
              </button>
            ) : (
              <div className="space-y-4">
                <div className="text-left space-y-1">
                  {meanings.map((m, i) => (
                    <div key={i} className="text-gray-700">
                      <span className="text-blue-500 font-medium mr-1">{m.pos}</span>
                      {m.def}
                    </div>
                  ))}
                </div>

                {word.word_roots && (
                  <div className="text-left text-sm text-gray-500 bg-gray-50 rounded-lg p-2">
                    词根: {word.word_roots}
                  </div>
                )}

                {examples.length > 0 && (
                  <div className="text-left space-y-1">
                    {examples.slice(0, 2).map((ex, i) => (
                      <div key={i} className="text-sm">
                        <div className="text-gray-700">{ex.en}</div>
                        <div className="text-gray-400">{ex.zh}</div>
                      </div>
                    ))}
                  </div>
                )}

                {word.synonyms && (
                  <div className="text-left text-sm text-gray-500">
                    近义词: {word.synonyms}
                  </div>
                )}
                {word.antonyms && (
                  <div className="text-left text-sm text-gray-500">
                    反义词: {word.antonyms}
                  </div>
                )}

                <div className="flex gap-3 pt-2">
                  <button
                    onClick={() => handleReviewAnswer(false)}
                    disabled={reviewSubmitting}
                    className="flex-1 py-3 rounded-xl bg-red-100 text-red-600 font-medium hover:bg-red-200 transition"
                  >
                    没记住
                  </button>
                  <button
                    onClick={() => handleReviewAnswer(true)}
                    disabled={reviewSubmitting}
                    className="flex-1 py-3 rounded-xl bg-green-100 text-green-600 font-medium hover:bg-green-200 transition"
                  >
                    记住了
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 列表模式 UI
  const tabs: { key: TabKey; label: string }[] = [
    { key: 'all', label: '全部' },
    { key: 'review', label: '待复习' },
    { key: 'mastered', label: '已掌握' },
  ];

  return (
    <div className={`min-h-screen ${theme.bg} p-4 pb-24`}>
      <div className="max-w-lg mx-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold text-gray-800">📖 我的单词本</h1>
          <button
            onClick={() => router.push('/kids')}
            className={`px-3 py-1.5 rounded-lg text-white text-sm font-medium ${theme.btnGrad}`}
          >
            去聊天学单词 →
          </button>
        </div>

        {/* Tab 筛选 */}
        <div className="flex gap-2 mb-4">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition ${
                tab === t.key
                  ? `${theme.tabActiveBg} ${theme.tabActiveText}`
                  : 'bg-white/60 text-gray-500 hover:bg-white/80'
              }`}
            >
              {t.label}
              {t.key === 'all' && total > 0 && tab === 'all' ? ` ${total}` : ''}
            </button>
          ))}
        </div>

        {/* 复习入口 + 选择操作 */}
        <div className="flex gap-2 mb-4">
          {tab !== 'mastered' && (
            <button
              onClick={startReview}
              className="flex-1 py-3 rounded-xl bg-gradient-to-r from-amber-400 to-orange-400 text-white font-medium shadow-sm hover:shadow-md transition"
            >
              开始复习
            </button>
          )}
          {words.length > 0 && (
            <button
              onClick={toggleSelectAll}
              className={`${tab === 'mastered' ? 'flex-1' : ''} px-4 py-3 rounded-xl font-medium transition ${
                selectedIds.size > 0 && selectedIds.size === words.length
                  ? 'bg-purple-500 text-white'
                  : 'bg-white/80 text-gray-600 border border-gray-200'
              }`}
            >
              {selectedIds.size > 0 && selectedIds.size === words.length ? '取消全选' : '全选'}
            </button>
          )}
        </div>

        {/* 选中复习按钮 */}
        {selectedIds.size > 0 && (
          <button
            onClick={() => startReviewWithWords(words.filter(w => selectedIds.has(w.id)))}
            className="w-full mb-4 py-3 rounded-xl bg-gradient-to-r from-purple-500 to-indigo-500 text-white font-medium shadow-md hover:shadow-lg transition flex items-center justify-center gap-2"
          >
            <span>📝</span> 复习选中的 {selectedIds.size} 个单词
          </button>
        )}

        {/* 加载中 */}
        {loading && (
          <div className="text-center py-8 text-gray-400">加载中...</div>
        )}

        {/* 空状态 */}
        {!loading && words.length === 0 && (
          <div className="text-center py-12">
            <div className="text-4xl mb-3">📚</div>
            <div className="text-gray-400 mb-4">
              {tab === 'review' ? '暂时没有待复习的单词' :
               tab === 'mastered' ? '还没有已掌握的单词' :
               '还没有学过单词'}
            </div>
            <button
              onClick={() => router.push('/kids')}
              className={`px-4 py-2 rounded-lg text-white text-sm ${theme.btnGrad}`}
            >
              去聊天学单词
            </button>
          </div>
        )}

        {/* 单词列表 */}
        <div className="space-y-3">
          {words.map(word => {
            const meanings = parseMeanings(word.meanings);
            const examples = parseExamples(word.example_sentences);
            const isExpanded = expandedId === word.id;
            return (
              <div
                key={word.id}
                className={`bg-white rounded-xl shadow-sm overflow-hidden transition-all ${
                  selectedIds.has(word.id) ? 'ring-2 ring-purple-400 shadow-purple-100' : ''
                }`}
              >
                {/* 摘要行 */}
                <div
                  onClick={() => setExpandedId(isExpanded ? null : word.id)}
                  className="p-4 cursor-pointer hover:bg-gray-50 transition"
                >
                  <div className="flex items-center gap-3">
                    {/* 选择框 */}
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleSelect(word.id); }}
                      className={`w-6 h-6 rounded-lg border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                        selectedIds.has(word.id)
                          ? 'bg-purple-500 border-purple-500 text-white'
                          : 'border-gray-300 hover:border-purple-400'
                      }`}
                    >
                      {selectedIds.has(word.id) && <span className="text-xs">✓</span>}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-lg font-bold text-gray-800">{word.word}</span>
                        {word.phonetic_us && (
                          <span className="text-xs text-gray-400">{word.phonetic_us}</span>
                        )}
                      </div>
                      <div className="text-sm text-gray-500 truncate mt-0.5">
                        {meanings.map(m => `${m.pos} ${m.def}`).join('；')}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-2 shrink-0">
                      <span className="text-xs text-amber-500">{masteryStars(word.mastery_level)}</span>
                      <span className="text-gray-300">{isExpanded ? '▲' : '▼'}</span>
                    </div>
                  </div>
                </div>

                {/* 展开详情 */}
                {isExpanded && (
                  <div className="px-4 pb-4 border-t border-gray-100 pt-3 space-y-3">
                    {word.phonetic_uk && (
                      <div className="text-sm text-gray-400">
                        美 {word.phonetic_us} | 英 {word.phonetic_uk}
                      </div>
                    )}

                    {/* 释义 */}
                    <div>
                      <div className="text-xs text-gray-400 mb-1">释义</div>
                      {meanings.map((m, i) => (
                        <div key={i} className="text-sm text-gray-700">
                          <span className="text-blue-500 mr-1">{m.pos}</span>{m.def}
                        </div>
                      ))}
                    </div>

                    {/* 词根 */}
                    {word.word_roots && (
                      <div>
                        <div className="text-xs text-gray-400 mb-1">词根词缀</div>
                        <div className="text-sm text-gray-600 bg-blue-50 rounded-lg px-3 py-2">
                          {word.word_roots}
                        </div>
                      </div>
                    )}

                    {/* 例句 */}
                    {examples.length > 0 && (
                      <div>
                        <div className="text-xs text-gray-400 mb-1">例句</div>
                        {examples.map((ex, i) => (
                          <div key={i} className="text-sm mb-1">
                            <div className="text-gray-700">{ex.en}</div>
                            <div className="text-gray-400">{ex.zh}</div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 近义词/反义词 */}
                    <div className="flex gap-4 text-sm">
                      {word.synonyms && (
                        <div className="flex-1">
                          <span className="text-gray-400">近义词: </span>
                          <span className="text-green-600">{word.synonyms}</span>
                        </div>
                      )}
                      {word.antonyms && (
                        <div className="flex-1">
                          <span className="text-gray-400">反义词: </span>
                          <span className="text-red-500">{word.antonyms}</span>
                        </div>
                      )}
                    </div>

                    {/* 统计和操作 */}
                    <div className="flex items-center justify-between pt-2">
                      <span className="text-xs text-gray-400">复习{word.review_count}次 | 正确{word.correct_count}次</span>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            startReviewWithWords([word]);
                          }}
                          className="text-xs text-purple-500 font-medium hover:text-purple-700"
                        >
                          复习
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(word.id);
                          }}
                          className="text-xs text-red-400 hover:text-red-600"
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* 分页 */}
        {tab === 'all' && total > 20 && (
          <div className="flex justify-center gap-3 mt-4">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded-lg bg-white text-gray-600 disabled:opacity-30"
            >
              上一页
            </button>
            <span className="py-1 text-sm text-gray-400">
              {page} / {Math.ceil(total / 20)}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page * 20 >= total}
              className="px-3 py-1 rounded-lg bg-white text-gray-600 disabled:opacity-30"
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
