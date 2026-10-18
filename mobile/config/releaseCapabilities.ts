import Constants from 'expo-constants';
import { Platform } from 'react-native';
import * as Updates from 'expo-updates';

export type ReleaseCapabilities = {
  variant: 'production' | 'preview' | 'development';
  advancedSettings: boolean;
  androidGoogleMapsConfigured: boolean;
  backgroundLocation: boolean;
  dailyJourney: boolean;
  rokid: boolean;
  siri: boolean;
  watch: boolean;
};

// This is expo-updates' native runtime, not the OTA-overridable Expo config.
// New runtimes require their own native-capability verification before admission.
export function supportsDailyJourneyNativeRuntime(platform: string, runtimeVersion: string | null): boolean {
  return platform === 'ios' && runtimeVersion === '1.3.6';
}

export function resolveReleaseCapabilities(
  extra: any,
  native: { platform: string; runtimeVersion: string | null } = { platform: 'unknown', runtimeVersion: null },
): ReleaseCapabilities {
  const release = extra?.release;
  const variant = release?.variant === 'preview' || release?.variant === 'development'
    ? release.variant
    : 'production';
  const capabilities = release?.capabilities ?? {};
  return {
    variant,
    advancedSettings: capabilities.advancedSettings === true,
    androidGoogleMapsConfigured: capabilities.androidGoogleMapsConfigured === true,
    backgroundLocation: capabilities.backgroundLocation === true,
    dailyJourney: capabilities.dailyJourney === true
      && supportsDailyJourneyNativeRuntime(native.platform, native.runtimeVersion),
    rokid: capabilities.rokid === true,
    siri: capabilities.siri === true,
    watch: capabilities.watch === true,
  };
}

export function getReleaseCapabilities(): ReleaseCapabilities {
  return resolveReleaseCapabilities(Constants.expoConfig?.extra, { platform: Platform.OS, runtimeVersion: Updates.runtimeVersion });
}

export function hasDailyJourneyNativeCapability(): boolean {
  return getReleaseCapabilities().dailyJourney;
}
