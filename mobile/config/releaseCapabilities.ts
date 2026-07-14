import Constants from 'expo-constants';

export type ReleaseCapabilities = {
  variant: 'production' | 'preview' | 'development';
  advancedSettings: boolean;
  backgroundLocation: boolean;
  rokid: boolean;
  siri: boolean;
  watch: boolean;
};

export function resolveReleaseCapabilities(extra: any): ReleaseCapabilities {
  const release = extra?.release;
  const variant = release?.variant === 'preview' || release?.variant === 'development'
    ? release.variant
    : 'production';
  const capabilities = release?.capabilities ?? {};
  return {
    variant,
    advancedSettings: capabilities.advancedSettings === true,
    backgroundLocation: capabilities.backgroundLocation === true,
    rokid: capabilities.rokid === true,
    siri: capabilities.siri === true,
    watch: capabilities.watch === true,
  };
}

export function getReleaseCapabilities(): ReleaseCapabilities {
  return resolveReleaseCapabilities(Constants.expoConfig?.extra);
}
