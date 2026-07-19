import {
  deleteLocalHealthVault,
  exportLocalHealthEnvelope,
  restoreLocalHealthEnvelope,
  type LocalHealthExportReceipt,
} from '../modules/local-health-kernel';
import { appendLocalExecutionEvent } from './localExecutionEvents';

export type LocalDataExport = {
  fileUri: string;
  recoveryKey: string;
};

export type LocalDataLifecycleKernel = {
  exportEnvelope: () => Promise<LocalHealthExportReceipt>;
  restoreEnvelope: (uri: string, recoveryKey: string) => Promise<void>;
  deleteVault: () => Promise<void>;
  appendEvent: (ownerScope: string, kind: string) => Promise<void>;
};

const nativeKernel: LocalDataLifecycleKernel = {
  exportEnvelope: exportLocalHealthEnvelope,
  restoreEnvelope: restoreLocalHealthEnvelope,
  deleteVault: deleteLocalHealthVault,
  appendEvent: appendLocalExecutionEvent,
};

const recoveryKeyPattern = /^[A-Za-z0-9+/]{43}=$/;

export class LocalDataLifecycle {
  constructor(
    private readonly ownerScope: string,
    private readonly kernel: LocalDataLifecycleKernel = nativeKernel,
  ) {
    if (!ownerScope.trim()) throw new Error('local_identity_missing');
  }

  async exportData(): Promise<LocalDataExport> {
    const receipt = await this.kernel.exportEnvelope();
    if (!receipt.uri.startsWith('file://') || !recoveryKeyPattern.test(receipt.recoveryKey)) {
      throw new Error('invalid_local_export_receipt');
    }
    await this.kernel.appendEvent(this.ownerScope, 'local_export_completed');
    return { fileUri: receipt.uri, recoveryKey: receipt.recoveryKey };
  }

  async restoreData(fileUri: string, recoveryKey: string): Promise<void> {
    const normalizedKey = recoveryKey.trim();
    if (!fileUri.startsWith('file://')) throw new Error('invalid_export_file_uri');
    if (!recoveryKeyPattern.test(normalizedKey)) throw new Error('invalid_recovery_key');
    await this.kernel.restoreEnvelope(fileUri, normalizedKey);
    await this.kernel.appendEvent(this.ownerScope, 'local_restore_completed');
  }

  async deleteAllData(): Promise<void> {
    await this.kernel.deleteVault();
  }
}
