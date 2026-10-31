// The old Forge exception is retired. A pinned upstream package never bypasses OSV.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { evaluateInstalledOsvFindings } from './osv-npm-audit-gate.mjs';
import verifier from './node-forge-backport.cjs';
const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const source = process.env.NODE_FORGE_TEST_SOURCE || dirname(require.resolve('node-forge/package.json', {
  paths: [join(here, 'release-tools'), join(here, '../mobile')],
}));
const advisories = ['GHSA-86w9-cpqp-85rv', 'GHSA-5x38-2vff-x55p', 'GHSA-7wch-p9px-956x',
  'GHSA-8hrf-8g6f-7xwp', 'GHSA-hqq3-7jhf-c5jx', 'GHSA-jc66-7q78-782g'];
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'reva-osv-upstream-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const dest = join(root, 'node_modules/node-forge');
  mkdirSync(dirname(dest), { recursive: true }); cpSync(source, dest, { recursive: true });
  return root;
}
for (const version of ['1.4.0', '1.4.1']) {
  test(`every reported Forge advisory remains blocking for ${version}`, async (t) => {
    const root = fixture(t);
    verifier.verifyInstallation({ projectRoot: root, apply: true });
    const findings = advisories.map(id => ({ id, packageName: 'node-forge', version, lockPath: 'node_modules/node-forge' }));
    const detailsById = new Map(advisories.map(id => [id, { database_specific: { severity: 'HIGH' } }]));
    const result = await evaluateInstalledOsvFindings({ projectRoot: root, findings, detailsById,
      policy: { exceptions: [], verified_backport: findings, verify_command: 'must-not-execute' } });
    assert.equal(result.blocked.length, findings.length);
    assert.deepEqual(result.verified_backport, []); assert.deepEqual(result.findings, findings);
  });
}
test('upstream verification refuses a relabelled vulnerable version', t => {
  const root = fixture(t), file = join(root, 'node_modules/node-forge/package.json');
  const data = JSON.parse(readFileSync(file)); data.version = '1.4.0'; writeFileSync(file, JSON.stringify(data));
  assert.throws(() => verifier.verifyInstallation({ projectRoot: root, apply: true }), /identity drift/);
});
test('CLI fails closed for a future advisory even with a verified upstream installation', t => {
  const root = fixture(t); verifier.verifyInstallation({ projectRoot: root });
  const lock = join(root, 'package-lock.json');
  writeFileSync(lock, JSON.stringify({ packages: { 'node_modules/node-forge': { version: '1.4.1' } } }));
  const networkFixture = 'data:text/javascript,' + encodeURIComponent(`
    globalThis.fetch = async url => ({ok:true,text:async()=>JSON.stringify(url.endsWith('querybatch')
      ? {results:[{vulns:[{id:'GHSA-future'}]}]} : {id:'GHSA-future',database_specific:{severity:'HIGH'}})});
  `);
  const result = spawnSync(process.execPath, ['--import', networkFixture, join(here, 'osv-npm-audit-gate.mjs'), '--lockfile', lock], {encoding:'utf8',timeout:30000});
  assert.equal(result.status, 1, result.stderr); assert.match(result.stderr, /GHSA-future/);
});
