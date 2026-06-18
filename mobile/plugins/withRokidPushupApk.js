const { withXcodeProject } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const BUNDLED_APK_NAME = 'rokid-pushup-glasses.apk';
const RESOURCE_DEST = path.join('HealthPilot', 'RokidApps', BUNDLED_APK_NAME);

function findRokidPushupApk(projectRoot, env = process.env) {
  const candidates = [
    env.REVA_ROKID_PUSHUP_APK_PATH,
    path.join(projectRoot, 'assets', 'rokid', BUNDLED_APK_NAME),
    path.join(
      projectRoot,
      '..',
      'apps',
      'rokid-pushup-glasses',
      'app',
      'build',
      'outputs',
      'apk',
      'release',
      'app-release.apk',
    ),
    path.join(
      projectRoot,
      '..',
      'apps',
      'rokid-pushup-glasses',
      'app',
      'build',
      'outputs',
      'apk',
      'debug',
      'app-debug.apk',
    ),
  ].filter(Boolean);

  return candidates.find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
}

function findMainTargetUuid(project, targetName = 'HealthPilot') {
  const targets = project.pbxNativeTargetSection();
  for (const [uuid, target] of Object.entries(targets)) {
    if (!uuid.endsWith('_comment') && target.name === targetName) {
      return uuid;
    }
  }
  return null;
}

function hasFileReference(project, fileName) {
  const refs = project.pbxFileReferenceSection();
  return Object.values(refs).some((ref) => (
    ref &&
    typeof ref === 'object' &&
    (ref.path === fileName || ref.path === `"${fileName}"`)
  ));
}

function withRokidPushupApk(config) {
  return withXcodeProject(config, (cfg) => {
    const projectRoot = cfg.modRequest.projectRoot;
    const iosRoot = cfg.modRequest.platformProjectRoot;
    const apkSource = findRokidPushupApk(projectRoot);
    const required = ['1', 'true', 'yes'].includes(
      (process.env.REVA_ROKID_PUSHUP_APK_REQUIRED || '').toLowerCase(),
    );

    if (!apkSource) {
      const message = [
        '[withRokidPushupApk] no Rokid push-up APK found;',
        'set REVA_ROKID_PUSHUP_APK_PATH or build apps/rokid-pushup-glasses first.',
      ].join(' ');
      if (required) {
        throw new Error(message);
      }
      console.warn(message);
      return cfg;
    }

    const dest = path.join(iosRoot, RESOURCE_DEST);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(apkSource, dest);

    const project = cfg.modResults;
    const mainTargetUuid = findMainTargetUuid(project);
    if (!mainTargetUuid) {
      throw new Error('withRokidPushupApk could not find HealthPilot target');
    }

    if (!hasFileReference(project, BUNDLED_APK_NAME)) {
      project.addResourceFile(RESOURCE_DEST, { target: mainTargetUuid });
    }
    return cfg;
  });
}

module.exports = withRokidPushupApk;
module.exports._findRokidPushupApk = findRokidPushupApk;
module.exports._BUNDLED_APK_NAME = BUNDLED_APK_NAME;
