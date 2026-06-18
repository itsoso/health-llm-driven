/**
 * calendar.ts 单测 —— 验证多源管理 + 事件读取的请求形状与后端契约一致。
 * 重点:① events 端点的 from/to query 透传;② addSource 按 provider 分流 body;
 * ③ sync 返回 {sources, count} 结构透传(fail-soft per source 由后端保证)。
 */
jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

import api from '../api';
import {
  addCalendarSource, deleteCalendarSource, getCalendarEvents,
  listCalendarSources, syncCalendar, updateCalendarSource,
} from '../calendar';

const mockApi = api as unknown as {
  get: jest.Mock; post: jest.Mock; put: jest.Mock; delete: jest.Mock;
};

describe('calendar service', () => {
  beforeEach(() => jest.clearAllMocks());

  it('getCalendarEvents passes from/to as query params', async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    await getCalendarEvents('2026-06-18', '2026-06-25');
    expect(mockApi.get).toHaveBeenCalledWith('/calendar/events', {
      params: { from: '2026-06-18', to: '2026-06-25' },
    });
  });

  it('getCalendarEvents omits empty params (lets backend default the window)', async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    await getCalendarEvents();
    expect(mockApi.get).toHaveBeenCalledWith('/calendar/events', { params: {} });
  });

  it('addCalendarSource sends caldav creds when provider=caldav', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 1 } });
    await addCalendarSource({
      provider: 'caldav', name: '工作', url: 'https://caldav.icloud.com',
      username: 'a@b.com', password: 'pw',
    });
    expect(mockApi.post).toHaveBeenCalledWith('/calendar/sources', {
      provider: 'caldav', name: '工作', url: 'https://caldav.icloud.com',
      username: 'a@b.com', password: 'pw',
    });
  });

  it('addCalendarSource sends only name+url for ics', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 2 } });
    await addCalendarSource({ provider: 'ics', name: '订阅', url: 'https://x/cal.ics' });
    expect(mockApi.post).toHaveBeenCalledWith('/calendar/sources', {
      provider: 'ics', name: '订阅', url: 'https://x/cal.ics',
    });
  });

  it('updateCalendarSource PUTs to /calendar/sources/{id}', async () => {
    mockApi.put.mockResolvedValue({ data: { id: 3, sync_enabled: false } });
    await updateCalendarSource(3, { sync_enabled: false });
    expect(mockApi.put).toHaveBeenCalledWith('/calendar/sources/3', { sync_enabled: false });
  });

  it('deleteCalendarSource DELETEs /calendar/sources/{id}', async () => {
    mockApi.delete.mockResolvedValue({ data: { ok: true } });
    await deleteCalendarSource(5);
    expect(mockApi.delete).toHaveBeenCalledWith('/calendar/sources/5');
  });

  it('syncCalendar returns the {sources,count} shape', async () => {
    mockApi.post.mockResolvedValue({ data: { sources: { '1': { synced: 3 }, '2': { error: 'boom' } }, count: 2 } });
    const res = await syncCalendar();
    expect(res.count).toBe(2);
    expect(res.sources['1'].synced).toBe(3);
    expect(res.sources['2'].error).toBe('boom');
  });

  it('listCalendarSources hits /calendar/sources', async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    await listCalendarSources();
    expect(mockApi.get).toHaveBeenCalledWith('/calendar/sources');
  });
});
