import Constants from 'expo-constants';
import { Platform } from 'react-native';
import * as Updates from 'expo-updates';
import { getReleaseCapabilities, hasDailyJourneyNativeCapability, resolveReleaseCapabilities, supportsDailyJourneyNativeRuntime } from '../releaseCapabilities';

jest.mock('expo-updates', () => ({ runtimeVersion: '1.3.5' }));
jest.mock('expo-constants', () => ({ expoConfig: { version: '1.3.6', extra: { release: { capabilities: { dailyJourney: true } } } } }));
describe('release capabilities', () => {
  it('defaults to the narrow App Store production surface', () => {
    expect(resolveReleaseCapabilities(undefined)).toEqual({
      variant: 'production',
      advancedSettings: false,
      androidGoogleMapsConfigured: false,
      rokid: false,
      siri: false,
      watch: false,
      backgroundLocation: false,
      dailyJourney: false,
    });
  });

  it('honours explicit capabilities in non-production builds', () => {
    expect(resolveReleaseCapabilities({
      release: {
        variant: 'preview',
        capabilities: {
          advancedSettings: true,
          androidGoogleMapsConfigured: true,
          rokid: true,
          siri: true,
          watch: false,
          backgroundLocation: true,
        },
      },
    })).toEqual({
      variant: 'preview',
      advancedSettings: true,
      androidGoogleMapsConfigured: true,
      rokid: true,
      siri: true,
      watch: false,
      backgroundLocation: true,
      dailyJourney: false,
    });
  });

  it.each([undefined, false, 'true', 1])('requires an explicit boolean Maps capability: %s', (value) => {
    expect(resolveReleaseCapabilities({ release: { capabilities: { androidGoogleMapsConfigured: value } } }))
      .toEqual(expect.objectContaining({ androidGoogleMapsConfigured: false }));
  });
});


describe('daily journey native runtime boundary', () => {
  const extra = { release: { capabilities: { dailyJourney: true, backgroundLocation: true } } };
  it.each(['1.3.4', '1.3.5', '1.3.60', '1.3.7', null, undefined])('rejects unverified native runtime %s even with an OTA capability', (runtime) => {
    expect(supportsDailyJourneyNativeRuntime('ios', runtime ?? null)).toBe(false);
    expect(resolveReleaseCapabilities(extra, { platform: 'ios', runtimeVersion: runtime ?? null }).dailyJourney).toBe(false);
  });
  it('requires iOS and the exact reviewed native runtime', () => {
    expect(supportsDailyJourneyNativeRuntime('ios', '1.3.6')).toBe(true);
    expect(supportsDailyJourneyNativeRuntime('android', '1.3.6')).toBe(false);
    expect(resolveReleaseCapabilities(extra, { platform: 'ios', runtimeVersion: '1.3.6' }).dailyJourney).toBe(true);
    expect(resolveReleaseCapabilities(extra).dailyJourney).toBe(false);
    expect(resolveReleaseCapabilities(undefined, { platform: 'ios', runtimeVersion: '1.3.6' }).dailyJourney).toBe(false);
  });
});


it('reads the immutable native runtime rather than the updated manifest version', () => {
  const original = Platform.OS;
  Object.defineProperty(Platform, 'OS', { configurable: true, value: 'ios' });
  try {
    expect(Constants.expoConfig?.version).toBe('1.3.6');
    expect(Updates.runtimeVersion).toBe('1.3.5');
    expect(hasDailyJourneyNativeCapability()).toBe(false);
    expect(getReleaseCapabilities().dailyJourney).toBe(false);
  } finally { Object.defineProperty(Platform, 'OS', { configurable: true, value: original }); }
});
