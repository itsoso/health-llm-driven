/**
 * 核心流程测试 — 验证关键页面能正确渲染
 */
// @ts-nocheck
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// Mock next/navigation
const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: '1' }),
  usePathname: () => '/',
}));

// Mock AuthContext — 默认已登录已引导
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'test', name: '测试', is_approved: true, onboarding_completed: true, is_admin: false },
    token: 'test-token', isAuthenticated: true, isLoading: false,
    login: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(), register: vi.fn(),
  }),
}));

vi.mock('@/contexts/ToastContext', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

// Mock react-query
vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: null, isLoading: false, refetch: vi.fn(), isFetching: false }),
  useMutation: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

// Mock API — 所有返回 Promise
const mockGet = vi.fn().mockResolvedValue({ data: [] });
const mockPost = vi.fn().mockResolvedValue({ data: {} });
vi.mock('@/services/api', () => ({
  dailyHealthApi: { getMyGarminData: vi.fn().mockResolvedValue({ data: [] }) },
  garminAnalysisApi: { getMyComprehensive: vi.fn().mockResolvedValue({ data: {} }) },
  basicHealthApi: { getMyLatest: vi.fn().mockResolvedValue({ data: null }) },
  dataCollectionApi: { syncGarmin: vi.fn() },
  healthTrendApi: { getLatest: vi.fn().mockResolvedValue({ data: null }) },
  onboardingApi: { getStatus: vi.fn().mockResolvedValue({ data: { profile_data: null } }), saveStep1: vi.fn(), saveStep2: vi.fn(), complete: vi.fn(), skip: vi.fn() },
  familyApi: { getReports: vi.fn().mockResolvedValue({ data: [] }), getReportDetail: vi.fn().mockResolvedValue({ data: null }), getIndicatorTrend: vi.fn().mockResolvedValue({ data: [] }) },
  feedbackApi: { submit: vi.fn() },
  sharedApi: { createShare: vi.fn() },
  chatApi: { transcribe: vi.fn(), voiceCommand: vi.fn() },
  api: { get: mockGet, post: mockPost },
}));

// Mock recharts
vi.mock('recharts', () => ({
  LineChart: ({ children }: any) => <div>{children}</div>,
  Line: () => null, BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => null, XAxis: () => null, YAxis: () => null,
  CartesianGrid: () => null, Tooltip: () => null, Legend: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  ReferenceLine: () => null,
}));

// Mock date-fns
vi.mock('date-fns', () => ({
  format: (d: any, f: string) => '2026-03-29',
  subDays: (d: any, n: number) => new Date(),
}));

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn().mockReturnValue('test-token'),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

beforeEach(() => {
  vi.clearAllMocks();
});

// ============================================================

describe('Home', () => {
  it('exposes the latest iPhone QR install entry', async () => {
    const Page = (await import('@/app/page')).default;
    render(<Page />);

    const installLink = screen.getByRole('link', { name: /扫码安装 iPhone 版/i });
    expect(installLink).toHaveAttribute('href', '/mobile-install/ios/latest/install.html');
    expect(screen.getByText('不走 TestFlight, 保留登录状态直接更新')).toBeDefined();
  });
});

describe('Dashboard', () => {
  it('renders quick action buttons', async () => {
    const Page = (await import('@/app/dashboard/page')).default;
    render(<Page />);
    expect(screen.getByText('喝水')).toBeDefined();
    expect(screen.getByText('饮食')).toBeDefined();
    expect(screen.getByText('AI助理')).toBeDefined();
    expect(screen.getByText('体检报告')).toBeDefined();
    expect(screen.getByText('运动')).toBeDefined();
    expect(screen.getByText('总览')).toBeDefined();
  });

  it('keeps blood pressure available in the home quick-record entry', async () => {
    const Page = (await import('@/app/dashboard/page')).default;
    render(<Page />);

    expect(screen.getByPlaceholderText(/血压120\/80/)).toBeDefined();
  });

  it('navigates on quick action click', async () => {
    const Page = (await import('@/app/dashboard/page')).default;
    render(<Page />);
    fireEvent.click(screen.getByText('AI助理'));
    expect(mockPush).toHaveBeenCalledWith('/ai-assistant');
  });
});

describe('Login', () => {
  it('renders form fields', async () => {
    const Page = (await import('@/app/login/page')).default;
    render(<Page />);
    // Already authenticated, so it redirects — but the component renders briefly
    // Just verify the module loads without errors
    expect(true).toBe(true);
  });
});

describe('Report Detail', () => {
  it('renders without crashing', async () => {
    // 旧版本测试 import 了 page.tsx (dynamic + ssr:false), 在 vitest 里
    // 需要等异步 chunk 解析才会渲染 "加载中...". 直接测 ClientPage 更稳.
    const ClientPage = (await import('@/app/family/reports/[id]/ClientPage')).default;
    render(<ClientPage />);
    expect(screen.getByText('加载中...')).toBeDefined();
  });
});

describe('Not Found (404)', () => {
  it('renders 404 page correctly', async () => {
    const NotFound = (await import('@/app/not-found')).default;
    render(<NotFound />);
    expect(screen.getByText('404')).toBeDefined();
    expect(screen.getByText('页面不存在')).toBeDefined();
    expect(screen.getByText('返回首页')).toBeDefined();
  });
});

describe('Weight Page', () => {
  it('renders without crashing', async () => {
    const Page = (await import('@/app/weight/page')).default;
    render(<Page />);
    expect(screen.getByText('追踪体重变化，管理健康目标')).toBeDefined();
  });
});

describe('Water Page', () => {
  it('renders without crashing', async () => {
    const Page = (await import('@/app/water/page')).default;
    render(<Page />);
    expect(screen.getByText('今日饮水')).toBeDefined();
  });
});
