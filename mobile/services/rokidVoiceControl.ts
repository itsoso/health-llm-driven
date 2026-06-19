import {
  startRokidRecord,
  stopRokidRecord,
} from '../modules/rokid-bridge';
import api from './api';
import { ROKID_PRIVACY_CLASS } from './rokidAmbient';

export const ROKID_VOICE_COMMAND_RECORD_TYPE = 'reva_voice_command';

export type RokidVoiceCommandIntent =
  | 'food_photo'
  | 'pushup_start'
  | 'pushup_stop'
  | 'pushup_save'
  | 'exercise_guidance'
  | 'confirm'
  | 'skip'
  | 'later'
  | 'unknown';

export type RokidVoiceCommand = {
  intent?: RokidVoiceCommandIntent | string;
  client_action?: string;
  route?: string | null;
  voice_reply?: string;
  display_text?: string;
  requires_confirmation?: boolean;
  safety_level?: string;
  parameters?: Record<string, unknown> | null;
  recommended_next_action?: Record<string, string> | null;
};

export type RokidVoiceCommandResponse = {
  event?: Record<string, unknown>;
  command?: RokidVoiceCommand;
};

export type SubmitRokidVoiceCommandInput = {
  transcript: string;
  confidence?: number;
  context?: string;
  capturedAt?: string;
  privacyClass?: string;
  meta?: Record<string, unknown>;
};

export type RokidVoiceClientActionHandlers = {
  captureFoodPhoto?: (options: { visualIntent: string }) => void | Promise<void>;
  openPushupCoach?: (options: { targetReps?: number; route?: string }) => void | Promise<void>;
  stopPushupCoach?: (options: { route?: string }) => void | Promise<void>;
  savePushupSet?: (options: { route?: string }) => void | Promise<void>;
  openGuidedTask?: (options: { route: string }) => void | Promise<void>;
  confirmCurrent?: () => void | Promise<void>;
  skipCurrent?: () => void | Promise<void>;
  snoozeCurrent?: () => void | Promise<void>;
  clarify?: (command: RokidVoiceCommand) => void | Promise<void>;
};

export async function startRokidVoiceCommandCapture() {
  return startRokidRecord({
    type: ROKID_VOICE_COMMAND_RECORD_TYPE,
    codec: 'pcm',
    mode: 'rokidOmni',
  });
}

export async function stopRokidVoiceCommandCapture() {
  return stopRokidRecord(ROKID_VOICE_COMMAND_RECORD_TYPE);
}

export async function submitRokidVoiceCommand(input: SubmitRokidVoiceCommandInput) {
  const response = await api.post('/ambient/rokid-voice-commands', {
    transcript: input.transcript,
    confidence: input.confidence,
    context: input.context ?? 'rokid_health',
    captured_at: input.capturedAt,
    privacy_class: input.privacyClass ?? ROKID_PRIVACY_CLASS,
    meta: input.meta,
  });
  return response.data as RokidVoiceCommandResponse;
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}

function readTargetReps(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return undefined;
  }
  const reps = Math.round(value);
  return reps > 0 && reps <= 200 ? reps : undefined;
}

export async function executeRokidVoiceClientAction(
  response: RokidVoiceCommandResponse,
  handlers: RokidVoiceClientActionHandlers,
) {
  const command = response.command;
  if (!command) {
    return;
  }
  const parameters = command.parameters ?? {};
  const route = command.route ?? undefined;

  switch (command.client_action) {
    case 'capture_food_photo':
      await handlers.captureFoodPhoto?.({
        visualIntent: readString(parameters.visual_intent) ?? 'food_scan',
      });
      return;
    case 'open_pushup_coach':
      await handlers.openPushupCoach?.({
        route: route ?? '/rokid-pushup-coach',
        targetReps: readTargetReps(parameters.target_reps),
      });
      return;
    case 'stop_pushup_coach':
      await handlers.stopPushupCoach?.({ route });
      return;
    case 'save_pushup_set':
      await handlers.savePushupSet?.({ route });
      return;
    case 'open_guided_task':
      await handlers.openGuidedTask?.({
        route: route ?? '/guided-task?domain=strength&source=rokid_voice',
      });
      return;
    case 'confirm_current':
      await handlers.confirmCurrent?.();
      return;
    case 'skip_current':
      await handlers.skipCurrent?.();
      return;
    case 'snooze_current':
      await handlers.snoozeCurrent?.();
      return;
    case 'clarify':
      await handlers.clarify?.(command);
      return;
    default:
      return;
  }
}
