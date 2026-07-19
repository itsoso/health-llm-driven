import {
  recognizeLocalFoodPhoto,
  type LocalFoodPhotoRecognition,
} from '../modules/local-health-kernel';
import { createLocalDietDraft, type LocalDietDraft } from './localDietDraft';

type LocalModelRouterDependencies = {
  deterministicText: (input: string, date: string) => LocalDietDraft;
  recognizePhoto: (uri: string) => Promise<LocalFoodPhotoRecognition>;
};

const defaultDependencies: LocalModelRouterDependencies = {
  deterministicText: createLocalDietDraft,
  recognizePhoto: recognizeLocalFoodPhoto,
};

/**
 * The shipped local router is intentionally small: deterministic text parsing
 * is the guaranteed path and Chinese-CLIP is a photo-candidate helper only.
 * It has no cloud client and therefore cannot silently fall back to a server.
 */
export class LocalModelRouter {
  constructor(private readonly dependencies: LocalModelRouterDependencies = defaultDependencies) {}

  createTextDraft(input: string, date: string): {
    engine: 'deterministic_local';
    draft: LocalDietDraft;
  } {
    return {
      engine: 'deterministic_local',
      draft: this.dependencies.deterministicText(input, date),
    };
  }

  async recognizePhoto(uri: string): Promise<{
    engine: 'chinese_clip_int8_local';
    recognition: LocalFoodPhotoRecognition;
  }> {
    const recognition = await this.dependencies.recognizePhoto(uri);
    if (!recognition.manualConfirmationRequired
        || recognition.canAutoSave
        || recognition.estimatesPortion) {
      throw new Error('unsafe_local_photo_recognition_contract');
    }
    return { engine: 'chinese_clip_int8_local', recognition };
  }
}

export const localModelRouter = new LocalModelRouter();
