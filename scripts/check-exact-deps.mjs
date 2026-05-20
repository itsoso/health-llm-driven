#!/usr/bin/env node
import fs from "node:fs";

const manifests = [
  "package.json",
  "frontend/package.json",
  "mobile/package.json",
];

const versionFields = ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"];
const rangePrefixes = ["^", "~"];
const violations = [];

for (const manifest of manifests) {
  if (!fs.existsSync(manifest)) continue;
  const pkg = JSON.parse(fs.readFileSync(manifest, "utf8"));
  for (const field of versionFields) {
    const deps = pkg[field] || {};
    for (const [name, version] of Object.entries(deps)) {
      if (typeof version === "string" && rangePrefixes.some((prefix) => version.startsWith(prefix))) {
        violations.push(`${manifest} ${field}.${name}=${version}`);
      }
    }
  }
}

if (violations.length > 0) {
  console.error("Dependency versions must be exact. Remove ^/~ ranges:");
  for (const line of violations) console.error(`- ${line}`);
  process.exit(1);
}
