import { buildRokidOperationDiagnostics } from '../rokidOperationDiagnostics';

describe('services/rokidOperationDiagnostics', () => {
  it('builds a structured Rokid diagnostic snapshot without raw media payloads', () => {
    const diagnostics = buildRokidOperationDiagnostics({
      operationId: 'rokid-food-001',
      status: {
        nativeBuildNumber: '184',
        nativeAppVersion: '1.3.0',
        bundleIdentifier: 'life.executor.health',
        authorizationState: 'authenticated',
        iosBleConnected: true,
        iosBleDeviceName: 'Glasses_0077',
        customViewRunning: true,
        audioStreamChunkCount: 12,
        audioStreamByteCount: 4096,
        lastAudioEventType: 'stream',
        speechRecognitionState: 'recognizing',
        speechAuthorizationStatus: 'authorized',
        speechAudioAppendCount: 3,
        lastSpeechTranscript: '记录这顿饭',
        image_base64: 'raw-image-should-not-leak',
        audio_base64: 'raw-audio-should-not-leak',
      },
      voiceState: { status: 'listening', message: '我来拍这餐' },
      voiceDebug: {
        lastRawTranscript: '记录这顿饭',
        lastCommandAction: 'capture_food_photo',
        photoPhase: 'native_received',
        photoSource: 'rokid_glasses',
        photoByteLength: 123456,
        photoHasBase64: true,
        photoHasImageUri: false,
        photoHasSha256: true,
        photoSummary: '西瓜 360kcal',
        photo_base64: 'raw-photo-should-not-leak',
      },
      selfCheck: {
        summary: '语音指令已路由: capture_food_photo',
        items: [
          { id: 'audio', title: '音频流', status: 'pass', detail: '12 chunks' },
        ],
      },
    });

    expect(diagnostics).toMatchObject({
      operation: { operation_id: 'rokid-food-001' },
      app: { build: '184', version: '1.3.0', bundle: 'life.executor.health' },
      link: { auth: 'authenticated', ble_connected: true, device: 'Glasses_0077' },
      audio: { event: 'stream', chunks: 12, bytes: 4096 },
      route: { raw_transcript: '记录这顿饭', last_action: 'capture_food_photo' },
      photo: {
        phase: 'native_received',
        source: 'rokid_glasses',
        bytes: 123456,
        has_base64: true,
        has_image_uri: false,
        has_sha256: true,
      },
    });
    expect(JSON.stringify(diagnostics)).not.toContain('raw-image-should-not-leak');
    expect(JSON.stringify(diagnostics)).not.toContain('raw-audio-should-not-leak');
    expect(JSON.stringify(diagnostics)).not.toContain('raw-photo-should-not-leak');
  });
});
