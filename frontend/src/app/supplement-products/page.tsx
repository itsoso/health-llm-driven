'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api/client';

interface Ingredient {
  name: string;
  form?: string;
  amount: string;
  daily_value_pct?: number | null;
}

interface Product {
  id: number;
  name: string;
  brand: string;
  category?: string;
  description?: string;
  serving_size?: string;
  servings_per_container?: number;
  container_count?: number;
  ingredients?: Ingredient[];
  price_cny?: number;
  price_per_serving?: number;
  purchase_url?: string;
  platform?: string;
  image_url?: string;
  certifications?: string[];
  capsule_type?: string;
  usage_advice?: string;
  precautions?: string;
  gene_relevance?: Array<{ gene: string; genotype: string; relevance: string }>;
  health_tags?: string[];
  rating?: number;
  review_count?: number;
}

export default function SupplementProductsPage() {
  const router = useRouter();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [compareIds, setCompareIds] = useState<Set<number>>(new Set());
  const [showCompare, setShowCompare] = useState(false);
  const [compareData, setCompareData] = useState<any>(null);

  useEffect(() => {
    loadProducts();
  }, [search, selectedCategory]);

  const loadProducts = async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (selectedCategory) params.set('category', selectedCategory);
      const res = await api.get(`/supplements/products?${params}`);
      setProducts(res.data.items || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const toggleCompare = (id: number) => {
    setCompareIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else if (next.size < 5) next.add(id);
      return next;
    });
  };

  const doCompare = async () => {
    if (compareIds.size < 2) return;
    try {
      const ids = Array.from(compareIds).join(',');
      const res = await api.get(`/supplements/products/compare/list?ids=${ids}`);
      setCompareData(res.data);
      setShowCompare(true);
    } catch (e) {
      console.error(e);
    }
  };

  const categories = [
    { value: '', label: '全部' },
    { value: 'vitamin', label: '维生素' },
    { value: 'mineral', label: '矿物质' },
    { value: 'antioxidant', label: '抗氧化' },
    { value: 'amino', label: '氨基酸' },
    { value: 'herb', label: '草本' },
    { value: 'other', label: '其他' },
  ];

  const categoryColors: Record<string, string> = {
    vitamin: 'bg-amber-100 text-amber-700',
    mineral: 'bg-blue-100 text-blue-700',
    antioxidant: 'bg-purple-100 text-purple-700',
    amino: 'bg-emerald-100 text-emerald-700',
    herb: 'bg-green-100 text-green-700',
    other: 'bg-gray-100 text-gray-700',
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <button onClick={() => router.back()} className="text-gray-400 hover:text-gray-600">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" /></svg>
              </button>
              <h1 className="text-lg font-bold text-gray-800">💊 补剂产品库</h1>
              <span className="text-xs text-gray-400">{products.length} 款产品</span>
            </div>
            {compareIds.size >= 2 && (
              <button onClick={doCompare}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-500 rounded-xl hover:bg-indigo-600 active:scale-95 transition-all">
                对比 ({compareIds.size})
              </button>
            )}
          </div>
          {/* Search + Filter */}
          <div className="flex gap-2">
            <input type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="搜索品牌或产品名..."
              className="flex-1 px-4 py-2 rounded-xl border border-gray-200 bg-gray-50 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200" />
            <div className="flex gap-1 overflow-x-auto">
              {categories.map(c => (
                <button key={c.value} onClick={() => setSelectedCategory(c.value)}
                  className={`px-3 py-2 rounded-xl text-xs font-medium whitespace-nowrap transition-colors ${
                    selectedCategory === c.value ? 'bg-indigo-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}>
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Product List */}
      <div className="max-w-5xl mx-auto px-4 py-4 space-y-3">
        {loading ? (
          <div className="text-center py-20 text-gray-400">加载中...</div>
        ) : products.length === 0 ? (
          <div className="text-center py-20 text-gray-400">没有找到产品</div>
        ) : products.map(p => {
          const isExpanded = expandedId === p.id;
          const isComparing = compareIds.has(p.id);
          return (
            <div key={p.id} className={`bg-white rounded-2xl border shadow-sm overflow-hidden transition-all ${isComparing ? 'border-indigo-300 ring-2 ring-indigo-100' : 'border-gray-100'}`}>
              {/* Card Header */}
              <div className="p-4 cursor-pointer" onClick={() => setExpandedId(isExpanded ? null : p.id)}>
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base font-bold text-gray-800">{p.brand}</span>
                      {p.category && (
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${categoryColors[p.category] || 'bg-gray-100 text-gray-600'}`}>
                          {categories.find(c => c.value === p.category)?.label || p.category}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-gray-600">{p.name}</div>
                    {/* Tags */}
                    {p.health_tags && p.health_tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {p.health_tags.slice(0, 4).map(tag => (
                          <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-100">{tag}</span>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Price + Rating */}
                  <div className="text-right shrink-0 ml-4">
                    {p.price_cny && (
                      <div className="text-lg font-bold text-gray-800">¥{Number(p.price_cny).toFixed(0)}</div>
                    )}
                    {p.price_per_serving && (
                      <div className="text-xs text-gray-400">¥{Number(p.price_per_serving).toFixed(2)}/份</div>
                    )}
                    {p.rating && (
                      <div className="text-xs text-amber-500 mt-1">{'★'.repeat(Math.round(p.rating))} {p.rating}</div>
                    )}
                    {p.review_count && (
                      <div className="text-[10px] text-gray-400">{p.review_count.toLocaleString()} 评价</div>
                    )}
                  </div>
                </div>
                {/* Quick Info Row */}
                <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                  {p.container_count && <span>{p.container_count}粒</span>}
                  {p.serving_size && <span>{p.serving_size}</span>}
                  {p.capsule_type && <span>{p.capsule_type === 'vegetarian' ? '素食胶囊' : p.capsule_type === 'softgel' ? '软胶囊' : p.capsule_type === 'liquid' ? '液体胶囊' : p.capsule_type}</span>}
                  {p.certifications?.map(c => <span key={c} className="text-emerald-500">{c}</span>)}
                </div>
              </div>

              {/* Expanded Detail */}
              {isExpanded && (
                <div className="border-t border-gray-100 px-4 py-4 space-y-4 bg-gray-50/50">
                  {/* Description */}
                  {p.description && <p className="text-sm text-gray-600 leading-6">{p.description}</p>}

                  {/* Ingredients Table */}
                  {p.ingredients && p.ingredients.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-700 mb-2">成分表</h4>
                      <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
                        <table className="w-full text-sm">
                          <thead className="bg-gray-50">
                            <tr>
                              <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">成分</th>
                              <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">形式</th>
                              <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">含量</th>
                              <th className="text-right px-3 py-2 text-xs font-medium text-gray-500">%DV</th>
                            </tr>
                          </thead>
                          <tbody>
                            {p.ingredients.map((ing, i) => (
                              <tr key={i} className="border-t border-gray-50">
                                <td className="px-3 py-2 text-gray-800 font-medium">{ing.name}</td>
                                <td className="px-3 py-2 text-gray-500 text-xs">{ing.form || '-'}</td>
                                <td className="px-3 py-2 text-right text-gray-700">{ing.amount}</td>
                                <td className="px-3 py-2 text-right text-gray-400">
                                  {ing.daily_value_pct != null ? `${ing.daily_value_pct}%` : '**'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Usage & Precautions */}
                  <div className="grid grid-cols-2 gap-3">
                    {p.usage_advice && (
                      <div className="bg-emerald-50 rounded-xl p-3">
                        <h4 className="text-xs font-semibold text-emerald-700 mb-1">服用建议</h4>
                        <p className="text-xs text-emerald-600 leading-5">{p.usage_advice}</p>
                      </div>
                    )}
                    {p.precautions && (
                      <div className="bg-amber-50 rounded-xl p-3">
                        <h4 className="text-xs font-semibold text-amber-700 mb-1">注意事项</h4>
                        <p className="text-xs text-amber-600 leading-5">{p.precautions}</p>
                      </div>
                    )}
                  </div>

                  {/* Gene Relevance */}
                  {p.gene_relevance && p.gene_relevance.length > 0 && (
                    <div className="bg-indigo-50 rounded-xl p-3">
                      <h4 className="text-xs font-semibold text-indigo-700 mb-1">🧬 基因关联</h4>
                      {p.gene_relevance.map((g, i) => (
                        <div key={i} className="text-xs text-indigo-600 leading-5">
                          <span className="font-mono font-semibold">{g.gene} {g.genotype}</span>: {g.relevance}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2">
                    <button onClick={(e) => { e.stopPropagation(); toggleCompare(p.id); }}
                      className={`px-3 py-2 rounded-xl text-xs font-medium transition-colors ${isComparing ? 'bg-indigo-500 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
                      {isComparing ? '已加入对比' : '加入对比'}
                    </button>
                    {p.purchase_url && (
                      <a href={p.purchase_url} target="_blank" rel="noopener noreferrer"
                        className="px-3 py-2 rounded-xl text-xs font-medium bg-orange-500 text-white hover:bg-orange-600 transition-colors">
                        去 {p.platform === 'iherb' ? 'iHerb' : p.platform} 购买 →
                      </a>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Compare Modal */}
      {showCompare && compareData && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={() => setShowCompare(false)}>
          <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[85vh] overflow-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-gray-800">产品对比</h2>
              <button onClick={() => setShowCompare(false)} className="text-gray-400 hover:text-gray-600 text-lg">×</button>
            </div>
            {/* Product headers */}
            <div className="grid gap-3" style={{ gridTemplateColumns: `120px repeat(${compareData.products.length}, 1fr)` }}>
              <div />
              {compareData.products.map((p: Product) => (
                <div key={p.id} className="text-center">
                  <div className="text-sm font-bold text-gray-800">{p.brand}</div>
                  <div className="text-xs text-gray-500">{p.name}</div>
                  {p.price_cny && <div className="text-sm font-semibold text-gray-700 mt-1">¥{Number(p.price_cny).toFixed(0)}</div>}
                  {p.price_per_serving && <div className="text-[10px] text-gray-400">¥{Number(p.price_per_serving).toFixed(2)}/份</div>}
                </div>
              ))}
            </div>
            {/* Comparison rows */}
            <div className="mt-4 border-t border-gray-100">
              {compareData.comparison.map((row: any, i: number) => (
                <div key={i} className={`grid gap-3 py-2 px-1 ${i % 2 === 0 ? 'bg-gray-50' : ''}`}
                  style={{ gridTemplateColumns: `120px repeat(${compareData.products.length}, 1fr)` }}>
                  <div className="text-xs font-medium text-gray-700">{row.ingredient}</div>
                  {compareData.products.map((p: Product) => {
                    const cell = row[`product_${p.id}`];
                    return (
                      <div key={p.id} className="text-center">
                        <div className={`text-xs font-medium ${cell?.amount === '-' ? 'text-gray-300' : 'text-gray-800'}`}>
                          {cell?.amount || '-'}
                        </div>
                        {cell?.form && cell.form !== '-' && <div className="text-[10px] text-gray-400">{cell.form}</div>}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
