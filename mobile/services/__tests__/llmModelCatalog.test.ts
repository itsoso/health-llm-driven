import {
  canonicalModelId,
  sanitizeLlmPreference,
  sanitizeModelOptions,
} from '../llmModelCatalog';

describe('llmModelCatalog', () => {
  it('keeps only advanced chat models and drops lower versions', () => {
    const options = sanitizeModelOptions([
      { id: 'qwen3.8-max-preview', label: 'Qwen3.8 Max Preview', provider: 'tokenplan', model: 'qwen3.8-max-preview', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.7-plus', label: 'Qwen3.7 Plus', provider: 'tokenplan', model: 'qwen3.7-plus', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.7-max', label: 'Qwen3.7 Max', provider: 'tokenplan', model: 'qwen3.7-max', speed_tier: 'reasoning', note: '' },
      { id: 'qwen3.6-plus', label: 'Qwen3.6 Plus', provider: 'tokenplan', model: 'qwen3.6-plus', speed_tier: 'reasoning', note: '' },
      { id: 'deepseek-v3.2', label: 'DeepSeek V3.2', provider: 'tokenplan', model: 'deepseek-v3.2', speed_tier: 'reasoning', note: '' },
      { id: 'glm-5.1', label: 'GLM-5.1', provider: 'tokenplan', model: 'glm-5.1', speed_tier: 'balanced', note: '' },
    ]);

    expect(options.map(option => option.id)).toEqual(['qwen3.8-max-preview', 'qwen3.7-plus', 'qwen3.7-max']);
  });

  it('canonicalizes legacy commercial ids to the same ids used by the Mac app', () => {
    expect(canonicalModelId('commercial/Claude-Opus-4.7')).toBe('claude-opus-4.7');
    expect(canonicalModelId('commercial/Gemini-3.1-Pro-Preview')).toBe('gemini-3.1-pro');
    expect(canonicalModelId('commercial/GPT-5.5')).toBe('gpt-5.5');
    expect(canonicalModelId('tokenplan/Qwen3.8-Max-Preview')).toBe('qwen3.8-max-preview');
  });

  it('clears a stale selected model when it is no longer advanced/selectable', () => {
    const pref = sanitizeLlmPreference({
      model_id: 'qwen3.6-plus',
      options: [
        { id: 'qwen3.6-plus', label: 'Qwen3.6 Plus', provider: 'tokenplan', model: 'qwen3.6-plus', speed_tier: 'reasoning', note: '' },
        { id: 'glm-5.2', label: 'GLM-5.2', provider: 'tokenplan', model: 'glm-5.2', speed_tier: 'balanced', note: '' },
      ],
    });

    expect(pref.model_id).toBeNull();
    expect(pref.options.map(option => option.id)).toEqual(['glm-5.2']);
  });
});
