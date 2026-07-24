import {
  prepareForAppReload,
  registerAppReloadPreparation,
} from '../appReloadPreparation';

describe('appReloadPreparation', () => {
  it('runs every registered preparation before reload', async () => {
    const first = jest.fn().mockResolvedValue(undefined);
    const second = jest.fn().mockResolvedValue(undefined);
    const unregisterFirst = registerAppReloadPreparation(first);
    const unregisterSecond = registerAppReloadPreparation(second);

    try {
      await prepareForAppReload();
      expect(first).toHaveBeenCalledTimes(1);
      expect(second).toHaveBeenCalledTimes(1);
    } finally {
      unregisterFirst();
      unregisterSecond();
    }
  });

  it('stops reload when any registered preparation fails', async () => {
    const unregister = registerAppReloadPreparation(async () => {
      throw new Error('draft write failed');
    });

    try {
      await expect(prepareForAppReload()).rejects.toThrow(
        '无法安全保存当前内容，请稍后重试更新',
      );
    } finally {
      unregister();
    }
  });
});
