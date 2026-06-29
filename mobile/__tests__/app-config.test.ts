const { buildWatchInjectionEnv } = require('../plugins/withWatchApp');

function configForVariant(variant?: string, env: Record<string, string | undefined> = {}) {
  const previous = process.env.APP_VARIANT;
  const previousEnv = new Map<string, string | undefined>();
  if (variant == null) {
    delete process.env.APP_VARIANT;
  } else {
    process.env.APP_VARIANT = variant;
  }
  Object.entries(env).forEach(([key, value]) => {
    previousEnv.set(key, process.env[key]);
    if (value == null) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  });

  try {
    jest.resetModules();
    const buildConfig = require('../app.config').default;
    return buildConfig({
      config: {
        name: '阿衡',
        slug: 'health-pilot',
      },
    } as any);
  } finally {
    if (previous == null) {
      delete process.env.APP_VARIANT;
    } else {
      process.env.APP_VARIANT = previous;
    }
    previousEnv.forEach((value, key) => {
      if (value == null) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    });
  }
}

function configuredUrlSchemes(config: any) {
  return (config.ios?.infoPlist?.CFBundleURLTypes ?? [])
    .flatMap((entry: any) => entry.CFBundleURLSchemes ?? []);
}

describe('app.config app links', () => {
  it('uses 阿衡 as the user-visible production app name', () => {
    const config = configForVariant('production');

    expect(config.name).toBe('阿衡');
    expect(config.ios?.infoPlist?.CFBundleDisplayName).toBe('阿衡');
  });

  it('keeps user-visible variant names aligned with 阿衡', () => {
    expect(configForVariant('development').ios?.infoPlist?.CFBundleDisplayName).toBe('阿衡 Dev');
    expect(configForVariant('preview').ios?.infoPlist?.CFBundleDisplayName).toBe('阿衡 Preview');
  });

  it('adds the health share universal link domain to iOS builds', () => {
    const config = configForVariant();

    expect(config.ios?.associatedDomains).toContain('applinks:health.executor.life');
  });

  it('adds an Android verified app link for app-open shared pages', () => {
    const config = configForVariant();

    expect(config.android?.intentFilters).toContainEqual({
      action: 'VIEW',
      autoVerify: true,
      data: [
        {
          scheme: 'https',
          host: 'health.executor.life',
          pathPrefix: '/open/shared',
        },
      ],
      category: ['BROWSABLE', 'DEFAULT'],
    });
  });

  it('passes Expo app version to the watch target injector', () => {
    const env = buildWatchInjectionEnv({ version: '1.3.0' }, { PATH: '/usr/bin' });

    expect(env.REVA_MARKETING_VERSION).toBe('1.3.0');
    expect(env.PATH).toBe('/usr/bin');
    expect(env.LANG).toBe('en_US.UTF-8');
  });

  it('uses variant-specific Rokid callback schemes so installed builds do not steal auth callbacks', () => {
    const productionSchemes = configuredUrlSchemes(configForVariant('production'));
    const previewSchemes = configuredUrlSchemes(configForVariant('preview'));
    const developmentSchemes = configuredUrlSchemes(configForVariant('development'));

    expect(productionSchemes).toContain('life.executor.health.rokid');
    expect(previewSchemes).toContain('life.executor.health.preview.rokid');
    expect(developmentSchemes).toContain('life.executor.health.dev.rokid');
    expect(new Set([
      productionSchemes.find((scheme: string) => scheme.includes('.rokid')),
      previewSchemes.find((scheme: string) => scheme.includes('.rokid')),
      developmentSchemes.find((scheme: string) => scheme.includes('.rokid')),
    ]).size).toBe(3);
  });

  it('allows Rokid CXR-L builds to request the SDK default cxrl callback while keeping the bundle-specific fallback registered', () => {
    const config = configForVariant('production', {
      ROKID_IOS_CALLBACK_SCHEME: 'cxrl',
    });
    const schemes = configuredUrlSchemes(config);

    expect(config.ios?.infoPlist?.RokidCXRAuthCallbackScheme).toBe('cxrl');
    expect(schemes).toEqual(expect.arrayContaining([
      'cxrl',
      'life.executor.health.rokid',
    ]));
  });
});
