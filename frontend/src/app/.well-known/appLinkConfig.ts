const APPLE_TEAM_ID = 'QA2U724DAN';
const IOS_BUNDLE_IDS = [
  'life.executor.health',
  'life.executor.health.preview',
  'life.executor.health.dev',
] as const;
const ANDROID_PACKAGE_NAME = 'life.executor.health';
const ANDROID_SHA256_CERT_FINGERPRINTS = [
  '0D:27:4E:32:7C:CE:1D:0C:5B:4D:E0:18:49:12:EE:D3:EA:24:F4:0B:86:AC:CF:30:4B:79:3A:73:5D:38:97:DA',
] as const;

export function appleAppSiteAssociation() {
  return {
    applinks: {
      apps: [],
      details: IOS_BUNDLE_IDS.map(bundleId => ({
        appID: `${APPLE_TEAM_ID}.${bundleId}`,
        paths: ['/shared/*'],
      })),
    },
  };
}

export function androidAssetLinks() {
  const configuredFingerprints = (process.env.ANDROID_SHA256_CERT_FINGERPRINTS || '')
    .split(',')
    .map(value => value.trim())
    .filter(Boolean);
  const fingerprints = Array.from(new Set([
    ...ANDROID_SHA256_CERT_FINGERPRINTS,
    ...configuredFingerprints,
  ]));

  if (fingerprints.length === 0) return [];

  return [
    {
      relation: ['delegate_permission/common.handle_all_urls'],
      target: {
        namespace: 'android_app',
        package_name: ANDROID_PACKAGE_NAME,
        sha256_cert_fingerprints: fingerprints,
      },
    },
  ];
}
