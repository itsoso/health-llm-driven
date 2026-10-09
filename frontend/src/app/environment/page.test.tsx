import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/services/api/client';
import EnvironmentPage from './page';
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 7 }, isAuthenticated: true }) }));
vi.mock('@/components/ProtectedRoute', () => ({ default: ({ children }: { children: React.ReactNode }) => children }));
let client: QueryClient;
let unavailable: boolean;
let failedAir: boolean;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  unavailable = false; failedAir = false;
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url === '/environment/weather') return { data: { weather: { available: !unavailable, source: 'qweather', weather: '晴', temperature: 0, display: { temperature: 0, humidity: 60, wind_speed: 1.23 } } } };
    if (failedAir) throw new Error('offline');
    return { data: { available: !unavailable, source: 'open-meteo', level: '良', display: { aqi: 0, pm25: 12.35 } } };
  });
});
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks(); });
const show = () => render(<QueryClientProvider client={client}><EnvironmentPage /></QueryClientProvider>);
describe('environment route', () => {
  it('renders weather and air from authenticated APIs with zero and formatted values', async () => {
    show();
    expect(await screen.findByText('0°C')).toBeTruthy();
    expect(screen.getByText('12.35 μg/m³')).toBeTruthy();
    expect(screen.getByText('和风天气')).toBeTruthy();
    expect(client.getQueryData(['environment', 'weather', 7])).toBeTruthy();
  });
  it('shows missingness instead of pretending unavailable data is measured', async () => {
    unavailable = true; show();
    expect(await screen.findByText('暂无天气数据')).toBeTruthy();
    expect(screen.getByText('暂无空气质量数据')).toBeTruthy();
    expect(screen.queryByText('0°C')).toBeNull();
  });
  it('keeps weather when air fails and supports retry', async () => {
    failedAir = true; show();
    expect(await screen.findByText('空气质量加载失败')).toBeTruthy();
    expect(screen.getByText('0°C')).toBeTruthy();
    failedAir = false;
    fireEvent.click(screen.getByRole('button', { name: '重试空气质量' }));
    await waitFor(() => expect(screen.queryByText('空气质量加载失败')).toBeNull());
    expect(screen.getByText('12.35 μg/m³')).toBeTruthy();
  });
});
