const APPLE_TEAM_ID = 'QA2U724DAN';
const IOS_BUNDLE_IDS = [
  'life.executor.health',
  'life.executor.health.preview',
  'life.executor.health.dev',
] as const;
const ANDROID_PACKAGE_NAME = 'life.executor.health';

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
  const fingerprints = (process.env.ANDROID_SHA256_CERT_FINGERPRINTS || '')
    .split(',')
    .map(value => value.trim())
    .filter(Boolean);

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
