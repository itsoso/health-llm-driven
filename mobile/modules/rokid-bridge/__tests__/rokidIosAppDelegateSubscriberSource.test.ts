import fs from 'fs';
import path from 'path';

describe('RokidBridge iOS AppDelegate subscriber source', () => {
  const sourcePath = path.join(__dirname, '..', 'ios', 'RokidBridgeAppDelegateSubscriber.swift');
  const source = fs.readFileSync(sourcePath, 'utf8');

  it('observes every inbound URL and returns the Rokid handler result', () => {
    expect(source).toContain('RokidBridgeURLHandler.observeOpenURL(url)');
    expect(source).toContain('return RokidBridgeURLHandler.handleOpenURL(url)');
  });
});
