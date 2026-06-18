#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_JSON="${ROOT_DIR}/mobile/app.json"

node - "${APP_JSON}" <<'NODE'
const fs = require('fs');

const appJsonPath = process.argv[2];
const appJson = JSON.parse(fs.readFileSync(appJsonPath, 'utf8'));
const infoPlist = appJson.expo?.ios?.infoPlist || {};
const required = [
  'UIInterfaceOrientationPortrait',
  'UIInterfaceOrientationPortraitUpsideDown',
  'UIInterfaceOrientationLandscapeLeft',
  'UIInterfaceOrientationLandscapeRight',
];

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

if (failures.length > 0) {
  console.error('iOS orientation check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('iOS orientation check passed.');
NODE
