jest.mock('../api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

import api from '../api';
import { logMedication, deleteMedicationLog } from '../medications';

const mockApi = api as unknown as {
  post: jest.Mock;
  delete: jest.Mock;
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('logMedication', () => {
  it('POST /medication/logs with full body shape', async () => {
    mockApi.post.mockResolvedValue({
      data: { id: 7, medication_id: 3, taken_date: '2026-06-12', taken_time: '08:30', status: 'taken' },
    });

    const out = await logMedication({
      medication_id: 3,
      taken_time: '08:30',
      status: 'taken',
    });

    expect(mockApi.post).toHaveBeenCalledWith('/medication/logs', {
      medication_id: 3,
      taken_time: '08:30',
      status: 'taken',
    });
    expect(out.id).toBe(7);
  });

  it('forwards skip_reason / notes when skipping', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 8 } });
    await logMedication({
      medication_id: 3,
      taken_time: '21:00',
      status: 'skipped',
      skip_reason: '忘记',
    });
    expect(mockApi.post).toHaveBeenCalledWith('/medication/logs', {
      medication_id: 3,
      taken_time: '21:00',
      status: 'skipped',
      skip_reason: '忘记',
    });
  });
});

describe('deleteMedicationLog', () => {
  it('DELETE /medication/logs/{id}', async () => {
    mockApi.delete.mockResolvedValue({ data: { message: '已删除', id: 9 } });
    await deleteMedicationLog(9);
    expect(mockApi.delete).toHaveBeenCalledWith('/medication/logs/9');
  });
});
