const {
  _patchAppDelegateContents,
  _resolveGeneratedAppDelegatePath,
} = require('../plugins/withRokidIosAuthCallback');
const fs = require('fs');
const os = require('os');
const path = require('path');

const BASE_APP_DELEGATE = `internal import Expo
import React
import ReactAppDependencyProvider

@main
class AppDelegate: ExpoAppDelegate {
  public override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    return super.application(app, open: url, options: options) || RCTLinkingManager.application(app, open: url, options: options)
  }
}
`;

describe('withRokidIosAuthCallback', () => {
  it('resolves the Expo generated AppDelegate from the actual project name', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'rokid-appdelegate-'));
    try {
      const appDelegatePath = path.join(tmpDir, 'app', 'AppDelegate.swift');
      fs.mkdirSync(path.dirname(appDelegatePath), { recursive: true });
      fs.writeFileSync(appDelegatePath, BASE_APP_DELEGATE, 'utf8');

      expect(_resolveGeneratedAppDelegatePath(tmpDir, { projectName: 'app' })).toBe(appDelegatePath);
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('patches generated AppDelegate to route Rokid auth callbacks before RN linking', () => {
    const patched = _patchAppDelegateContents(BASE_APP_DELEGATE);

    expect(patched).toContain(`#if canImport(RokidBridge)
internal import RokidBridge
#endif`);
    expect(patched).toContain(`RokidBridgeURLHandler.observeOpenURL(url)
    if RokidBridgeURLHandler.canHandleOpenURL(url) {
      _ = RokidBridgeURLHandler.handleOpenURL(url)
      return true
    }`);
    expect(patched.indexOf('RokidBridgeURLHandler.observeOpenURL(url)')).toBeLessThan(
      patched.indexOf('RokidBridgeURLHandler.canHandleOpenURL(url)'),
    );
    expect(patched.indexOf('RokidBridgeURLHandler.canHandleOpenURL(url)')).toBeLessThan(
      patched.indexOf('RCTLinkingManager.application'),
    );
  });

  it('does not duplicate the Rokid callback hook', () => {
    const once = _patchAppDelegateContents(BASE_APP_DELEGATE);
    const twice = _patchAppDelegateContents(once);

    expect(twice).toBe(once);
    expect((twice.match(/RokidBridgeURLHandler/g) ?? []).length).toBe(3);
  });

  it('repairs a generated AppDelegate that handles Rokid URLs but forgot to observe them', () => {
    const partiallyPatched = BASE_APP_DELEGATE.replace(
      '    return super.application(app, open: url, options: options) || RCTLinkingManager.application(app, open: url, options: options)\n',
      `    #if canImport(RokidBridge)
    if RokidBridgeURLHandler.canHandleOpenURL(url) {
      _ = RokidBridgeURLHandler.handleOpenURL(url)
      return true
    }
    #endif

    return super.application(app, open: url, options: options) || RCTLinkingManager.application(app, open: url, options: options)
`,
    );

    const patched = _patchAppDelegateContents(partiallyPatched);

    expect(patched).toContain('RokidBridgeURLHandler.observeOpenURL(url)');
    expect(patched.indexOf('RokidBridgeURLHandler.observeOpenURL(url)')).toBeLessThan(
      patched.indexOf('RokidBridgeURLHandler.canHandleOpenURL(url)'),
    );
  });
});
