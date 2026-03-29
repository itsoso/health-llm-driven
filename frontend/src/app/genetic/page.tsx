'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const CATEGORIES = [
  { key: 'nutrition', label: '营养代谢', icon: '🥗' },
  { key: 'exercise', label: '运动能力', icon: '🏃' },
  { key: 'drug_sensitivity', label: '药物敏感', icon: '💊' },
  { key: 'disease_risk', label: '疾病风险', icon: '🩺' },
  { key: 'sleep', label: '睡眠特质', icon: '😴' },
];

const RISK_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-700 border-red-300',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  low: 'bg-green-100 text-green-700 border-green-300',
  info: 'bg-blue-100 text-blue-700 border-blue-300',
};

const RISK_LABELS: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险', info: '参考' };

const GENE_TEMPLATES: Record<string, Array<{gene: string; variant: string; options: Array<{genotype: string; label: string; risk: string}>}>> = {
  nutrition: [
    { gene: "MTHFR", variant: "C677T", options: [
      { genotype: "CC", label: "叶酸代谢正常", risk: "low" },
      { genotype: "CT", label: "叶酸代谢轻度减弱", risk: "medium" },
      { genotype: "TT", label: "叶酸代谢显著减弱", risk: "high" },
    ]},
    { gene: "CYP1A2", variant: "咖啡因代谢", options: [
      { genotype: "AA", label: "快速代谢", risk: "low" },
      { genotype: "AC", label: "中等代谢", risk: "info" },
      { genotype: "CC", label: "慢速代谢", risk: "medium" },
    ]},
    { gene: "LCT", variant: "乳糖耐受", options: [
      { genotype: "CC", label: "乳糖不耐受", risk: "medium" },
      { genotype: "CT", label: "部分耐受", risk: "low" },
      { genotype: "TT", label: "乳糖耐受", risk: "low" },
    ]},
    { gene: "ALDH2", variant: "酒精代谢", options: [
      { genotype: "GG", label: "酒精代谢正常", risk: "low" },
      { genotype: "GA", label: "酒精代谢减弱", risk: "medium" },
      { genotype: "AA", label: "酒精代谢缺陷", risk: "high" },
    ]},
    { gene: "VDR", variant: "维生素D需求", options: [
      { genotype: "正常", label: "维D需求正常", risk: "low" },
      { genotype: "增高", label: "维D需求增高", risk: "medium" },
    ]},
  ],
  exercise: [
    { gene: "ACTN3", variant: "R577X", options: [
      { genotype: "RR", label: "爆发力型", risk: "info" },
      { genotype: "RX", label: "混合型", risk: "info" },
      { genotype: "XX", label: "耐力型", risk: "info" },
    ]},
    { gene: "ACE", variant: "I/D", options: [
      { genotype: "II", label: "耐力倾向", risk: "info" },
      { genotype: "ID", label: "均衡型", risk: "info" },
      { genotype: "DD", label: "爆发力倾向", risk: "info" },
    ]},
    { gene: "PPARGC1A", variant: "有氧能力", options: [
      { genotype: "正常", label: "有氧能力正常", risk: "info" },
      { genotype: "增强", label: "有氧能力较强", risk: "info" },
      { genotype: "偏弱", label: "有氧能力偏弱", risk: "low" },
    ]},
  ],
  drug_sensitivity: [
    { gene: "CYP2C19", variant: "氯吡格雷代谢", options: [
      { genotype: "*1/*1", label: "正常代谢", risk: "low" },
      { genotype: "*1/*2", label: "中间代谢", risk: "medium" },
      { genotype: "*2/*2", label: "慢代谢", risk: "high" },
      { genotype: "*1/*17", label: "超快代谢", risk: "medium" },
    ]},
    { gene: "CYP2D6", variant: "止痛药代谢", options: [
      { genotype: "正常", label: "正常代谢", risk: "low" },
      { genotype: "慢代谢", label: "慢代谢(需调整剂量)", risk: "high" },
      { genotype: "超快代谢", label: "超快代谢(需调整剂量)", risk: "medium" },
    ]},
    { gene: "SLCO1B1", variant: "他汀类药物", options: [
      { genotype: "正常", label: "他汀耐受正常", risk: "low" },
      { genotype: "敏感", label: "他汀肌病风险增高", risk: "high" },
    ]},
    { gene: "HLA-B*5801", variant: "别嘌醇过敏", options: [
      { genotype: "阴性", label: "别嘌醇可使用", risk: "low" },
      { genotype: "阳性", label: "别嘌醇禁用(严重过敏)", risk: "high" },
    ]},
  ],
  disease_risk: [
    { gene: "APOE", variant: "e4", options: [
      { genotype: "e3/e3", label: "标准风险", risk: "low" },
      { genotype: "e3/e4", label: "心血管/AD风险轻度增高", risk: "medium" },
      { genotype: "e4/e4", label: "心血管/AD风险显著增高", risk: "high" },
    ]},
    { gene: "TCF7L2", variant: "2型糖尿病", options: [
      { genotype: "CC", label: "标准风险", risk: "low" },
      { genotype: "CT", label: "糖尿病风险轻度增高", risk: "medium" },
      { genotype: "TT", label: "糖尿病风险增高", risk: "high" },
    ]},
    { gene: "FTO", variant: "肥胖倾向", options: [
      { genotype: "TT", label: "标准体重倾向", risk: "low" },
      { genotype: "AT", label: "轻度肥胖倾向", risk: "medium" },
      { genotype: "AA", label: "肥胖倾向增高", risk: "high" },
    ]},
  ],
  sleep: [
    { gene: "CLOCK", variant: "昼夜节律", options: [
      { genotype: "TT", label: "标准作息型", risk: "info" },
      { genotype: "TC", label: "轻度夜猫子", risk: "low" },
      { genotype: "CC", label: "夜猫子型", risk: "medium" },
    ]},
    { gene: "PER2", variant: "睡眠需求", options: [
      { genotype: "正常", label: "标准睡眠需求", risk: "info" },
      { genotype: "增高", label: "睡眠需求偏高", risk: "low" },
    ]},
    { gene: "ADA", variant: "深度睡眠", options: [
      { genotype: "GG", label: "深睡正常", risk: "info" },
      { genotype: "GA", label: "深睡偏少", risk: "medium" },
    ]},
  ],
};

type Variant = {
  id: number; category: string; gene_name: string; variant_name: string;
  genotype: string; result_label: string; risk_level: string; description?: string;
};
type Profile = { id: number; test_provider: string; test_date: string; report_id?: string; notes?: string };

function GeneticContent() {
  const { isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('nutrition');
  const [showAddTemplate, setShowAddTemplate] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<number | null>(null);
  const [selectedGenotype, setSelectedGenotype] = useState<string | null>(null);
  const [showProfileForm, setShowProfileForm] = useState(false);
  const [pdfUploading, setPdfUploading] = useState(false);
  const [pdfStatus, setPdfStatus] = useState('');
  const [profileForm, setProfileForm] = useState({ test_provider: '', test_date: '', report_id: '', notes: '' });
  const [crossAnalysis, setCrossAnalysis] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  useEffect(() => { document.title = '基因数据 | 健康管理'; }, []);

  const { data: profilesData } = useQuery({
    queryKey: ['genetic-profiles'],
    queryFn: () => api.get('/genetic/profiles/me'),
    enabled: isAuthenticated,
  });

  const { data: variantsData, isLoading } = useQuery({
    queryKey: ['genetic-variants', activeTab],
    queryFn: () => api.get(`/genetic/variants/me?category=${activeTab}`),
    enabled: isAuthenticated,
  });

  const profiles: Profile[] = profilesData?.data || [];
  const variants: Variant[] = variantsData?.data || [];
  const latestProfile = profiles.length > 0 ? profiles[0] : null;

  const createProfileMutation = useMutation({
    mutationFn: (data: typeof profileForm) => api.post('/genetic/profiles', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['genetic-profiles'] });
      setShowProfileForm(false);
      setProfileForm({ test_provider: '', test_date: '', report_id: '', notes: '' });
    },
  });

  const addVariantMutation = useMutation({
    mutationFn: (data: Record<string, unknown>[]) => api.post('/genetic/variants/batch', { variants: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['genetic-variants'] });
      setShowAddTemplate(false);
      setSelectedTemplate(null);
      setSelectedGenotype(null);
    },
  });

  const deleteVariantMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/genetic/variants/${id}`),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['genetic-variants'] }); },
  });

  const templates = GENE_TEMPLATES[activeTab] || [];

  const handleAddFromTemplate = () => {
    if (selectedTemplate === null || !selectedGenotype || !latestProfile) return;
    const tpl = templates[selectedTemplate];
    const opt = tpl.options.find(o => o.genotype === selectedGenotype);
    if (!opt) return;
    addVariantMutation.mutate([{
      profile_id: latestProfile.id, category: activeTab, gene_name: tpl.gene,
      variant_name: tpl.variant, genotype: opt.genotype, result_label: opt.label, risk_level: opt.risk,
    }]);
  };

  const handleCrossAnalysis = async () => {
    setAnalysisLoading(true);
    setCrossAnalysis(null);
    try {
      const res = await api.get('/genetic/cross-analysis/me');
      setCrossAnalysis(res.data?.analysis || res.data?.message || JSON.stringify(res.data));
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setCrossAnalysis('分析失败: ' + (err.response?.data?.detail || '请稍后重试'));
    } finally { setAnalysisLoading(false); }
  };

  return (
    <main className="min-h-screen p-4 md:p-8 bg-gradient-to-br from-indigo-50 via-white to-purple-50">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="bg-gradient-to-r from-teal-600 to-emerald-600 rounded-2xl shadow-2xl p-6 mb-6 text-white">
          <h1 className="text-2xl font-bold mb-2">🧬 基因数据</h1>
          {latestProfile ? (
            <div className="text-teal-100 text-sm">
              检测机构: {latestProfile.test_provider} | 检测日期: {latestProfile.test_date}
              {latestProfile.report_id && ` | 报告编号: ${latestProfile.report_id}`}
            </div>
          ) : (
            <p className="text-teal-100 text-sm">尚未创建基因档案</p>
          )}
          <div className="flex gap-2 mt-3">
            <button onClick={() => setShowProfileForm(!showProfileForm)}
              className="px-4 py-1.5 bg-white/20 hover:bg-white/30 rounded-lg text-sm font-medium transition border border-white/30">
              {latestProfile ? '新建档案' : '创建档案'}
            </button>
          </div>
        </div>

        {/* Profile creation form */}
        {showProfileForm && (
          <div className="bg-white rounded-xl shadow-sm p-5 mb-6 border border-gray-200">
            <h3 className="font-semibold text-gray-800 mb-1">新建基因档案</h3>
            <p className="text-xs text-gray-500 mb-4">从你的华大基因/微基因检测报告中录入基因位点数据，AI 会结合这些数据给出个性化建议。</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">检测机构 *</label>
                <select value={profileForm.test_provider}
                  onChange={e => setProfileForm({...profileForm, test_provider: e.target.value})}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-teal-500 focus:border-transparent">
                  <option value="">选择检测机构</option>
                  <option value="华大基因">华大基因</option>
                  <option value="微基因">微基因 (WeGene)</option>
                  <option value="23andMe">23andMe</option>
                  <option value="圆基因">圆基因</option>
                  <option value="其他">其他</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">检测日期 *</label>
                <input type="date" value={profileForm.test_date}
                  onChange={e => setProfileForm({...profileForm, test_date: e.target.value})}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-teal-500 focus:border-transparent" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">报告编号</label>
                <input type="text" placeholder="选填" value={profileForm.report_id}
                  onChange={e => setProfileForm({...profileForm, report_id: e.target.value})}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-teal-500 focus:border-transparent" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">备注</label>
                <input type="text" placeholder="选填" value={profileForm.notes}
                  onChange={e => setProfileForm({...profileForm, notes: e.target.value})}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:ring-2 focus:ring-teal-500 focus:border-transparent" />
              </div>
            </div>
            {/* 文件上传区 */}
            <div className="mt-4 p-4 bg-gray-50 rounded-xl border border-dashed border-gray-300">
              <p className="text-sm font-medium text-gray-700 mb-2">📄 上传检测数据（推荐）</p>
              <p className="text-xs text-gray-500 mb-3">支持微基因/23andMe 的 TXT 原始数据（秒级解析）或 PDF 报告（AI 提取，较慢）。</p>
              <input
                type="file"
                accept=".txt,.pdf,.csv"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  if (!profileForm.test_provider || !profileForm.test_date) {
                    alert('请先选择检测机构和日期');
                    return;
                  }
                  const isTxt = file.name.endsWith('.txt') || file.name.endsWith('.csv');
                  setPdfUploading(true);
                  setPdfStatus(isTxt ? '正在解析原始数据...' : '正在上传 PDF...');

                  if (isTxt) {
                    // TXT: 直接读文本，秒级解析
                    const reader = new FileReader();
                    reader.onload = async () => {
                      try {
                        const res = await api.post('/genetic/profiles/upload-txt', {
                          test_provider: profileForm.test_provider,
                          test_date: profileForm.test_date,
                          txt_content: reader.result as string,
                          notes: profileForm.notes,
                        });
                        setPdfUploading(false);
                        setPdfStatus(`解析完成！匹配到 ${res.data.matched_count} 个健康相关基因位点`);
                        setShowProfileForm(false);
                        queryClient.invalidateQueries({ queryKey: ['genetic-profiles'] });
                        queryClient.invalidateQueries({ queryKey: ['genetic-variants'] });
                      } catch (err: any) {
                        setPdfUploading(false);
                        setPdfStatus('解析失败: ' + (err.response?.data?.detail || err.message));
                      }
                    };
                    reader.readAsText(file);
                  } else {
                    // PDF: base64 上传，AI 异步提取
                    const reader = new FileReader();
                    reader.onload = async () => {
                      const base64 = (reader.result as string).split(',')[1];
                      try {
                        const res = await api.post('/genetic/profiles/upload-pdf', {
                          test_provider: profileForm.test_provider,
                          test_date: profileForm.test_date,
                          pdf_base64: base64,
                          notes: profileForm.notes,
                        });
                        setPdfStatus(`AI 正在提取... (ID: ${res.data.id})`);
                        const pollId = res.data.id;
                        const poll = setInterval(async () => {
                          try {
                            const detail = await api.get(`/genetic/profiles/${pollId}`);
                            const variants = detail.data.variants || [];
                            if (variants.length > 0 || (detail.data.notes && detail.data.notes.includes('完成'))) {
                              clearInterval(poll);
                              setPdfUploading(false);
                              setPdfStatus(`提取完成！发现 ${variants.length} 个基因位点`);
                              setShowProfileForm(false);
                              queryClient.invalidateQueries({ queryKey: ['genetic-profiles'] });
                              queryClient.invalidateQueries({ queryKey: ['genetic-variants'] });
                            } else if (detail.data.notes && detail.data.notes.includes('失败')) {
                              clearInterval(poll);
                              setPdfUploading(false);
                              setPdfStatus('提取失败: ' + detail.data.notes);
                            }
                          } catch { /* continue polling */ }
                        }, 3000);
                        setTimeout(() => { clearInterval(poll); setPdfUploading(false); }, 300000);
                      } catch (err: any) {
                        setPdfUploading(false);
                        setPdfStatus('上传失败: ' + (err.response?.data?.detail || err.message));
                      }
                    };
                    reader.readAsDataURL(file);
                  }
                }}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-teal-50 file:text-teal-700 hover:file:bg-teal-100"
                disabled={pdfUploading}
              />
              {pdfUploading && (
                <div className="mt-2 flex items-center gap-2 text-sm text-teal-700">
                  <div className="animate-spin h-4 w-4 border-2 border-teal-500 border-t-transparent rounded-full" />
                  {pdfStatus || 'AI 正在提取基因位点...'}
                </div>
              )}
              {!pdfUploading && pdfStatus && (
                <p className="mt-2 text-sm text-teal-700">{pdfStatus}</p>
              )}
            </div>

            <div className="flex gap-2 mt-4">
              <button onClick={() => createProfileMutation.mutate(profileForm)}
                disabled={!profileForm.test_provider || !profileForm.test_date || createProfileMutation.isPending || pdfUploading}
                className="px-5 py-2 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700 disabled:opacity-50 transition">
                {createProfileMutation.isPending ? '保存中...' : '手动录入模式'}
              </button>
              <button onClick={() => setShowProfileForm(false)}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200 transition">
                取消
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-3">上传 PDF 自动提取，或点"手动录入模式"逐项选择。</p>
          </div>
        )}

        {/* Category tabs */}
        <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
          {CATEGORIES.map(cat => (
            <button key={cat.key} onClick={() => { setActiveTab(cat.key); setShowAddTemplate(false); }}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition ${
                activeTab === cat.key
                  ? 'bg-teal-600 text-white shadow-md'
                  : 'bg-white text-gray-600 hover:bg-gray-50 border border-gray-200'
              }`}>
              <span>{cat.icon}</span> {cat.label}
            </button>
          ))}
        </div>

        {/* Variant cards */}
        {isLoading ? (
          <div className="text-center py-12 text-gray-500">加载中...</div>
        ) : variants.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border border-gray-200 mb-4">
            <p className="text-gray-400 text-lg mb-2">暂无{CATEGORIES.find(c => c.key === activeTab)?.label}数据</p>
            {latestProfile ? (
              <button onClick={() => { setShowAddTemplate(true); setSelectedTemplate(null); setSelectedGenotype(null); }}
                className="mt-2 px-5 py-2 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700 transition">
                + 从报告中录入
              </button>
            ) : (
              <p className="text-gray-400 text-sm">请先在上方创建基因档案</p>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            {variants.map((v: Variant) => (
              <div key={v.id} className={`rounded-xl p-4 border ${RISK_COLORS[v.risk_level] || RISK_COLORS.info}`}>
                <div className="flex justify-between items-start">
                  <div>
                    <span className="font-bold text-base">{v.gene_name}</span>
                    <span className="text-sm ml-2 opacity-70">{v.variant_name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-white/60 font-medium">
                      {RISK_LABELS[v.risk_level] || v.risk_level}
                    </span>
                    <button onClick={() => deleteVariantMutation.mutate(v.id)}
                      className="text-xs opacity-40 hover:opacity-100 transition" title="删除">
                      x
                    </button>
                  </div>
                </div>
                <div className="mt-2 text-sm font-medium">{v.genotype} - {v.result_label}</div>
                {v.description && <p className="mt-1 text-xs opacity-70">{v.description}</p>}
              </div>
            ))}
          </div>
        )}

        {/* Add from template */}
        {latestProfile && (
          <div className="mb-6">
            <button onClick={() => { setShowAddTemplate(!showAddTemplate); setSelectedTemplate(null); setSelectedGenotype(null); }}
              className="px-4 py-2 bg-white border border-teal-300 text-teal-700 rounded-lg text-sm font-medium hover:bg-teal-50 transition">
              + 从模板添加
            </button>

            {showAddTemplate && (
              <div className="bg-white rounded-xl shadow-sm p-5 mt-3 border border-gray-200">
                <h4 className="font-semibold text-gray-800 mb-3">选择基因位点</h4>
                <div className="flex flex-wrap gap-2 mb-4">
                  {templates.map((tpl, idx) => (
                    <button key={tpl.gene} onClick={() => { setSelectedTemplate(idx); setSelectedGenotype(null); }}
                      className={`px-3 py-1.5 rounded-lg text-sm border transition ${
                        selectedTemplate === idx ? 'bg-teal-100 border-teal-400 text-teal-800' : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                      }`}>
                      {tpl.gene} ({tpl.variant})
                    </button>
                  ))}
                </div>

                {selectedTemplate !== null && (
                  <div>
                    <h5 className="text-sm font-medium text-gray-700 mb-2">选择基因型</h5>
                    <div className="flex flex-col gap-2">
                      {templates[selectedTemplate].options.map(opt => (
                        <label key={opt.genotype}
                          className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition ${
                            selectedGenotype === opt.genotype ? 'border-teal-400 bg-teal-50' : 'border-gray-200 hover:bg-gray-50'
                          }`}>
                          <input type="radio" name="genotype" value={opt.genotype} checked={selectedGenotype === opt.genotype}
                            onChange={() => setSelectedGenotype(opt.genotype)} className="accent-teal-600" />
                          <div className="flex-1">
                            <span className="font-medium text-sm">{opt.genotype}</span>
                            <span className="ml-2 text-sm text-gray-600">{opt.label}</span>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${RISK_COLORS[opt.risk]}`}>
                            {RISK_LABELS[opt.risk]}
                          </span>
                        </label>
                      ))}
                    </div>
                    <button onClick={handleAddFromTemplate}
                      disabled={!selectedGenotype || addVariantMutation.isPending}
                      className="mt-3 px-4 py-2 bg-teal-600 text-white rounded-lg text-sm font-medium hover:bg-teal-700 disabled:opacity-50 transition">
                      {addVariantMutation.isPending ? '保存中...' : '添加'}
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* AI Cross Analysis */}
        <div className="bg-white rounded-xl shadow-sm p-5 border border-gray-200">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-800">🤖 AI 交叉分析</h3>
            <button onClick={handleCrossAnalysis} disabled={analysisLoading}
              className="px-4 py-2 bg-gradient-to-r from-teal-600 to-emerald-600 text-white rounded-lg text-sm font-medium hover:from-teal-700 hover:to-emerald-700 disabled:opacity-50 transition">
              {analysisLoading ? '分析中...' : '开始分析'}
            </button>
          </div>
          <p className="text-xs text-gray-500 mb-3">综合基因数据与当前健康状态，给出个性化建议</p>
          {crossAnalysis && (
            <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
              {crossAnalysis}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

export default function GeneticPage() {
  return (
    <ProtectedRoute>
      <GeneticContent />
    </ProtectedRoute>
  );
}
