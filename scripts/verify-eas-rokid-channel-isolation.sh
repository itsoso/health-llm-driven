#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EAS_JSON="${ROOT_DIR}/mobile/eas.json"

node - "${EAS_JSON}" <<'NODE'
const fs = require('fs');

const easPath = process.argv[2];
const eas = JSON.parse(fs.readFileSync(easPath, 'utf8'));
const profiles = eas.build || {};
const failures = [];

for (const [name, profile] of Object.entries(profiles)) {
  if (!name.startsWith('rokid-')) continue;

  const channel = profile.channel;
  if (!channel) {
    failures.push(`${name}: missing channel`);
    continue;
  }

  if (channel !== name) {
    failures.push(`${name}: channel must be "${name}", got "${channel}"`);
  }

  if (channel === 'production' || channel === 'preview' || channel === 'development') {
    failures.push(`${name}: must not share the generic "${channel}" channel`);
  }
}

if (failures.length > 0) {
  console.error('Rokid EAS channel isolation check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('Rokid EAS channel isolation check passed.');
NODE
