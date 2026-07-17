import fs from 'node:fs';
import path from 'node:path';

const sourcePath = path.resolve(__dirname, '../ios/RevaPcmStreamModule.swift');

describe('Reva PCM stream iOS module', () => {
  it('captures microphone PCM without using Apple speech recognition', () => {
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).toContain('AVAudioEngine');
    expect(source).toContain('AVAudioConverter');
    expect(source).toContain('sampleRate: 16000');
    expect(source).toContain('onPcmChunk');
    expect(source).not.toContain('import Speech');
    expect(source).not.toContain('SFSpeechRecognizer');
  });

  it('uses an exclusive recording session so other app audio pauses during hold-to-talk', () => {
    const source = fs.readFileSync(sourcePath, 'utf8');

    expect(source).toContain('setCategory(.record');
    expect(source).toContain('notifyOthersOnDeactivation');
    expect(source).not.toContain('mixWithOthers');
  });
});
