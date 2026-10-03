'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const guard = require('../frontend/scripts/braces-depth-guard.cjs');
const sourceRoot = path.resolve(process.env.BRACES_TEST_ROOT || 'mobile');
const source = path.join(sourceRoot, 'node_modules/braces');
const patch = path.resolve('mobile/patches/braces+3.0.3.patch');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'reva-braces-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const dir = path.join(root, 'node_modules/braces');
  fs.mkdirSync(path.dirname(dir));
  fs.cpSync(source, dir, {recursive:true});
  for (const name of ['fill-range', 'to-regex-range', 'is-number']) {
    const dep = path.dirname(require.resolve(`${name}/package.json`, {paths:[source]}));
    fs.cpSync(dep, path.join(root, 'node_modules', name), {recursive:true});
  }
  if (fs.readFileSync(path.join(dir, 'lib/compile.js'), 'utf8').includes('maximum nesting depth')) {
    const reverse = spawnSync('git', ['apply', '--reverse', '--unidiff-zero', patch], {cwd:root, encoding:'utf8'});
    assert.equal(reverse.status, 0, reverse.stderr);
  }
  return {root, dir};
}

test('verification is read-only; apply covers each nested copy and is idempotent', t => {
  const {root, dir} = fixture(t);
  const nested = path.join(root, 'node_modules/@scope/parent/node_modules/braces');
  fs.mkdirSync(path.dirname(nested), {recursive:true}); fs.cpSync(dir, nested, {recursive:true});
  const before = fs.readFileSync(path.join(dir, 'lib/parse.js'));
  assert.throws(() => guard.verifyInstallation({projectRoot:root}), /not applied/);
  assert.deepEqual(fs.readFileSync(path.join(dir, 'lib/parse.js')), before);
  const result = guard.verifyInstallation({projectRoot:root, apply:true});
  assert.equal(result.copies.length, 2);
  assert.ok(result.copies.every(x => x.version === '3.0.3' && x.behaviorVerified));
  assert.deepEqual(guard.verifyInstallation({projectRoot:root, apply:true}), result);
});
for (const file of ['lib/compile.js', 'lib/utils.js', 'index.js', 'package.json']) {
  test(`drift in ${file} rejects every copy before applying`, t => {
    const {root, dir} = fixture(t);
    const nested = path.join(root, 'node_modules/parent/node_modules/braces');
    fs.mkdirSync(path.dirname(nested), {recursive:true}); fs.cpSync(dir, nested, {recursive:true});
    fs.appendFileSync(path.join(nested, file), '\n// drift');
    const before = fs.readFileSync(path.join(dir, 'lib/parse.js'));
    assert.throws(() => guard.verifyInstallation({projectRoot:root, apply:true}), /drift/);
    assert.deepEqual(fs.readFileSync(path.join(dir, 'lib/parse.js')), before);
  });
}
test('missing source, unknown executable, traversal, symlinks and hardlinks fail closed', t => {
  for (const damage of ['missing','extra','symbolic','hard']) {
    const {root, dir} = fixture(t);
    const file = path.join(dir, 'lib/compile.js');
    for (const lockPath of ['../braces','/node_modules/braces','node_modules/../braces']) {
      assert.throws(() => guard.verifyInstalledCopy({projectRoot:root, lockPath}), /Invalid/);
    }
    if (damage==='missing') fs.unlinkSync(file);
    if (damage==='extra') fs.writeFileSync(path.join(dir,'lib/extra.js'), '');
    if (damage==='hard') fs.linkSync(file, path.join(root,'outside.js'));
    if (damage==='symbolic') {fs.renameSync(file, path.join(root,'outside.js')); fs.symlinkSync(path.join(root,'outside.js'),file);}
    assert.throws(() => guard.verifyInstallation({projectRoot:root, apply:true}));
  }
});
test('patch-package artifact produces exactly the verified source bytes', t => {
  const {root} = fixture(t);
  const applied = spawnSync('git', ['apply', '--unidiff-zero', patch], {cwd:root, encoding:'utf8'});
  assert.equal(applied.status,0,applied.stderr);
  assert.equal(guard.verifyInstallation({projectRoot:root}).copies.length,1);
});
test('OSV keeps original HIGH finding, rejects missing/partial/unrelated evidence', async t => {
  const {evaluateInstalledOsvFindings} = await import('./osv-npm-audit-gate.mjs');
  const {root} = fixture(t);
  const finding = {id:guard.PIN.advisory, packageName:'braces', version:'3.0.3', lockPath:'node_modules/braces'};
  const detailsById = new Map([[finding.id,{database_specific:{severity:'HIGH'}}],['OTHER',{database_specific:{severity:'HIGH'}}]]);
  const evaluate = findings => evaluateInstalledOsvFindings({projectRoot:root, findings, detailsById, policy:{exceptions:[]}});
  assert.equal((await evaluate([finding])).blocked.length,1);
  guard.verifyInstallation({projectRoot:root,apply:true});
  const findings = [finding,{...finding,lockPath:'node_modules/missing/node_modules/braces'},{...finding,id:'OTHER'}];
  const result = await evaluate(findings);
  assert.equal(result.blocked.length,2);
  assert.deepEqual(result.findings, findings);
  assert.equal(result.allowed.length,0);
  assert.equal(result.verified_mitigation.length,1);
  assert.equal(result.verified_mitigation[0].severity,'HIGH');
  assert.equal((await evaluate([{...finding,version:'3.0.4'}])).blocked.length,1);
});
