import { resolveReleaseCapabilities } from '../releaseCapabilities';

describe('release capabilities', () => {
  it('defaults to the narrow App Store production surface', () => {
    expect(resolveReleaseCapabilities(undefined)).toEqual({
      variant: 'production',
      advancedSettings: false,
      rokid: false,
      siri: false,
      watch: false,
      backgroundLocation: false,
    });
  });

  it('honours explicit capabilities in non-production builds', () => {
    expect(resolveReleaseCapabilities({
      release: {
        variant: 'preview',
        capabilities: {
          advancedSettings: true,
          rokid: true,
          siri: true,
          watch: false,
          backgroundLocation: true,
        },
      },
    })).toEqual({
      variant: 'preview',
      advancedSettings: true,
      rokid: true,
      siri: true,
      watch: false,
      backgroundLocation: true,
    });
  });
});
