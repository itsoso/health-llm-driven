const {
  _patchAppDelegateContents,
} = require('../plugins/withRokidIosAuthCallback');

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
  it('patches generated AppDelegate to route Rokid auth callbacks before RN linking', () => {
    const patched = _patchAppDelegateContents(BASE_APP_DELEGATE);

    expect(patched).toContain(`#if canImport(RokidBridge)
internal import RokidBridge
#endif`);
    expect(patched).toContain(`if RokidBridgeURLHandler.canHandleOpenURL(url) {
      _ = RokidBridgeURLHandler.handleOpenURL(url)
      return true
    }`);
    expect(patched.indexOf('RokidBridgeURLHandler.canHandleOpenURL(url)')).toBeLessThan(
      patched.indexOf('RCTLinkingManager.application'),
    );
  });

  it('does not duplicate the Rokid callback hook', () => {
    const once = _patchAppDelegateContents(BASE_APP_DELEGATE);
    const twice = _patchAppDelegateContents(once);

    expect(twice).toBe(once);
    expect((twice.match(/RokidBridgeURLHandler/g) ?? []).length).toBe(2);
  });
});
