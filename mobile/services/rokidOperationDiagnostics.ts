type DiagnosticInput = {
  operationId?: string;
  status?: Record<string, unknown>;
  voiceState?: {
    status?: string;
    message?: string;
  };
  voiceDebug?: Record<string, unknown>;
  selfCheck?: {
    summary?: string;
    items?: Array<{
      id?: string;
      title?: string;
      status?: string;
      detail?: string;
    }>;
  };
};

function readString(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function readNumber(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function readBoolean(source: Record<string, unknown> | undefined, key: string) {
  const value = source?.[key];
  return typeof value === 'boolean' ? value : undefined;
}

function compact<T extends Record<string, unknown>>(value: T): T {
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => entry !== undefined && entry !== null && entry !== ''),
  ) as T;
}

export function buildRokidOperationDiagnostics(input: DiagnosticInput) {
  const status = input.status;
  const voiceDebug = input.voiceDebug;

  return compact({
    operation: compact({
      operation_id: input.operationId,
      generated_at: new Date().toISOString(),
    }),
    app: compact({
      build: readString(status, 'nativeBuildNumber'),
      version: readString(status, 'nativeAppVersion'),
      bundle: readString(status, 'bundleIdentifier'),
    }),
    link: compact({
      auth: readString(status, 'authorizationState'),
      ble_connected: readBoolean(status, 'iosBleConnected'),
      device: readString(status, 'iosBleDeviceName') ?? readString(status, 'currentDeviceName'),
      sdk_linked: readBoolean(status, 'sdkLinked'),
      callback_api: readBoolean(status, 'cxrCallbackApiEnabled'),
      notify: readString(status, 'cxrNotifySubscriptionMode'),
    }),
    custom_view: compact({
      running: readBoolean(status, 'customViewRunning'),
      evidence: readBoolean(status, 'customViewSessionEvidence'),
      display_inferred: readBoolean(status, 'customViewDisplayInferred'),
      command_accepted: readBoolean(status, 'lastCustomViewOpenCommandAccepted'),
      error: readString(status, 'lastCustomViewOpenError'),
      payload_bytes: readNumber(status, 'lastCustomViewPayloadBytes'),
      payload_hash: readString(status, 'lastCustomViewPayloadHash'),
      payload_shape: readString(status, 'lastCustomViewPayloadShape'),
      raw_notify_present: Boolean(readString(status, 'lastCustomViewRawNotify')),
    }),
    audio: compact({
      event: readString(status, 'lastAudioEventType'),
      active: readString(status, 'activeRecordType'),
      type: readString(status, 'lastAudioRecordType'),
      chunks: readNumber(status, 'audioStreamChunkCount') ?? 0,
      bytes: readNumber(status, 'audioStreamByteCount') ?? 0,
      last_chunk: readNumber(status, 'lastAudioChunkBytes'),
      codec: readNumber(status, 'lastAudioCodec'),
      channels: readNumber(status, 'lastAudioChannels'),
      at: readString(status, 'lastAudioEventAt'),
    }),
    speech: compact({
      state: readString(status, 'speechRecognitionState'),
      auth: readString(status, 'speechAuthorizationStatus'),
      available: readBoolean(status, 'speechRecognizerAvailable'),
      locale: readString(status, 'speechRecognitionLocale'),
      appends: readNumber(status, 'speechAudioAppendCount') ?? 0,
      frames: readNumber(status, 'speechAudioFrameCount') ?? 0,
      last_transcript: readString(status, 'lastSpeechTranscript') ?? readString(voiceDebug, 'lastTranscript'),
      last_transcript_at: readString(status, 'lastSpeechTranscriptAt') ?? readString(voiceDebug, 'lastTranscriptAt'),
      last_error: readString(status, 'lastSpeechError'),
    }),
    fallback: compact({
      mode: readString(voiceDebug, 'fallbackMode'),
      reason: readString(voiceDebug, 'fallbackReason'),
      last_source: readString(voiceDebug, 'fallbackLastSource'),
      last_event_at: readString(voiceDebug, 'fallbackLastEventAt'),
      error: readString(voiceDebug, 'fallbackError'),
    }),
    route: compact({
      raw_transcript: readString(voiceDebug, 'lastRawTranscript'),
      normalized_transcript: readString(voiceDebug, 'lastNormalizedTranscript'),
      normalized_by: readString(voiceDebug, 'lastTranscriptNormalizedBy'),
      last_action: readString(voiceDebug, 'lastCommandAction'),
      last_at: readString(voiceDebug, 'lastCommandAt'),
      last_reply: readString(voiceDebug, 'lastCommandReply'),
      last_error: readString(voiceDebug, 'lastCommandError'),
    }),
    photo: compact({
      phase: readString(voiceDebug, 'photoPhase'),
      source: readString(voiceDebug, 'photoSource'),
      requested_at: readString(voiceDebug, 'photoRequestedAt'),
      result_at: readString(voiceDebug, 'photoResultAt'),
      bytes: readNumber(voiceDebug, 'photoByteLength'),
      mime: readString(voiceDebug, 'photoMimeType'),
      has_base64: readBoolean(voiceDebug, 'photoHasBase64'),
      has_image_uri: readBoolean(voiceDebug, 'photoHasImageUri'),
      has_sha256: readBoolean(voiceDebug, 'photoHasSha256'),
      error: readString(voiceDebug, 'photoError'),
      draft: readString(voiceDebug, 'photoDraftStatus'),
      summary: readString(voiceDebug, 'photoSummary'),
    }),
    voice: compact({
      state: input.voiceState?.status,
      message: input.voiceState?.message,
    }),
    self_check: compact({
      summary: input.selfCheck?.summary,
      items: input.selfCheck?.items?.map((item) => compact({
        id: item.id,
        title: item.title,
        status: item.status,
        detail: item.detail,
      })),
    }),
  });
}
