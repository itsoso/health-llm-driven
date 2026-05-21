import { describe, expect, it } from 'vitest';
import { GET as getAasa } from '../apple-app-site-association/route';
import { GET as getAssetLinks } from '../assetlinks.json/route';

describe('app link verification files', () => {
  const productionAndroidFingerprint = '0D:27:4E:32:7C:CE:1D:0C:5B:4D:E0:18:49:12:EE:D3:EA:24:F4:0B:86:AC:CF:30:4B:79:3A:73:5D:38:97:DA';

  it('serves an Apple app site association file for shared links', async () => {
    const res = await getAasa();
    const body = await res.json();

    expect(res.headers.get('content-type')).toContain('application/json');
    expect(body.applinks.apps).toEqual([]);
    expect(body.applinks.details).toContainEqual({
      appID: 'QA2U724DAN.life.executor.health',
      paths: ['/shared/*'],
    });
  });

  it('serves Android asset links for the production keystore', async () => {
    const previous = process.env.ANDROID_SHA256_CERT_FINGERPRINTS;
    delete process.env.ANDROID_SHA256_CERT_FINGERPRINTS;

    try {
      const res = await getAssetLinks();
      const body = await res.json();

      expect(res.headers.get('content-type')).toContain('application/json');
      expect(body).toEqual([
        {
          relation: ['delegate_permission/common.handle_all_urls'],
          target: {
            namespace: 'android_app',
            package_name: 'life.executor.health',
            sha256_cert_fingerprints: [productionAndroidFingerprint],
          },
        },
      ]);
    } finally {
      if (previous == null) {
        delete process.env.ANDROID_SHA256_CERT_FINGERPRINTS;
      } else {
        process.env.ANDROID_SHA256_CERT_FINGERPRINTS = previous;
      }
    }
  });

  it('appends Android asset links from configured fingerprints', async () => {
    const previous = process.env.ANDROID_SHA256_CERT_FINGERPRINTS;
    process.env.ANDROID_SHA256_CERT_FINGERPRINTS = 'AA:BB:CC, 11:22:33';

    try {
      const res = await getAssetLinks();
      const body = await res.json();

      expect(res.headers.get('content-type')).toContain('application/json');
      expect(body).toEqual([
        {
          relation: ['delegate_permission/common.handle_all_urls'],
          target: {
            namespace: 'android_app',
            package_name: 'life.executor.health',
            sha256_cert_fingerprints: [productionAndroidFingerprint, 'AA:BB:CC', '11:22:33'],
          },
        },
      ]);
    } finally {
      if (previous == null) {
        delete process.env.ANDROID_SHA256_CERT_FINGERPRINTS;
      } else {
        process.env.ANDROID_SHA256_CERT_FINGERPRINTS = previous;
      }
    }
  });
});
