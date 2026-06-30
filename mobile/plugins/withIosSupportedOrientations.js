const { withDangerousMod, withInfoPlist } = require('@expo/config-plugins');
const plist = require('@expo/plist').default;
const fs = require('fs');
const path = require('path');

const SUPPORTED_ORIENTATIONS = [
  'UIInterfaceOrientationPortrait',
  'UIInterfaceOrientationPortraitUpsideDown',
  'UIInterfaceOrientationLandscapeLeft',
  'UIInterfaceOrientationLandscapeRight',
];

function applySupportedOrientationsToInfoPlist(infoPlist) {
  infoPlist.UISupportedInterfaceOrientations = [...SUPPORTED_ORIENTATIONS];
  infoPlist['UISupportedInterfaceOrientations~ipad'] = [...SUPPORTED_ORIENTATIONS];
  return infoPlist;
}

function isMainAppInfoPlist(candidatePath) {
  const parts = candidatePath.split(path.sep).map((part) => part.toLowerCase());
  if (parts.some((part) => (
    part.includes('watch')
    || part.includes('complication')
    || part.includes('extension')
    || part.includes('intent')
  ))) {
    return false;
  }

  try {
    const parsed = plist.parse(fs.readFileSync(candidatePath, 'utf8'));
    const bundleId = String(parsed.CFBundleIdentifier || '').toLowerCase();
    return !bundleId.includes('watchkit')
      && !bundleId.includes('extension')
      && !bundleId.includes('intent');
  } catch {
    return false;
  }
}

function findInfoPlists(platformProjectRoot) {
  if (!fs.existsSync(platformProjectRoot)) return [];
  return fs.readdirSync(platformProjectRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.name.endsWith('.xcodeproj') && !entry.name.endsWith('.xcworkspace'))
    .map((entry) => path.join(platformProjectRoot, entry.name, 'Info.plist'))
    .filter((candidate) => fs.existsSync(candidate));
}

function resolveGeneratedInfoPlistPath(platformProjectRoot, modRequest = {}) {
  const projectName = modRequest.projectName;
  if (projectName) {
    const projectInfoPlistPath = path.join(platformProjectRoot, projectName, 'Info.plist');
    if (fs.existsSync(projectInfoPlistPath)) {
      return projectInfoPlistPath;
    }
  }

  const mainCandidates = findInfoPlists(platformProjectRoot).filter(isMainAppInfoPlist);
  if (mainCandidates.length > 0) return mainCandidates[0];

  return path.join(platformProjectRoot, 'HealthPilot', 'Info.plist');
}

function patchGeneratedInfoPlist(platformProjectRoot, modRequest = {}) {
  const infoPlistPath = resolveGeneratedInfoPlistPath(platformProjectRoot, modRequest);
  if (!fs.existsSync(infoPlistPath)) {
    throw new Error(`withIosSupportedOrientations could not find ${infoPlistPath}`);
  }

  const current = plist.parse(fs.readFileSync(infoPlistPath, 'utf8'));
  const patched = applySupportedOrientationsToInfoPlist(current);
  fs.writeFileSync(infoPlistPath, plist.build(patched), 'utf8');
}

function withIosSupportedOrientations(config) {
  config = withInfoPlist(config, (mod) => {
    applySupportedOrientationsToInfoPlist(mod.modResults);
    return mod;
  });

  return withDangerousMod(config, [
    'ios',
    (cfg) => {
      patchGeneratedInfoPlist(cfg.modRequest.platformProjectRoot, cfg.modRequest);
      return cfg;
    },
  ]);
}

module.exports = withIosSupportedOrientations;
module.exports._applySupportedOrientationsToInfoPlist = applySupportedOrientationsToInfoPlist;
module.exports._patchGeneratedInfoPlist = patchGeneratedInfoPlist;
module.exports._resolveGeneratedInfoPlistPath = resolveGeneratedInfoPlistPath;
module.exports._SUPPORTED_ORIENTATIONS = SUPPORTED_ORIENTATIONS;
