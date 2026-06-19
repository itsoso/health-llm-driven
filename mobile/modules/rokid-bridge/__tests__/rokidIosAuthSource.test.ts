import fs from 'fs';
import path from 'path';

describe('RokidBridge iOS auth callback source', () => {
  const sourcePath = path.join(__dirname, '..', 'ios', 'RokidBridgeModule.swift');
  const source = fs.readFileSync(sourcePath, 'utf8');
  const podspecPath = path.join(__dirname, '..', 'ios', 'RokidBridge.podspec');
  const podspec = fs.readFileSync(podspecPath, 'utf8');
  const easJsonPath = path.join(__dirname, '..', '..', '..', 'eas.json');
  const easJson = JSON.parse(fs.readFileSync(easJsonPath, 'utf8'));

  it('routes callbacks through the SDK auth manager callback handler', () => {
    expect(source).toContain('CxrClient.shared.auth.canHandleURL(url)');
    expect(source).toContain('CxrClient.shared.auth.handleCallback(url: url)');
  });

  it('always lets the top-level CXR client inspect auth callbacks for session setup', () => {
    expect(source).toMatch(/let handledByAuth = CxrClient\.shared\.auth\.handleCallback\(url: url\)[\s\S]+let handledByClient = CxrClient\.shared\.handleOpenURL\(url\)/);
    expect(source).not.toContain('handledByAuth ? false : CxrClient.shared.handleOpenURL(url)');
    expect(source).toContain('clientOpenUrlHandled');
  });

  it('does not require the callback host/path before passing the URL to the SDK', () => {
    expect(source).toContain('acceptedCallbackSchemes.contains');
    expect(source).not.toContain('&& url.host?.caseInsensitiveCompare(callbackHost) == .orderedSame');
    expect(source).not.toContain('&& url.path == callbackPath');
  });

  it('uses explicit bundle id, longer timeout, and native auth diagnostics', () => {
    expect(source).toContain('authorizationRequestTimeoutSeconds: TimeInterval = 180.0');
    expect(source).toContain('requestTimeout: authorizationRequestTimeoutSeconds');
    expect(source).toContain('bundleId: Bundle.main.bundleIdentifier');
    expect(source).toContain('lastAuthorizationRequestAt');
    expect(source).toContain('lastAuthorizationError');
    expect(source).toContain('lastAuthorizationErrorAt');
  });

  it('records SDK auth events and explicit companion routing config for device debugging', () => {
    expect(source).toContain('private static let companionServerScheme = "rokidai"');
    expect(source).toContain('private static let companionServerHost = "connect"');
    expect(source).toContain('payload["companionServerScheme"] = companionServerScheme');
    expect(source).toContain('payload["companionServerHost"] = companionServerHost');
    expect(source).toContain('CxrClient.shared.auth.eventPublisher');
    expect(source).toContain('recordAuthorizationEvent');
    expect(source).toContain('lastAuthorizationEvent');
    expect(source).toContain('lastAuthorizationEventAt');
    expect(source).toContain('currentDeviceName');
  });

  it('observes every inbound iOS URL with a query-free fingerprint before auth filtering', () => {
    expect(source).toContain('lastOpenUrlFingerprint');
    expect(source).toContain('lastOpenUrlAt');
    expect(source).toContain('lastOpenUrlExpectedAuthCallback');
    expect(source).toContain('fileprivate static func observeOpenURL(_ url: URL)');
    expect(source).toContain('lastOpenUrlFingerprint = urlFingerprint(url)');
    expect(source).toContain('lastOpenUrlExpectedAuthCallback = isExpectedAuthCallback(url)');
    expect(source).toContain('private static func urlFingerprint(_ url: URL) -> String');
    expect(source).toContain('payload["lastOpenUrlFingerprint"] = lastOpenUrlFingerprint');
    expect(source).not.toContain('lastOpenUrlFingerprint = url.absoluteString');
  });

  it('resets stale not-authenticated, failed, or authenticating SDK auth state before explicit retry', () => {
    expect(source).toContain('resetAuthorizationStateForExplicitRequest()');
    expect(source).toMatch(/startAuthorizationAttempt\(scopes: scopes, appName: appName\)[\s\S]+resetAuthorizationStateForExplicitRequest\(\)[\s\S]+configureAuthentication\(force: true\)[\s\S]+CxrClient\.shared\.auth\.authenticate/);
    expect(source).toContain('case .notAuthenticated, .authenticating, .expired');
    expect(source).toContain('case .failed(_)');
    expect(source).toContain('CxrClient.shared.auth.clearAuthentication()');
  });

  it('clears notAuthenticated SDK auth state before explicit retry because timeout can leave stale callback internals', () => {
    expect(source).toMatch(/case \.authenticated\(_, _\):\s+return/);
    expect(source).toMatch(/case \.notAuthenticated, \.authenticating, \.expired:/);
  });

  it('refreshes the SDK auth config after clearing stale auth state on each explicit authorization request', () => {
    expect(source).toContain('configureAuthentication(force: true)');
    expect(source).toContain('private static func configureAuthentication(force: Bool = false)');
    expect(source).toMatch(/resetAuthorizationStateForExplicitRequest\(\)[\s\S]+configureAuthentication\(force: true\)[\s\S]+markAuthorizationPhase\("authenticate_invoking"/);
  });

  it('exposes a query-redacted native authorization timeline for field debugging', () => {
    expect(source).toContain('authDiagnosticTimeline');
    expect(source).toContain('lastAuthorizationAttemptId');
    expect(source).toContain('lastAuthorizationPhase');
    expect(source).toContain('lastAuthorizationDurationMs');
    expect(source).toContain('lastAuthorizationStateBeforeReset');
    expect(source).toContain('lastAuthorizationStateAfterReset');
    expect(source).toContain('lastAuthorizationStateBeforeAuthenticate');
    expect(source).toContain('NSLog("[RevaRokidAuth]');
    expect(source).toContain('payload["authDiagnosticTimeline"] = authDiagnosticTimeline');
  });

  it('surfaces iOS BLE and CustomView-open boundaries for session debugging', () => {
    expect(source).toContain('RGCxrClientBLE.shared.isConnected');
    expect(source).toContain('RGCxrClientBLE.shared.connectedDeviceName');
    expect(source).toContain('payload["iosBleConnected"]');
    expect(source).toContain('payload["iosBleDeviceName"]');
    expect(source).toContain('RGCxrClientBLE.shared.connectionStatePublisher');
    expect(source).toContain('"ble_connection_event"');
    expect(source).toContain('recordAuthDiagnostic(');
    expect(source).toContain('"custom_view_open_requested"');
    expect(source).toContain('"custom_view_open_invoked"');
  });

  it('blocks CustomView opening until the CXR-L glasses BLE link is connected', () => {
    expect(source).toContain('rokid_glasses_ble_not_connected');
    expect(source).toMatch(/guard iosBleConnected\(\) else \{[\s\S]+custom_view_open_blocked[\s\S]+rokid_glasses_ble_not_connected[\s\S]+promise\.resolve/);
    expect(source).toMatch(/guard iosBleConnected\(\) else \{[\s\S]+return[\s\S]+let resolutionState = PromiseResolutionState/);
  });

  it('captures raw CustomView notify events and payload fingerprints for open failures', () => {
    expect(source).toContain('lastCustomViewPayloadHash');
    expect(source).toContain('lastCustomViewPayloadShape');
    expect(source).toContain('lastCustomViewPayloadBytes');
    expect(source).toContain('lastCustomViewRawNotify');
    expect(source).toContain('lastCustomViewOpenError');
    expect(source).toContain('cxrCallbackApiEnabled');
    expect(source).toContain('cxrNotifySubscriptionMode');
    expect(source).toContain('RGCxrClientBLE.shared.notifyPublisher');
    expect(source).toContain('handleCustomViewNotify');
    expect(source).toContain('Custom_View_Opened');
    expect(source).toContain('Custom_View_Open_Failed');
    expect(source).toContain('payload["lastCustomViewPayloadHash"]');
    expect(source).toContain('payload["lastCustomViewRawNotify"]');
    expect(source).toContain('payload["cxrCallbackApiEnabled"]');
    expect(source).toContain('payload["cxrNotifySubscriptionMode"]');
  });

  it('keeps the callback CustomView API behind an explicit compile flag for the refreshed Rokid framework', () => {
    expect(source).toContain('#if ROKID_CXRL_CALLBACK_API');
    expect(source).toContain('setNotifyEventListenCmds');
    expect(source).toContain('custom_view_open_callback');
    expect(source).toContain('lastCustomViewOpenCallbackSuccess');
    expect(source).toContain('lastCustomViewOpenCallbackErrorCode');
    expect(source).toContain('ROKID_CXRL_CALLBACK_API');
  });

  it('does not mark CustomView as running from openCustomView callback success alone', () => {
    expect(source).toContain('lastCustomViewOpenCommandAccepted');
    expect(source).toContain('payload["lastCustomViewOpenCommandAccepted"]');
    expect(source).not.toContain('RokidBridgeModule.customViewRunning = true');
    expect(source).toMatch(/customViewRunningEventPublisher[\s\S]+customViewRunning = event\.isRunning/);
  });

  it('initializes the refreshed CXR-L client before auth and exposes the real initialized state', () => {
    expect(source).toContain('CxrClient.initialize(');
    expect(source).toContain('mode: .customView');
    expect(source).toContain('RGCxrClientInitializationOptions(');
    expect(source).toContain('CxrClient.isInitialized');
    expect(source).toContain('CxrClient.initializationMode');
    expect(source).toContain('cxr_initialize');
    expect(source).toContain('cxr_client_not_initialized');
    expect(source).toMatch(/startAuthorizationAttempt\(scopes: scopes, appName: appName\)[\s\S]+ensureCustomViewInitialized\(\)[\s\S]+guard cxrClientInitialized\(\)/);
    expect(source).not.toContain('return true\n    #else\n    return false\n    #endif\n  }\n\n  private static func cxrInitializationMode()');
  });

  it('allows pinning a refreshed Rokid iOS binary framework as a first-class local pod', () => {
    expect(podspec).toContain('ROKID_IOS_CLIENT_FRAMEWORK_PATH');
    expect(podspec).toContain('Rokid vendored framework not found');
    expect(podspec).toContain('Rokid vendored framework is missing refreshed CustomView callback APIs');
    expect(podspec).toContain("s.dependency 'RGCoreKit', '0.0.2'");
    expect(podspec).toContain("s.dependency 'RGCxrClient', rokid_ios_client_version");
    expect(podspec).toContain('不把框架传播进 RokidBridge 的 -F 搜索路径');
    expect(podspec).toContain('ROKID_IOS_CLIENT_HAS_CALLBACK_API');
    expect(podspec).toContain('ROKID_CXRL_CALLBACK_API');
  });

  it('activates the refreshed Rokid iOS framework path and callback API in Rokid EAS profiles', () => {
    for (const profileName of ['rokid-preview', 'rokid-production']) {
      const env = easJson.build[profileName].env;
      expect(env.ROKID_IOS_CLIENT_FRAMEWORK_PATH).toBe('vendor/RGCxrClient.framework');
      expect(env.ROKID_IOS_CLIENT_HAS_CALLBACK_API).toBe('1');
    }
  });

  it('can configure the SDK callback scheme from Info.plist while keeping safe fallbacks observable', () => {
    expect(source).toContain('private static var callbackScheme: String');
    expect(source).toContain('private static let sdkDefaultCallbackScheme = "cxrl"');
    expect(source).toContain('RokidCXRAuthCallbackScheme');
    expect(source).toContain('private static var acceptedCallbackSchemes: [String]');
    expect(source).toContain('payload["callbackSchemeSource"] = callbackSchemeSource');
    expect(source).toContain('payload["acceptedCallbackSchemes"] = acceptedCallbackSchemes');
    expect(source).toContain('return "\\(bundleIdentifier).rokid"');
    expect(source).not.toContain('private static let callbackScheme = "life.executor.health.rokid"');
  });
});
