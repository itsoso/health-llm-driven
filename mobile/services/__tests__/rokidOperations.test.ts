jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

import api from '../api';
import {
  appendRokidOperationEvent,
  createRokidOperation,
  createRokidOperationId,
  getRokidOperationTimeline,
  uploadRokidDiagnostics,
} from '../rokidOperations';

const mockedApi = api as jest.Mocked<typeof api>;

describe('services/rokidOperations', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('creates stable client operation ids for traceable Rokid actions', () => {
    const id = createRokidOperationId('food');

    expect(id).toMatch(/^rokid-food-\d{13}-[a-z0-9]{6}$/);
  });

  it('creates a Rokid operation ledger row', async () => {
    mockedApi.post.mockResolvedValueOnce({
      data: {
        operation_id: 'rokid-food-001',
        type: 'capture_food',
        state: 'queued',
      },
    } as never);

    await expect(createRokidOperation({
      operationId: 'rokid-food-001',
      type: 'capture_food',
      primarySurface: 'rokid_glasses',
      meta: { route: 'cxrl_customview' },
      entityRefs: { meal_session_id: 42 },
    })).resolves.toMatchObject({
      operation_id: 'rokid-food-001',
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/devices/rokid/operations', {
      operation_id: 'rokid-food-001',
      type: 'capture_food',
      state: 'queued',
      primary_surface: 'rokid_glasses',
      summary: undefined,
      last_error_code: undefined,
      meta: { route: 'cxrl_customview' },
      entity_refs: { meal_session_id: 42 },
      write_intent_id: undefined,
    });
  });

  it('appends trace events and uploads diagnostics without raw media', async () => {
    mockedApi.post
      .mockResolvedValueOnce({ data: { id: 10, event_type: 'capture_requested' } } as never)
      .mockResolvedValueOnce({ data: { id: 11, event_type: 'diagnostic_snapshot' } } as never);

    await appendRokidOperationEvent('rokid-food-001', {
      eventType: 'capture_requested',
      phase: 'photo',
      severity: 'info',
      state: 'running',
      message: 'photo requested',
      payload: { hasBase64: false },
    });

    await uploadRokidDiagnostics({
      operationId: 'rokid-food-001',
      summary: 'audio missing, phone fallback active',
      diagnostics: {
        audio: { chunks: 0, bytes: 0 },
        photo: { hasBase64: false },
      },
    });

    expect(mockedApi.post).toHaveBeenNthCalledWith(1, '/devices/rokid/operations/rokid-food-001/events', {
      event_type: 'capture_requested',
      phase: 'photo',
      severity: 'info',
      state: 'running',
      message: 'photo requested',
      payload: { hasBase64: false },
      occurred_at: undefined,
    });
    expect(mockedApi.post).toHaveBeenNthCalledWith(2, '/devices/rokid/diagnostics', {
      operation_id: 'rokid-food-001',
      summary: 'audio missing, phone fallback active',
      diagnostics: {
        audio: { chunks: 0, bytes: 0 },
        photo: { hasBase64: false },
      },
      severity: 'warn',
      occurred_at: undefined,
    });
  });

  it('reads a Rokid operation timeline', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: {
        operation: { operation_id: 'rokid-food-001' },
        events: [{ event_type: 'diagnostic_snapshot' }],
      },
    } as never);

    await expect(getRokidOperationTimeline('rokid-food-001')).resolves.toMatchObject({
      operation: { operation_id: 'rokid-food-001' },
      events: [{ event_type: 'diagnostic_snapshot' }],
    });

    expect(mockedApi.get).toHaveBeenCalledWith('/devices/rokid/operations/rokid-food-001');
  });
});
