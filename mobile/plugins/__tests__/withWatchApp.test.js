const fs = require('fs');
const os = require('os');
const path = require('path');
const { buildWatchInjectionEnv, _resolveGeneratedXcodeprojPath } = require('../withWatchApp');

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
    expect(pluginSource).toContain('buildWatchInjectionEnv(cfg, {');
    expect(pluginSource).toContain('REVA_MAIN_TARGET_NAME');
    expect(pluginSource).not.toContain('buildWatchInjectionEnv(cfg.modRequest.exp, process.env)');
  });

  it('resolves the Expo generated xcodeproj from the actual project name', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'watch-xcodeproj-'));
    try {
      fs.mkdirSync(path.join(tmpDir, 'app.xcodeproj'), { recursive: true });

      expect(_resolveGeneratedXcodeprojPath(tmpDir, { projectName: 'app' }))
        .toBe(path.join(tmpDir, 'app.xcodeproj'));
    } finally {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('keeps the main iOS target on the Expo generated Info.plist after watch target injection', () => {
    const injectorSource = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'apps', 'watch', 'scripts', 'inject_watch_target.rb'),
      'utf8',
    );

    expect(injectorSource).toContain("ENV['REVA_IOS_INFOPLIST_FILE']");
    expect(injectorSource).not.toContain("project.targets.find { |t| t.name == 'HealthPilot' }");
  });
});
