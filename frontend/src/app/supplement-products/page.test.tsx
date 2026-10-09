import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import ProductPage from './page';
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 7 } }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
let client: QueryClient;
beforeEach(() => { client = new QueryClient({ defaultOptions: { queries: { retry: false } } }); });
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); });
const show = () => render(<QueryClientProvider client={client}><ProductPage /></QueryClientProvider>);
it('supports bounded search and resets pagination for a new search', async () => {
  const read = vi.spyOn(api, 'get').mockResolvedValue({ data: { items: [{ id: 1, name: 'Synthetic product', brand: 'Test brand' }], total: 25 } });
  show(); await screen.findByText('Synthetic product');
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  await waitFor(() => expect(read).toHaveBeenCalledWith('/supplements/products', { params: { search: undefined, limit: 20, offset: 20 } }));
  fireEvent.change(screen.getByLabelText('产品名称或品牌'), { target: { value: ' test brand ' } });
  fireEvent.click(screen.getByRole('button', { name: '搜索' }));
  await waitFor(() => expect(read).toHaveBeenCalledWith('/supplements/products', { params: { search: 'test brand', limit: 20, offset: 0 } }));
  expect(client.getQueryData(['supplement-products', 7, 'test brand', 0])).toBeTruthy();
});
it('distinguishes an empty product library from a failed request', async () => {
  vi.spyOn(api, 'get').mockRejectedValue(new Error('offline')); show();
  expect(await screen.findByRole('alert')).toBeTruthy();
  expect(screen.queryByText('产品库暂无数据')).toBeNull();
});
