const fs = require('fs');
const path = require('path');
const { buildWatchInjectionEnv } = require('../withWatchApp');

describe('withWatchApp privacy manifests', () => {
  it('keeps photo library purpose strings in generated watch plist templates', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(pluginSource).toContain('NSPhotoLibraryUsageDescription');
    expect(pluginSource).toContain('NSPhotoLibraryAddUsageDescription');
  });

  it('passes the full Expo config into the watch injector so appVersion is not reset to 1.0', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(buildWatchInjectionEnv({ version: '1.3.0' }, { PATH: '/usr/bin' }).REVA_MARKETING_VERSION)
      .toBe('1.3.0');
    expect(pluginSource).toContain('buildWatchInjectionEnv(cfg, process.env)');
    expect(pluginSource).not.toContain('buildWatchInjectionEnv(cfg.modRequest.exp, process.env)');
  });

  it('keeps the main iOS target on the Expo generated Info.plist after watch target injection', () => {
    const injectorSource = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'apps', 'watch', 'scripts', 'inject_watch_target.rb'),
      'utf8',
    );

    expect(injectorSource).toMatch(/if main_t[\s\S]+bs\['GENERATE_INFOPLIST_FILE'\] = 'NO'[\s\S]+bs\['INFOPLIST_FILE'\] = 'HealthPilot\/Info\.plist'[\s\S]+end/);
  });
});
