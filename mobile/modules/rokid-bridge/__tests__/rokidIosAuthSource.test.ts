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

  it('subscribes to Rokid audio stream events and exposes privacy-safe audio diagnostics', () => {
    expect(source).toContain('CxrClient.shared.audioEventPublisher');
    expect(source).toContain('private static func handleAudioEvent(_ event: RGCxrClientAudioEvent)');
    expect(source).toContain('audio_event_started');
    expect(source).toContain('audio_event_stream');
    expect(source).toContain('dataEvent.data.count');
    expect(source).toContain('payload["audioStreamChunkCount"] = audioStreamChunkCount');
    expect(source).toContain('payload["audioStreamByteCount"] = audioStreamByteCount');
    expect(source).toContain('payload["lastAudioEventType"] = lastAudioEventType');
    expect(source).toContain('payload["lastAudioTimestamp"] = String(lastAudioTimestamp)');
    expect(source).toContain('Privacy: never log or forward raw PCM bytes here');
    expect(source).not.toContain('dataEvent.data.base64EncodedString');
  });

  it('prints native diagnostic timestamps in Beijing UTC+8 time', () => {
    expect(source).toContain('beijingTimeZone');
    expect(source).toContain('TimeZone(secondsFromGMT: 8 * 60 * 60)');
    expect(source).toContain('formatter.timeZone = beijingTimeZone');
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

  it('gates the CustomView SDK open on a live BLE link (restored after the #158->#159 regression), keeping pending auto-retry', () => {
    expect(source).toContain('rokid_glasses_ble_not_connected');
    expect(source).toContain('"custom_view_ble_preflight"');
    // pending payload is stored BEFORE the guard so connectionStatePublisher can auto-retry once BLE connects
    expect(source).toContain('pendingCustomViewPayload = view');
    expect(source).toContain('retryPendingCustomViewAfterBleConnected()');
    expect(source).toContain('"custom_view_auto_retry"');
    expect(source).toContain('payload["customViewPendingRetry"]');
    expect(source).toContain('payload["lastCustomViewAutoRetryAt"]');
    // #158 worked WITH this guard; #159 removed it and the glasses stopped rendering.
    // openCustomView must NOT reach the SDK while BLE is down — block, surface, and return.
    expect(source).toMatch(/guard iosBleConnected\(\) else \{[\s\S]+custom_view_open_blocked[\s\S]+promise\.resolve[\s\S]+return/);
    // the never-attempt-while-disconnected stopgap from #159 must be gone
    expect(source).not.toMatch(/sdk_open_will_still_be_attempted/);
    // the guard must sit before the SDK open path
    expect(source).toMatch(/guard iosBleConnected\(\) else \{[\s\S]+let resolutionState = PromiseResolutionState/);
    expect(source).toMatch(/CxrClient\.shared\.openCustomView\(view\) \{ success, errorCode in/);
  });

  it('does not treat connected CustomView open as successful without callback or running confirmation', () => {
    expect(source).not.toMatch(/custom_view_open_settled[\s\S]+resolveCustomViewOpenPromiseIfNeeded\(promise, state: resolutionState, commandAccepted: true\)/);
    expect(source).not.toContain('lastCustomViewOpenCommandAccepted ?? true');
    expect(source).toContain('customViewOpenSettleCommandAccepted()');
    expect(source).toContain('markCustomViewOpenUnconfirmedIfNeeded(commandAccepted: settledCommandAccepted)');
    expect(source).toContain('rokid_custom_view_open_callback_missing');
    expect(source).toContain('rokid_custom_view_not_running_after_open');
    expect(source).toMatch(/if !success \|\| RokidBridgeModule\.customViewRunning \{[\s\S]+resolveCustomViewOpenPromiseIfNeeded\(promise, state: resolutionState, commandAccepted: success\)/);
    expect(source).toMatch(/let settledCommandAccepted =[\s\S]+customViewOpenSettleCommandAccepted\(\)[\s\S]+custom_view_open_settled[\s\S]+resolveCustomViewOpenPromiseIfNeeded\(promise, state: resolutionState, commandAccepted: settledCommandAccepted\)/);
    expect(source).toMatch(/if !ok \{[\s\S]+response\["reason"\] = lastCustomViewOpenError \?\? "rokid_custom_view_open_not_accepted"/);
  });

  it('initializes the CXR client, auth config, and runtime subscriptions on the main thread together', () => {
    expect(source).toContain('let initializeConfigureAndBind = {');
    expect(source).toMatch(/let initializeConfigureAndBind = \{[\s\S]+CxrClient\.initialize\([\s\S]+configureAuthentication\(\)[\s\S]+bindRuntimeEvents\(\)/);
    expect(source).toMatch(/if Thread\.isMainThread \{[\s\S]+initializeConfigureAndBind\(\)[\s\S]+\} else \{[\s\S]+DispatchQueue\.main\.sync\(execute: initializeConfigureAndBind\)/);
    expect(source).not.toMatch(/DispatchQueue\.main\.sync\(execute: initializeIfNeeded\)[\s\S]+configureAuthentication\(\)[\s\S]+bindRuntimeEvents\(\)/);
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
