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

function patchGeneratedInfoPlist(platformProjectRoot) {
  const infoPlistPath = path.join(platformProjectRoot, 'HealthPilot', 'Info.plist');
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
      patchGeneratedInfoPlist(cfg.modRequest.platformProjectRoot);
      return cfg;
    },
  ]);
}

module.exports = withIosSupportedOrientations;
module.exports._applySupportedOrientationsToInfoPlist = applySupportedOrientationsToInfoPlist;
module.exports._SUPPORTED_ORIENTATIONS = SUPPORTED_ORIENTATIONS;
