import {
  LocalDataLifecycle,
  type LocalDataLifecycleKernel,
} from '../localDataLifecycle';

function kernel(): jest.Mocked<LocalDataLifecycleKernel> {
  return {
    exportEnvelope: jest.fn().mockResolvedValue({
      uri: 'file:///private/export.json',
      recoveryKey: 'a'.repeat(43) + '=',
    }),
    restoreEnvelope: jest.fn().mockResolvedValue(undefined),
    deleteVault: jest.fn().mockResolvedValue(undefined),
    appendEvent: jest.fn().mockResolvedValue(undefined),
  };
}

describe('LocalDataLifecycle', () => {
  it('returns the encrypted file and recovery key as separate artifacts', async () => {
    const port = kernel();
    const lifecycle = new LocalDataLifecycle('local-owner', port);

    await expect(lifecycle.exportData()).resolves.toEqual({
      fileUri: 'file:///private/export.json',
      recoveryKey: 'a'.repeat(43) + '=',
    });
    expect(port.appendEvent).toHaveBeenCalledWith(
      'local-owner',
      'local_export_completed',
    );
  });

  it('restores only through the authenticated native envelope path and audits success', async () => {
    const port = kernel();
    const lifecycle = new LocalDataLifecycle('local-owner', port);

    await lifecycle.restoreData('file:///private/export.json', `  ${'b'.repeat(43)}=  `);

    expect(port.restoreEnvelope).toHaveBeenCalledWith(
      'file:///private/export.json',
      'b'.repeat(43) + '=',
    );
    expect(port.appendEvent).toHaveBeenCalledWith(
      'local-owner',
      'local_restore_completed',
    );
  });

  it('does not claim an audit success when export or restore fails', async () => {
    const port = kernel();
    port.exportEnvelope.mockRejectedValueOnce(new Error('storage_failure'));
    const lifecycle = new LocalDataLifecycle('local-owner', port);

    await expect(lifecycle.exportData()).rejects.toThrow('storage_failure');
    expect(port.appendEvent).not.toHaveBeenCalled();

    port.restoreEnvelope.mockRejectedValueOnce(new Error('authentication_failed'));
    await expect(
      lifecycle.restoreData('file:///private/export.json', 'bad-key'),
    ).rejects.toThrow('invalid_recovery_key');
    expect(port.restoreEnvelope).not.toHaveBeenCalled();
  });

  it('crypto-shreds the native vault without writing a misleading surviving event', async () => {
    const port = kernel();
    const lifecycle = new LocalDataLifecycle('local-owner', port);

    await lifecycle.deleteAllData();

    expect(port.deleteVault).toHaveBeenCalledTimes(1);
    expect(port.appendEvent).not.toHaveBeenCalled();
  });
});
