import buildConfig from '../app.config';

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
});
