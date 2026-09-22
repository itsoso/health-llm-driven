import { describe, expect, it } from 'vitest';

import {
  canonicalModelId,
  sanitizeLlmPreference,
  sanitizeModelOptions,
} from '../modelCatalog';

describe('modelCatalog', () => {
  it('keeps only advanced chat models and drops lower versions', () => {
    const options = sanitizeModelOptions([
      { id: 'qwen3.8-max', label: 'Qwen3.8 Max', provider: 'tokenplan', model: 'qwen3.8-max', speed_tier: 'reasoning', note: '' },
      { id: 'tokenplan/Qwen3.8-Max-Preview', label: 'Qwen3.8 Max Preview', provider: 'tokenplan', model: 'qwen3.8-max', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.7-plus', label: 'Qwen3.7 Plus', provider: 'tokenplan', model: 'qwen3.7-plus', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.7-max', label: 'Qwen3.7 Max', provider: 'tokenplan', model: 'qwen3.7-max', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.6-flash', label: 'Qwen3.6 Flash', provider: 'tokenplan', model: 'qwen3.6-flash', speed_tier: 'fast', note: '' },
      { id: 'kimi-k2.6', label: 'Kimi K2.6', provider: 'tokenplan', model: 'kimi-k2.6', speed_tier: 'reasoning', note: '' },
      { id: 'glm-5.1', label: 'GLM-5.1', provider: 'tokenplan', model: 'glm-5.1', speed_tier: 'balanced', note: '' },
    ]);

    expect(options.map(option => option.id)).toEqual(['qwen3.8-max', 'qwen3.7-plus', 'qwen3.7-max']);
  });

  it('canonicalizes legacy commercial ids to the same ids used by the Mac app', () => {
    expect(canonicalModelId('commercial/Claude-Opus-4.7')).toBe('claude-opus-4.7');
    expect(canonicalModelId('commercial/Gemini-3.1-Pro-Preview')).toBe('gemini-3.1-pro');
    expect(canonicalModelId('commercial/GPT-5.5')).toBe('gpt-5.5');
    expect(canonicalModelId('qwen-3.8')).toBe('qwen3.8-max');
  });

  it('clears a stale selected model when it is no longer advanced/selectable', () => {
    const pref = sanitizeLlmPreference({
      model_id: 'glm-5.1',
      options: [
        { id: 'glm-5.1', label: 'GLM-5.1', provider: 'tokenplan', model: 'glm-5.1', speed_tier: 'balanced', note: '' },
        { id: 'glm-5.2', label: 'GLM-5.2', provider: 'tokenplan', model: 'glm-5.2', speed_tier: 'balanced', note: '' },
      ],
    });

    expect(pref.model_id).toBeNull();
    expect(pref.options.map(option => option.id)).toEqual(['glm-5.2']);
  });

  it('retains current API models and the existing explicit selection', () => {
    const ids = ['qwen3.8-max', 'qwen3.8-flash', 'deepseek-v4.1-flash', 'deepseek-v4-pro-0813', 'glm-5.3', 'qwen3.7-max'];
    const pref = sanitizeLlmPreference({
      model_id: 'qwen3.7-max',
      options: ids.map(id => ({ id, label: id, provider: 'tokenplan', model: id, speed_tier: 'balanced' })),
    });
    expect(pref.options.map(option => option.id)).toEqual(ids);
    expect(pref.model_id).toBe('qwen3.7-max');
  });

  it('does not fabricate new options or expose media and automatic routing models', () => {
    expect(sanitizeModelOptions([])).toEqual([]);
    expect(sanitizeModelOptions(['qwen-image-3.0-pro', 'happyhorse-1.1-t2v', 'qwen-audio-3.0-asr-flash', 'auto'].map(id => ({
      id, label: id, provider: 'tokenplan', model: id, speed_tier: 'balanced',
    })))).toEqual([]);
  });
});
