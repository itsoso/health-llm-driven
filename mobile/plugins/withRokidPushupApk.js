const { withXcodeProject } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const BUNDLED_APK_NAME = 'rokid-pushup-glasses.apk';
const LEGACY_PROJECT_NAME = 'HealthPilot';

function buildResourceDest(projectName = LEGACY_PROJECT_NAME) {
  return path.join(projectName || LEGACY_PROJECT_NAME, 'RokidApps', BUNDLED_APK_NAME);
}

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
    const name = String(target?.name || '').replace(/^"|"$/g, '');
    if (!uuid.endsWith('_comment') && name === targetName) {
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

function ensureResourcesGroup(project) {
  if (project.pbxGroupByName('Resources')) {
    return;
  }

  const resourcesGroup = project.addPbxGroup([], 'Resources');
  if (resourcesGroup.pbxGroup?.path == null) {
    delete resourcesGroup.pbxGroup.path;
  }

  const mainGroup = project.getFirstProject()?.firstProject?.mainGroup;
  if (mainGroup) {
    project.addToPbxGroup(resourcesGroup.uuid, mainGroup);
  }
}

function addBundledApkResource(project, mainTargetUuid, resourceDest = buildResourceDest()) {
  ensureResourcesGroup(project);
  return project.addResourceFile(resourceDest, {
    target: mainTargetUuid,
    sourceTree: 'SOURCE_ROOT',
  });
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

    const mainTargetName = cfg.modRequest.projectName || 'HealthPilot';
    const resourceDest = buildResourceDest(mainTargetName);
    const dest = path.join(iosRoot, resourceDest);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(apkSource, dest);

    const project = cfg.modResults;
    const mainTargetUuid = findMainTargetUuid(project, mainTargetName);
    if (!mainTargetUuid) {
      throw new Error(`withRokidPushupApk could not find ${mainTargetName} target`);
    }

    if (!hasFileReference(project, BUNDLED_APK_NAME)) {
      addBundledApkResource(project, mainTargetUuid, resourceDest);
    }
    return cfg;
  });
}

module.exports = withRokidPushupApk;
module.exports._findRokidPushupApk = findRokidPushupApk;
module.exports._ensureResourcesGroup = ensureResourcesGroup;
module.exports._addBundledApkResource = addBundledApkResource;
module.exports._buildResourceDest = buildResourceDest;
module.exports._BUNDLED_APK_NAME = BUNDLED_APK_NAME;
