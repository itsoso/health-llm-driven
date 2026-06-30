const fs = require('fs');
const os = require('os');
const path = require('path');
const plist = require('@expo/plist').default;

const {
  _SUPPORTED_ORIENTATIONS,
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

  it('patches the Expo generated app Info.plist even when the target directory is app', () => {
    const infoPlistPath = path.join(tmpDir, 'app', 'Info.plist');
    writeInfoPlist(infoPlistPath, { CFBundleIdentifier: 'life.executor.health' });

    _patchGeneratedInfoPlist(tmpDir, { projectName: 'app' });

    const patched = plist.parse(fs.readFileSync(infoPlistPath, 'utf8'));
    expect(patched.UISupportedInterfaceOrientations).toEqual(_SUPPORTED_ORIENTATIONS);
    expect(patched['UISupportedInterfaceOrientations~ipad']).toEqual(_SUPPORTED_ORIENTATIONS);
  });

  it('resolves the main app plist without choosing generated extension plists', () => {
    const appInfoPlistPath = path.join(tmpDir, 'app', 'Info.plist');
    const watchInfoPlistPath = path.join(tmpDir, 'RevaWatch', 'Info.plist');
    writeInfoPlist(appInfoPlistPath, { CFBundleIdentifier: 'life.executor.health' });
    writeInfoPlist(watchInfoPlistPath, { CFBundleIdentifier: 'life.executor.health.watchkitapp' });

    expect(_resolveGeneratedInfoPlistPath(tmpDir, { projectName: 'missing' })).toBe(appInfoPlistPath);
  });
});
