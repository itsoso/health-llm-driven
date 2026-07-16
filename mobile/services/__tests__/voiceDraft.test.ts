import {
  buildVoiceDraft,
  buildVoiceDraftExtraContext,
  mergeExtraContext,
} from '../voiceDraft';

describe('voiceDraft', () => {
  it('normalizes common health voice terms while preserving the raw transcript', () => {
    const draft = buildVoiceDraft({
      source: 'hold_to_talk',
      rawTranscript: '今天 h r v 下降  体重 73.1 公斤 喝水 500 ml',
      asr: {
        provider: 'openai_whisper',
        model: 'whisper-1',
        durationMs: 1234,
        confidence: 'medium',
      },
    });

    expect(draft).toMatchObject({
      source: 'hold_to_talk',
      rawTranscript: '今天 h r v 下降  体重 73.1 公斤 喝水 500 ml',
      normalizedText: '今天 HRV 下降 体重 73.1kg 喝水 500ml',
      state: 'editable',
      asrProvider: 'openai_whisper',
      asrModel: 'whisper-1',
      asrDurationMs: 1234,
    });
    expect(draft.confidence).toBe('medium');
  });

  it('builds compact Agent context for voice correction and parser recovery', () => {
    const draft = buildVoiceDraft({
      source: 'realtime_mic',
      rawTranscript: '机场贵宾厅吃了番茄鸡蛋面',
    });

    const context = JSON.parse(buildVoiceDraftExtraContext(draft));

    expect(context).toEqual({
      source: 'mobile_voice_input',
      voice_draft: {
        source: 'realtime_mic',
        raw: '机场贵宾厅吃了番茄鸡蛋面',
        normalized: '机场贵宾厅吃了番茄鸡蛋面',
        confidence: 'medium',
        asr_provider: 'cloud_asr',
      },
      instruction: expect.stringContaining('优先按 normalized 理解'),
    });
  });

  it('merges voice context with an existing Agent mode context instead of overwriting it', () => {
    const merged = mergeExtraContext(
      JSON.stringify({ source: 'mobile_chat_composer', mode: 'deep' }),
      JSON.stringify({ source: 'mobile_voice_input', voice_draft: { normalized: '记录午餐' } }),
    );

    expect(JSON.parse(merged)).toEqual({
      source: 'mobile_chat_composer',
      mode: 'deep',
      voice_input: {
        source: 'mobile_voice_input',
        voice_draft: { normalized: '记录午餐' },
      },
    });
  });
});
