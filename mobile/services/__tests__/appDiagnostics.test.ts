import { buildAppDiagnosticsSnapshot } from '../appDiagnostics';

describe('app diagnostics', () => {
  it('labels an OTA launch with channel, runtime, update id, and native build', () => {
    const snapshot = buildAppDiagnosticsSnapshot({
      platform: 'ios',
      constants: {
        nativeAppVersion: '1.3.0',
        nativeBuildVersion: '129',
        expoConfig: {
          name: 'HealthPilot',
          ios: { bundleIdentifier: 'life.executor.health' },
          extra: { eas: { projectId: 'project-1' } },
        },
      },
      updates: {
        channel: 'rokid-production',
        runtimeVersion: '1.3.0',
        updateId: 'update-1',
        isEmbeddedLaunch: false,
        isEmergencyLaunch: false,
        createdAt: new Date('2026-06-18T06:54:17Z'),
      },
    });

    expect(snapshot.summary).toEqual({
      appVersion: '1.3.0',
      buildNumber: '129',
      channel: 'rokid-production',
      runtimeVersion: '1.3.0',
      launchSource: 'ota',
    });
    expect(snapshot.rows).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'bundleIdentifier', value: 'life.executor.health' }),
        expect.objectContaining({ id: 'projectId', value: 'project-1' }),
        expect.objectContaining({ id: 'updateId', value: 'update-1' }),
      ]),
    );
  });

  it('labels an embedded launch when no OTA bundle is active', () => {
    const snapshot = buildAppDiagnosticsSnapshot({
      platform: 'ios',
      constants: {
        nativeAppVersion: '1.3.0',
        nativeBuildVersion: '129',
        expoConfig: { name: 'HealthPilot' },
      },
      updates: {
        channel: 'rokid-production',
        runtimeVersion: '1.3.0',
        updateId: null,
        isEmbeddedLaunch: true,
      },
    });

    expect(snapshot.summary.launchSource).toBe('embedded');
    expect(snapshot.rows.find((row) => row.id === 'embeddedLaunch')?.value).toBe('yes');
  });
});
