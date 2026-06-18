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
    expect(source).toContain('url.scheme?.caseInsensitiveCompare(callbackScheme) == .orderedSame');
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
});
