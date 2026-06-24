jest.mock('../api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

import api from '../api';
import {
  listRokidGlanceCards,
  submitRokidAudioInput,
  submitRokidVisualInput,
} from '../rokidAmbient';

const mockedApi = api as jest.Mocked<typeof api>;

describe('services/rokidAmbient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('submits Rokid visual food captures to the ambient visual input endpoint', async () => {
    mockedApi.post.mockResolvedValueOnce({ data: { event: { id: 101 } } } as never);

    await submitRokidVisualInput({
      intent: 'food_scan',
      imageUri: 'private://rokid/meal-001.jpg',
      ocrText: '牛肉面',
      recognitionResult: { foods: [{ name: '牛肉面' }] },
      confidence: 0.76,
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/visual-inputs', {
      intent: 'food_scan',
      source: 'rokid_glasses',
      device_type: 'glasses',
      image_uri: 'private://rokid/meal-001.jpg',
      image_sha256: undefined,
      ocr_text: '牛肉面',
      recognition_result: { foods: [{ name: '牛肉面' }] },
      confidence: 0.76,
      captured_at: undefined,
      privacy_class: 'health_l3',
      meta: undefined,
    });
  });

  it('threads operation ids through visual capture meta', async () => {
    mockedApi.post.mockResolvedValueOnce({ data: { event: { id: 102 } } } as never);

    await submitRokidVisualInput({
      intent: 'food_scan',
      operationId: 'rokid-food-001',
      meta: { trigger: 'voice_command' },
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/visual-inputs', expect.objectContaining({
      meta: {
        trigger: 'voice_command',
        operation_id: 'rokid-food-001',
      },
    }));
  });

  it('submits push-to-talk transcripts as Rokid audio input events', async () => {
    mockedApi.post.mockResolvedValueOnce({ data: { event: { id: 202 } } } as never);

    await submitRokidAudioInput({
      intent: 'food',
      transcript: '午餐一碗牛肉面',
      confidence: 0.83,
      meta: { trigger: 'push_to_talk' },
    });

    expect(mockedApi.post).toHaveBeenCalledWith('/ambient/audio-inputs', {
      intent: 'food',
      transcript: '午餐一碗牛肉面',
      source: 'rokid_glasses',
      device_type: 'glasses',
      confidence: 0.83,
      captured_at: undefined,
      privacy_class: 'health_l3',
      meta: { trigger: 'push_to_talk' },
    });
  });

  it('lists glance cards for the Rokid glasses surface', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: [{ id: 7, surface: 'rokid_glasses' }] } as never);

    await expect(listRokidGlanceCards()).resolves.toEqual([{ id: 7, surface: 'rokid_glasses' }]);

    expect(mockedApi.get).toHaveBeenCalledWith('/ambient/glance-cards', {
      params: { surface: 'rokid_glasses' },
    });
  });
});
