import buildConfig from '../app.config';
const { buildWatchInjectionEnv } = require('../plugins/withWatchApp');

function configForVariant(variant?: string) {
  const previous = process.env.APP_VARIANT;
  if (variant == null) {
    delete process.env.APP_VARIANT;
  } else {
    process.env.APP_VARIANT = variant;
  }

  try {
    return buildConfig({
      config: {
        name: 'HealthPilot',
        slug: 'health-pilot',
      },
    } as any);
  } finally {
    if (previous == null) {
      delete process.env.APP_VARIANT;
    } else {
      process.env.APP_VARIANT = previous;
    }
  }
}

describe('app.config app links', () => {
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
});
