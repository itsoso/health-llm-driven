import { describe, expect, it } from 'vitest';

import { GARMIN_ENDPOINTS } from './garminEndpoints';

describe('GARMIN_ENDPOINTS', () => {
  it('keeps credential reads separate from atomic connection writes', () => {
    expect(GARMIN_ENDPOINTS.credentials).toBe('/api/auth/garmin/credentials');
    expect(GARMIN_ENDPOINTS.connect).toBe('/api/auth/garmin/connect');
  });
});
