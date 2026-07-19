import fs from 'fs';
import path from 'path';

const moduleRoot = path.resolve(__dirname, '..');
const iosRoot = path.join(moduleRoot, 'ios');

function read(name: string): string {
  return fs.readFileSync(path.join(iosRoot, name), 'utf8');
}

describe('local health native privacy boundary', () => {
  it('registers every encrypted vault operation through the Expo module', () => {
    const source = read('LocalHealthKernelModule.swift');

    expect(source).toContain('Name("LocalHealthKernel")');
    for (const operation of [
      'createVault',
      'openVault',
      'putEncrypted',
      'getDecrypted',
      'listDecrypted',
      'delete',
      'exportEnvelope',
      'restoreEnvelope',
      'deleteVault',
      'recognizeFoodPhoto',
    ]) {
      expect(source).toContain(`AsyncFunction("${operation}")`);
    }
    expect(source).toContain('UIApplication.shared.isProtectedDataAvailable');
  });

  it('uses a non-synchronizing, passcode-bound data-protection keychain item', () => {
    const source = read('SystemLocalHealthKeychain.swift');

    expect(source).toContain('kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly');
    expect(source).toMatch(/kSecAttrSynchronizable as String:\s*kCFBooleanFalse/);
    expect(source).toMatch(/kSecUseDataProtectionKeychain as String:\s*kCFBooleanTrue/);
    expect(source).not.toContain('kSecAttrAccessibleAfterFirstUnlock');
  });

  it('keeps vault artifacts in Application Support with complete file protection', () => {
    const source = read('SystemLocalHealthVaultFiles.swift');

    expect(source).toContain('.applicationSupportDirectory');
    expect(source).toContain('FileProtectionType.complete');
    expect(source).toContain('LocalHealthKernel');
  });

  it('does not add network or plaintext diagnostic output to the privacy boundary', () => {
    const source = [
      read('LocalHealthKernelModule.swift'),
      read('SystemLocalHealthKeychain.swift'),
      read('SystemLocalHealthVaultFiles.swift'),
    ].join('\n');

    expect(source).not.toMatch(/URLSession|print\(|NSLog\(|os_log|Logger\s*\(/);
  });
});
