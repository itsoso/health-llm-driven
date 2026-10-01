import fs from 'node:fs';
import path from 'node:path';

const sourcePath = path.resolve(__dirname, '../ios/RevaPcmPlayerModule.swift');

describe('Reva PCM player iOS module', () => {
  it('plays in-memory 24kHz mono PCM and exposes interruption', () => {
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).toContain('AVAudioEngine');
    expect(source).toContain('AVAudioPlayerNode');
    expect(source).toContain('sampleRate: 24000');
    expect(source).toContain('onPlaybackDrained');
    expect(source).toContain('AsyncFunction("stop")');
    expect(source).toContain('maxChunkBytes');
    expect(source).toContain('maxSessionBytes');
    expect(source).toContain('highWaterBytes');
    expect(source).toContain('lowWaterBytes');
    expect(source).toContain('backpressureWaiters');
    expect(source).not.toContain('write(to:');
    expect(source).not.toContain('FileManager');
  });
});
