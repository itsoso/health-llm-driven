'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';
interface Product { id: number; name: string; brand: string; category?: string | null; description?: string | null; }
interface ProductList { items: Product[]; total: number; }
const pageSize = 20;
function ProductContent() {
  const { user } = useAuth();
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const products = useQuery({
    queryKey: ['supplement-products', user?.id, search, page],
    queryFn: async () => (await api.get<ProductList>('/supplements/products', { params: { search: search || undefined, limit: pageSize, offset: page * pageSize } })).data,
    enabled: !!user?.id,
  });
  return <main className="min-h-screen bg-gray-50 p-4 md:p-8"><div className="max-w-5xl mx-auto">
    <h1 className="text-2xl font-bold mb-2">补剂产品库</h1>
    <p className="text-gray-600 mb-6">浏览产品资料，个人补剂记录可在<Link href="/supplements" className="text-indigo-600 underline">补剂管理</Link>中维护。</p>
    <form className="flex gap-2 mb-6" onSubmit={event => { event.preventDefault(); setSearch(input.trim()); setPage(0); }}>
      <input aria-label="产品名称或品牌" placeholder="搜索产品名称或品牌" value={input} onChange={event => setInput(event.target.value)} className="border rounded-lg px-3 py-2 min-w-0 flex-1" />
      <button className="bg-indigo-600 text-white rounded-lg px-5 py-2" type="submit">搜索</button>
    </form>
    {products.isLoading ? <p role="status">加载产品库…</p> : products.isError ? <div role="alert" className="bg-red-50 text-red-800 p-4 rounded-xl">产品库加载失败。<button className="underline ml-2" onClick={() => products.refetch()}>重试产品库</button></div>
      : !products.data?.items.length ? <p className="bg-white p-6 rounded-xl text-gray-500">{search ? '未找到匹配产品' : '产品库暂无数据'}</p>
      : <div className="grid md:grid-cols-2 gap-4">{products.data.items.map(product => <article key={product.id} className="bg-white rounded-xl p-5 shadow-sm">
        <h2 className="text-lg font-semibold">{product.name}</h2><p className="text-gray-600 mt-1">{product.brand}</p>
        {product.category && <p className="text-sm text-gray-500 mt-2">分类：{product.category}</p>}
        {product.description && <p className="text-gray-700 mt-3 whitespace-pre-wrap">{product.description}</p>}
      </article>)}</div>}
    <div className="flex items-center justify-between mt-6">
      <button disabled={page === 0 || products.isFetching} onClick={() => setPage(value => value - 1)} className="px-4 py-2 rounded-lg bg-white disabled:opacity-40">上一页</button>
      <span className="text-gray-600">第 {page + 1} 页</span>
      <button disabled={!products.data || (page + 1) * pageSize >= products.data.total || products.isFetching || products.isError} onClick={() => setPage(value => value + 1)} className="px-4 py-2 rounded-lg bg-white disabled:opacity-40">下一页</button>
    </div>
  </div></main>;
}
export default function SupplementProductsPage() { return <ProtectedRoute><ProductContent /></ProtectedRoute>; }
