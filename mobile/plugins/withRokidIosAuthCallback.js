const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const ROKID_IMPORT_BLOCK = `#if canImport(RokidBridge)
internal import RokidBridge
#endif`;

const ROKID_OPEN_URL_HOOK = `    #if canImport(RokidBridge)
    RokidBridgeURLHandler.observeOpenURL(url)
    if RokidBridgeURLHandler.canHandleOpenURL(url) {
      _ = RokidBridgeURLHandler.handleOpenURL(url)
      return true
    }
    #endif

`;

function patchAppDelegateContents(contents) {
  let patched = contents;

  if (!patched.includes('internal import RokidBridge')) {
    const importAnchor = 'import ReactAppDependencyProvider\n';
    if (!patched.includes(importAnchor)) {
      throw new Error('withRokidIosAuthCallback could not find AppDelegate import anchor');
    }
    patched = patched.replace(importAnchor, `${importAnchor}\n${ROKID_IMPORT_BLOCK}\n`);
  }

  if (
    patched.includes('RokidBridgeURLHandler.canHandleOpenURL(url)')
    && !patched.includes('RokidBridgeURLHandler.observeOpenURL(url)')
  ) {
    patched = patched.replace(
      '    if RokidBridgeURLHandler.canHandleOpenURL(url) {',
      `    RokidBridgeURLHandler.observeOpenURL(url)
    if RokidBridgeURLHandler.canHandleOpenURL(url) {`,
    );
  }

  if (!patched.includes('RokidBridgeURLHandler.canHandleOpenURL(url)')) {
    const returnAnchor = '    return super.application(app, open: url, options: options) || RCTLinkingManager.application(app, open: url, options: options)\n';
    if (!patched.includes(returnAnchor)) {
      throw new Error('withRokidIosAuthCallback could not find AppDelegate open-url return anchor');
    }
    patched = patched.replace(returnAnchor, `${ROKID_OPEN_URL_HOOK}${returnAnchor}`);
  }

  return patched;
}

function isAppDelegateDirectory(entryName) {
  const lower = entryName.toLowerCase();
  return !lower.includes('watch')
    && !lower.includes('complication')
    && !lower.includes('extension')
    && !entryName.endsWith('.xcodeproj')
    && !entryName.endsWith('.xcworkspace');
}

function resolveGeneratedAppDelegatePath(platformProjectRoot, modRequest = {}) {
  const projectName = modRequest.projectName;
  if (projectName) {
    const projectAppDelegate = path.join(platformProjectRoot, projectName, 'AppDelegate.swift');
    if (fs.existsSync(projectAppDelegate)) return projectAppDelegate;
  }

  const candidates = fs.readdirSync(platformProjectRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && isAppDelegateDirectory(entry.name))
    .map((entry) => path.join(platformProjectRoot, entry.name, 'AppDelegate.swift'))
    .filter((candidate) => fs.existsSync(candidate))
    .sort();

  if (candidates.length > 0) return candidates[0];
  return path.join(platformProjectRoot, 'HealthPilot', 'AppDelegate.swift');
}

function withRokidIosAuthCallback(config) {
  return withDangerousMod(config, [
    'ios',
    (cfg) => {
      const appDelegatePath = resolveGeneratedAppDelegatePath(
        cfg.modRequest.platformProjectRoot,
        cfg.modRequest,
      );
      const contents = fs.readFileSync(appDelegatePath, 'utf8');
      const patched = patchAppDelegateContents(contents);
      if (patched !== contents) {
        fs.writeFileSync(appDelegatePath, patched, 'utf8');
      }
      return cfg;
    },
  ]);
}

module.exports = withRokidIosAuthCallback;
module.exports._patchAppDelegateContents = patchAppDelegateContents;
module.exports._resolveGeneratedAppDelegatePath = resolveGeneratedAppDelegatePath;
