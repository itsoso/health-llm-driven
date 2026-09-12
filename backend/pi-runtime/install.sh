#!/usr/bin/env bash
# Install only this private package; host Node/npm provisioning is an operator task.
set -euo pipefail

if ! command -v node >/dev/null 2>&1; then
  printf '%s\n' 'Pi runtime requires Node >=22.19.0; node is missing from PATH. Provision Node on this host before deploying.' >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  printf '%s\n' 'Pi runtime requires npm; npm is missing from PATH. Provision npm on this host before deploying.' >&2
  exit 1
fi
if ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 22 || (major === 22 && minor >= 19) ? 0 : 1)'; then
  printf '%s\n' 'Pi runtime requires a working Node >=22.19.0. Upgrade the host runtime before deploying; no dependencies were changed.' >&2
  exit 1
fi

runtime_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$runtime_dir"
if [[ ! -f package-lock.json ]]; then
  printf '%s\n' 'Pi runtime install failed: committed package-lock.json is missing.' >&2
  exit 1
fi
npm ci --omit=dev --ignore-scripts --no-fund

node --input-type=module <<'JS'
import { readFileSync } from 'node:fs';
import { Agent } from '@earendil-works/pi-agent-core';
import { createAssistantMessageEventStream } from '@earendil-works/pi-ai';

const manifest = JSON.parse(readFileSync('package.json', 'utf8'));
for (const name of ['@earendil-works/pi-agent-core', '@earendil-works/pi-ai']) {
  const expected = manifest.dependencies[name];
  const installed = JSON.parse(readFileSync(`node_modules/${name}/package.json`, 'utf8')).version;
  if (!/^\d+\.\d+\.\d+$/.test(expected) || installed !== expected) {
    throw new Error(`Pi runtime install failed: ${name} does not match its exact manifest pin`);
  }
}
if (typeof Agent !== 'function' || typeof createAssistantMessageEventStream !== 'function') {
  throw new Error('Pi runtime install failed: official Pi API import check failed');
}
console.log('Pi runtime dependency pins and official API imports verified.');
JS
