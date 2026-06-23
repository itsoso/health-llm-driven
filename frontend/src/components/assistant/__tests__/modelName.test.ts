import { describe, expect, it } from 'vitest';
import { prettyModelName } from '../modelName';

describe('prettyModelName', () => {
  it('strips provider prefix and patch version for known families', () => {
    expect(prettyModelName('commercial/Claude-Opus-4.7')).toBe('Claude Opus');
    expect(prettyModelName('claude-sonnet-4.5')).toBe('Claude Sonnet');
    expect(prettyModelName('gpt-5.5')).toBe('GPT-5');
    expect(prettyModelName('gemini-3.1-pro')).toBe('Gemini Pro');
    expect(prettyModelName('tokenplan/qwen3.7-plus')).toBe('Qwen');
    expect(prettyModelName('deepseek-v4-pro')).toBe('DeepSeek');
  });

  it('gracefully cleans unknown ids', () => {
    expect(prettyModelName('vendor/some-model-2.0')).toBe('some model');
    expect(prettyModelName('openclaw:main')).toBe('main');
  });

  it('returns null for empty input', () => {
    expect(prettyModelName(null)).toBeNull();
    expect(prettyModelName('')).toBeNull();
    expect(prettyModelName('   ')).toBeNull();
  });
});
