#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="${ROOT_DIR}/mobile"

CONFIG_JSON="$(cd "${MOBILE_DIR}" && npx expo config --type public --json)"

node - "${MOBILE_DIR}" "${CONFIG_JSON}" <<'NODE'
const path = require('path');

const mobileDir = process.argv[2];
const config = JSON.parse(process.argv[3]);
const infoPlist = config.ios?.infoPlist || {};
const pluginPath = path.join(mobileDir, 'plugins', 'withIosSupportedOrientations.js');
const orientationPlugin = require(pluginPath);
const required = orientationPlugin._SUPPORTED_ORIENTATIONS;

const failures = [];
for (const key of ['UISupportedInterfaceOrientations', 'UISupportedInterfaceOrientations~ipad']) {
  const configured = infoPlist[key];
  if (!Array.isArray(configured)) {
    failures.push(`${key}: missing orientation array`);
    continue;
  }

  for (const orientation of required) {
    if (!configured.includes(orientation)) {
      failures.push(`${key}: missing ${orientation}`);
    }
  }
}

const plugins = config.plugins || [];
if (!plugins.some((plugin) => plugin === './plugins/withIosSupportedOrientations')) {
  failures.push('plugins: missing ./plugins/withIosSupportedOrientations');
}

const patched = orientationPlugin._applySupportedOrientationsToInfoPlist({
  UISupportedInterfaceOrientations: ['UIInterfaceOrientationPortrait'],
});
for (const key of ['UISupportedInterfaceOrientations', 'UISupportedInterfaceOrientations~ipad']) {
  for (const orientation of required) {
    if (!patched[key]?.includes(orientation)) {
      failures.push(`withIosSupportedOrientations: ${key} did not apply ${orientation}`);
    }
  }
}

if (failures.length > 0) {
  console.error('iOS orientation check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('iOS orientation check passed.');
NODE
