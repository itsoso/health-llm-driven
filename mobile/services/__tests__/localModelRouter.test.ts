import { LocalModelRouter } from '../localModelRouter';

describe('LocalModelRouter', () => {
  it('always keeps text capture on the deterministic local path', () => {
    const deterministicText = jest.fn().mockReturnValue({ record: { food_items: '米饭' } });
    const recognizePhoto = jest.fn();
    const router = new LocalModelRouter({ deterministicText, recognizePhoto });

    expect(router.createTextDraft('午饭米饭', '2026-07-19')).toEqual({
      engine: 'deterministic_local',
      draft: { record: { food_items: '米饭' } },
    });
    expect(deterministicText).toHaveBeenCalledWith('午饭米饭', '2026-07-19');
    expect(recognizePhoto).not.toHaveBeenCalled();
  });

  it('uses Chinese-CLIP locally for photos and preserves manual-confirm-only flags', async () => {
    const recognizePhoto = jest.fn().mockResolvedValue({
      decision: 'candidate',
      candidates: [],
      manualConfirmationRequired: true,
      canAutoSave: false,
      estimatesPortion: false,
    });
    const router = new LocalModelRouter({ deterministicText: jest.fn(), recognizePhoto });

    await expect(router.recognizePhoto('file:///private/photo.jpg')).resolves.toEqual({
      engine: 'chinese_clip_int8_local',
      recognition: expect.objectContaining({
        manualConfirmationRequired: true,
        canAutoSave: false,
        estimatesPortion: false,
      }),
    });
  });
});
