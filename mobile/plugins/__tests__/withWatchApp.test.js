const fs = require('fs');
const os = require('os');
const path = require('path');
const { buildWatchInjectionEnv, _resolveGeneratedXcodeprojPath } = require('../withWatchApp');

const APP_GROUP = 'group.life.executor.health';

function watchEnabledConfig() {
  const previous = process.env.INCLUDE_WATCH_APP;
  process.env.INCLUDE_WATCH_APP = '1';
  try {
    jest.resetModules();
    const appJson = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'app.json'), 'utf8'));
    const buildConfig = require('../../app.config').default;
    return buildConfig({ config: appJson.expo });
  } finally {
    if (previous == null) delete process.env.INCLUDE_WATCH_APP;
    else process.env.INCLUDE_WATCH_APP = previous;
  }
}

describe('withWatchApp privacy manifests', () => {
  it('keeps the phone-to-watch token bridge on Keychain-only storage', () => {
    const bridgeSource = fs.readFileSync(
      path.join(__dirname, '..', '..', 'native', 'watch', 'WatchPhoneBridge.swift'),
      'utf8',
    );

    expect(bridgeSource).toContain('SecItemCopyMatching');
    expect(bridgeSource).not.toContain('UserDefaults(suiteName: appGroup)');
  });

  it('keeps photo library purpose strings in generated watch plist templates', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(pluginSource).toContain('NSPhotoLibraryUsageDescription');
    expect(pluginSource).toContain('NSPhotoLibraryAddUsageDescription');
  });

  it('uses 小巴 as the generated watch app and complication display name', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(pluginSource).toContain('<key>CFBundleDisplayName</key><string>小巴</string>');
    expect(pluginSource).toContain('<key>CFBundleName</key><string>小巴</string>');
    expect(pluginSource).not.toContain('<key>CFBundleDisplayName</key><string>Reva</string>');
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

  it('forces 小巴 display names when the ruby watch injector runs without Expo templates', () => {
    const injectorSource = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'apps', 'watch', 'scripts', 'inject_watch_target.rb'),
      'utf8',
    );

    expect(injectorSource).toContain("ensure_plist_value(watch_plist, 'CFBundleDisplayName', '小巴')");
    expect(injectorSource).toContain("ensure_plist_value(comp_plist, 'CFBundleDisplayName', '小巴')");
  });

  it('declares the watch App Group in generated watch and complication entitlements', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(pluginSource).toContain(APP_GROUP);
    expect(pluginSource).toContain('com.apple.security.application-groups');
  });

  it('keeps CODE_SIGN_ENTITLEMENTS on watch targets so App Group works on device', () => {
    const injectorSource = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'apps', 'watch', 'scripts', 'inject_watch_target.rb'),
      'utf8',
    );

    expect(injectorSource).toContain("bs['CODE_SIGN_ENTITLEMENTS']");
    expect(injectorSource).toContain('RevaWatch.entitlements');
    expect(injectorSource).toContain('RevaComplication.entitlements');
    expect(injectorSource).not.toContain("bs.delete('CODE_SIGN_ENTITLEMENTS')");
  });

  it('passes watch App Group entitlements to EAS app extension provisioning', () => {
    const extensions = watchEnabledConfig().extra.eas.build.experimental.ios.appExtensions;

    for (const target of ['RevaWatch', 'RevaComplication']) {
      const extension = extensions.find((item) => item.targetName === target);
      expect(extension?.entitlements?.['com.apple.security.application-groups']).toEqual([APP_GROUP]);
    }
  });

  it('adds watch source references relative to their Xcode groups', () => {
    const injectorSource = fs.readFileSync(
      path.join(__dirname, '..', '..', '..', 'apps', 'watch', 'scripts', 'inject_watch_target.rb'),
      'utf8',
    );

    expect(injectorSource).toContain('group.new_file(File.basename(f))');
    expect(injectorSource).toContain('cgroup.new_file(File.basename(f))');
    expect(injectorSource).toContain('group.path = watch_name');
    expect(injectorSource).toContain('cgroup.path = comp_name');
    expect(injectorSource).not.toContain('group.new_file(f)');
    expect(injectorSource).not.toContain('cgroup.new_file(f)');
  });
});
