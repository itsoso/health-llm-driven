describe('local-health-kernel JS facade', () => {
  const loadModule = (platform: 'ios' | 'android' | 'web', native?: any) => {
    jest.resetModules();
    const requireNativeModule = jest.fn(() => {
      if (!native) throw new Error('native module missing');
      return native;
    });
    jest.doMock('expo-modules-core', () => ({
      Platform: { OS: platform },
      requireNativeModule,
    }));
    return {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      kernel: require('../index'),
      requireNativeModule,
    };
  };

  it('fails explicitly when the native kernel is unavailable', async () => {
    const { kernel } = loadModule('ios');

    await expect(kernel.createLocalHealthVault('local-user')).rejects.toMatchObject({
      code: 'native_module_unavailable',
    });
  });

  it('delegates encrypted CRUD and export without changing health payloads', async () => {
    const native = {
      createVault: jest.fn().mockResolvedValue(undefined),
      openVault: jest.fn().mockResolvedValue(undefined),
      putEncrypted: jest.fn().mockResolvedValue(undefined),
      commitMutation: jest.fn().mockResolvedValue(undefined),
      getDecrypted: jest.fn().mockResolvedValue('{"food_items":"米饭"}'),
      listDecrypted: jest.fn().mockResolvedValue(['{"food_items":"米饭"}']),
      delete: jest.fn().mockResolvedValue(undefined),
      exportEnvelope: jest.fn().mockResolvedValue({
        uri: 'file:///private/export.json',
        recoveryKey: 'separate-key',
      }),
      restoreEnvelope: jest.fn().mockResolvedValue(undefined),
      deleteVault: jest.fn().mockResolvedValue(undefined),
      recognizeFoodPhoto: jest.fn().mockResolvedValue(JSON.stringify({
        decision: 'candidate',
        candidates: [{
          canonicalFoodID: 'food.staple.rice.white',
          displayName: '白米饭',
          category: 'staple',
          score: 0.72,
          evidence: 'whole_image',
          regionIndex: null,
        }],
        topScore: 0.72,
        margin: 0.05,
      })),
    };
    const { kernel, requireNativeModule } = loadModule('ios', native);

    await kernel.createLocalHealthVault('local-user');
    await kernel.openLocalHealthVault('local-user');
    await kernel.putLocalHealthEncrypted({
      collection: 'diet_records',
      id: 'meal-1',
      version: 1,
      equalityIndexes: { day: '2026-07-19' },
      payload: '{"food_items":"米饭"}',
    });
    await kernel.commitLocalHealthMutation({
      writes: [{
        collection: 'execution_events',
        id: 'event-1',
        version: 1,
        equalityIndexes: { record_id: 'meal-1' },
        payload: '{"kind":"diet_record_confirmed"}',
      }],
      deletes: [],
    });
    await expect(
      kernel.getLocalHealthDecrypted('diet_records', 'meal-1'),
    ).resolves.toBe('{"food_items":"米饭"}');
    await expect(
      kernel.listLocalHealthDecrypted('diet_records', 'day', '2026-07-19'),
    ).resolves.toEqual(['{"food_items":"米饭"}']);
    await kernel.deleteLocalHealthEncrypted('diet_records', 'meal-1');
    await expect(kernel.exportLocalHealthEnvelope()).resolves.toEqual({
      uri: 'file:///private/export.json',
      recoveryKey: 'separate-key',
    });
    await kernel.restoreLocalHealthEnvelope('file:///private/export.json', 'separate-key');
    await expect(kernel.recognizeLocalFoodPhoto('file:///private/photo.jpg')).resolves.toEqual({
      decision: 'candidate',
      candidates: [{
        canonicalFoodId: 'food.staple.rice.white',
        displayName: '白米饭',
        category: 'staple',
        score: 0.72,
        evidence: 'whole_image',
      }],
      manualConfirmationRequired: true,
      canAutoSave: false,
      estimatesPortion: false,
    });
    await kernel.deleteLocalHealthVault();

    expect(requireNativeModule).toHaveBeenCalledWith('LocalHealthKernel');
    expect(native.putEncrypted).toHaveBeenCalledWith(
      'diet_records',
      'meal-1',
      1,
      { day: '2026-07-19' },
      '{"food_items":"米饭"}',
    );
    expect(native.commitMutation).toHaveBeenCalledWith(JSON.stringify({
      writes: [{
        collection: 'execution_events',
        id: 'event-1',
        version: 1,
        equalityIndexes: { record_id: 'meal-1' },
        payload: '{"kind":"diet_record_confirmed"}',
      }],
      deletes: [],
    }));
  });

  it('rejects a malformed photo result instead of inventing a food candidate', async () => {
    const native = {
      recognizeFoodPhoto: jest.fn().mockResolvedValue('{"decision":"candidate","candidates":[]}'),
    };
    const { kernel } = loadModule('ios', native);

    await expect(
      kernel.recognizeLocalFoodPhoto('file:///private/photo.jpg'),
    ).rejects.toMatchObject({ code: 'invalid_vision_result' });
  });

  it('rejects unsupported collections before crossing the native boundary', async () => {
    const native = { putEncrypted: jest.fn() };
    const { kernel } = loadModule('ios', native);

    await expect(kernel.putLocalHealthEncrypted({
      collection: 'unknown',
      id: 'meal-1',
      version: 1,
      equalityIndexes: {},
      payload: '{}',
    })).rejects.toMatchObject({ code: 'invalid_collection' });
    expect(native.putEncrypted).not.toHaveBeenCalled();
  });
});
