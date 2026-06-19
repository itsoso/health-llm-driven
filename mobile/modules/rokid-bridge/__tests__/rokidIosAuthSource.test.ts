import fs from 'fs';
import path from 'path';

describe('RokidBridge iOS auth callback source', () => {
  const sourcePath = path.join(__dirname, '..', 'ios', 'RokidBridgeModule.swift');
  const source = fs.readFileSync(sourcePath, 'utf8');

  it('routes callbacks through the SDK auth manager callback handler', () => {
    expect(source).toContain('CxrClient.shared.auth.canHandleURL(url)');
    expect(source).toContain('CxrClient.shared.auth.handleCallback(url: url)');
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
