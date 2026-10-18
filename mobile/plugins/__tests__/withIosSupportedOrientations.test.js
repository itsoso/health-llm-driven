const fs = require('fs');
const os = require('os');
const path = require('path');
const plist = require('@expo/plist').default;

const {
  _SUPPORTED_ORIENTATIONS,
  _applySupportedOrientationsToInfoPlist,
  _applyIosReleaseScopeToInfoPlist,
  _patchGeneratedInfoPlist,
  _resolveGeneratedInfoPlistPath,
} = require('../withIosSupportedOrientations');

function writeInfoPlist(filePath, values = {}) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, plist.build(values), 'utf8');
}

describe('withIosSupportedOrientations', () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ios-orientations-'));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('preserves all iPad orientations for the explicitly enabled tablet config', () => {
    const patched = _applySupportedOrientationsToInfoPlist({}, true);
    expect(patched['UISupportedInterfaceOrientations~ipad']).toEqual([
      'UIInterfaceOrientationPortrait', 'UIInterfaceOrientationPortraitUpsideDown',
      'UIInterfaceOrientationLandscapeLeft', 'UIInterfaceOrientationLandscapeRight',
    ]);
    expect(patched.UIRequiresFullScreen).toBe(false);
    expect(patched.UISupportedInterfaceOrientations).toEqual(['UIInterfaceOrientationPortrait']);
  });

  it('patches the Expo generated app Info.plist even when the target directory is app', () => {
    const infoPlistPath = path.join(tmpDir, 'app', 'Info.plist');
    writeInfoPlist(infoPlistPath, { CFBundleIdentifier: 'life.executor.health' });

    _patchGeneratedInfoPlist(tmpDir, { projectName: 'app' });

    const patched = plist.parse(fs.readFileSync(infoPlistPath, 'utf8'));
    expect(patched.UISupportedInterfaceOrientations).toEqual(_SUPPORTED_ORIENTATIONS);
    expect(patched.UISupportedInterfaceOrientations).toEqual([
      'UIInterfaceOrientationPortrait',
    ]);
    expect(patched['UISupportedInterfaceOrientations~ipad']).toBeUndefined();
  });

  it('resolves the main app plist without choosing generated extension plists', () => {
    const appInfoPlistPath = path.join(tmpDir, 'app', 'Info.plist');
    const watchInfoPlistPath = path.join(tmpDir, 'RevaWatch', 'Info.plist');
    writeInfoPlist(appInfoPlistPath, { CFBundleIdentifier: 'life.executor.health' });
    writeInfoPlist(watchInfoPlistPath, { CFBundleIdentifier: 'life.executor.health.watchkitapp' });

    expect(_resolveGeneratedInfoPlistPath(tmpDir, { projectName: 'missing' })).toBe(appInfoPlistPath);
  });

  it('removes unused background and always-location declarations from the standard binary', () => {
    const infoPlist = {
      UIBackgroundModes: ['fetch', 'audio'],
      NSLocationAlwaysUsageDescription: 'always',
      NSLocationAlwaysAndWhenInUseUsageDescription: 'always and when in use',
      NSLocationWhenInUseUsageDescription: 'foreground only',
    };

    _applyIosReleaseScopeToInfoPlist(infoPlist);

    expect(infoPlist.UIBackgroundModes).toBeUndefined();
    expect(infoPlist.NSLocationAlwaysUsageDescription).toBeUndefined();
    expect(infoPlist.NSLocationAlwaysAndWhenInUseUsageDescription).toBeUndefined();
    expect(infoPlist.NSLocationWhenInUseUsageDescription).toBe('foreground only');
  });
});


describe('daily journey generated native plist', () => {
  it('preserves only authorized location and strips legacy always permission', () => {
    const result = _applyIosReleaseScopeToInfoPlist({
      UIBackgroundModes: ['location', 'fetch', 'audio', 'processing'],
      NSLocationAlwaysUsageDescription: 'legacy',
      NSLocationAlwaysAndWhenInUseUsageDescription: '记录今天行程',
    }, true);
    expect(result.UIBackgroundModes).toEqual(['location']);
    expect(result.NSLocationAlwaysAndWhenInUseUsageDescription).toBe('记录今天行程');
    expect(result.NSLocationAlwaysUsageDescription).toBeUndefined();
  });
  it('retains required declarations in the actual generated main-app plist', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'journey-plist-'));
    try {
      const file = path.join(root, 'app', 'Info.plist');
      writeInfoPlist(file, { CFBundleIdentifier: 'life.executor.health', UIBackgroundModes: ['location', 'fetch'], NSLocationAlwaysAndWhenInUseUsageDescription: '记录今天行程' });
      _patchGeneratedInfoPlist(root, { projectName: 'app' }, false, true);
      const actual = plist.parse(fs.readFileSync(file, 'utf8'));
      expect(actual.UIBackgroundModes).toEqual(['location']);
      expect(actual.NSLocationAlwaysAndWhenInUseUsageDescription).toBe('记录今天行程');
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
});
