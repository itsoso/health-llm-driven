'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

const source = process.env.NODE_FORGE_TEST_SOURCE || path.dirname(require.resolve('node-forge/package.json', {
  paths: [path.join(__dirname, 'release-tools'), path.join(__dirname, '../mobile')],
}));

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'reva-forge-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const packageDir = path.join(root, 'node_modules/node-forge');
  fs.mkdirSync(path.dirname(packageDir), { recursive: true });
  fs.cpSync(source, packageDir, { recursive: true });
  return { root, packageDir };
}

function verifyVectors(packageDir) {
  const forge = require(path.join(packageDir, 'lib/index.js'));
  const keys = crypto.generateKeyPairSync('rsa', { modulusLength: 1024, publicExponent: 3 });
  const pub = forge.pki.publicKeyFromPem(keys.publicKey.export({ type: 'spki', format: 'pem' }));
  const digest = crypto.createHash('sha256').update('public backport regression').digest();
  const oid = Buffer.from('0609608648016503040201', 'hex');
  function sign(elements) {
    const algorithm = Buffer.concat([Buffer.from([0x30, elements.length]), elements]);
    const info = Buffer.concat([algorithm, Buffer.from([4, 32]), digest]);
    const der = Buffer.concat([Buffer.from([0x30, info.length]), info]);
    const em = Buffer.concat([Buffer.from([0, 1]), Buffer.alloc(128 - der.length - 3, 255), Buffer.from([0]), der]);
    return crypto.privateEncrypt({ key: keys.privateKey, padding: crypto.constants.RSA_NO_PADDING }, em).toString('binary');
  }
  const plain = sign(oid);
  const withNull = sign(Buffer.concat([oid, Buffer.from([5, 0])]));
  const extra = sign(Buffer.concat([oid, Buffer.from([5, 0, 4, 1, 0])]));
  assert.equal(pub.verify(digest.toString('binary'), plain), true, 'OID only');
  assert.equal(pub.verify(digest.toString('binary'), withNull), true, 'OID + NULL');
  assert.equal(pub.verify(Buffer.alloc(32).toString('binary'), withNull), false, 'wrong signature');
  assert.throws(() => pub.verify(digest.toString('binary'), extra), /does not contain a valid RSASSA-PKCS1-v1_5/);
}

test('public verify rejects extra nested elements while accepting both valid encodings', (t) => {
  const { root, packageDir } = fixture(t);
  require('./node-forge-backport.cjs').verifyInstallation({ projectRoot: root, apply: true });
  verifyVectors(packageDir);
});

const backport = require('./node-forge-backport.cjs');
const patchFile = path.join(__dirname, '../mobile/patches/node-forge+1.4.0.patch');
function restoreOriginal(packageDir) {
  const rsaFile = path.join(packageDir, 'lib/rsa.js');
  const lines = fs.readFileSync(patchFile, 'utf8').split(/^@@.*@@.*\n/m)[1].trimEnd().split('\n');
  const old = lines.filter((s) => s[0] !== '+').map((s) => s.slice(1)).join('\n') + '\n';
  const replacement = lines.filter((s) => s[0] !== '-').map((s) => s.slice(1)).join('\n') + '\n';
  const data = fs.readFileSync(rsaFile, 'utf8');
  if (data.includes(replacement)) fs.writeFileSync(rsaFile, data.replace(replacement, old));
}

test('default verification cannot mutate or accept the unpatched installation', (t) => {
  const { root, packageDir } = fixture(t);
  restoreOriginal(packageDir);
  const before = fs.readFileSync(path.join(packageDir, 'lib/rsa.js'));
  assert.throws(() => backport.verifyInstallation({ projectRoot: root }), /backport not applied/);
  assert.deepEqual(fs.readFileSync(path.join(packageDir, 'lib/rsa.js')), before);
});

test('all nested copies are patched, verified, and replayed without changing true version', (t) => {
  const { root, packageDir } = fixture(t);
  const nested = path.join(root, 'node_modules/@scope/parent/node_modules/node-forge');
  fs.mkdirSync(path.dirname(nested), { recursive: true });
  fs.cpSync(packageDir, nested, { recursive: true });
  restoreOriginal(packageDir); restoreOriginal(nested);
  const result = backport.verifyInstallation({ projectRoot: root, apply: true });
  assert.equal(result.copies.length, 2);
  for (const copy of result.copies) {
    assert.equal(copy.version, '1.4.0');
    assert.equal(copy.behaviorVerified, true);
    assert.equal(copy.advisory, 'GHSA-86w9-cpqp-85rv');
    assert.equal(copy.sourceSha256, backport.PIN.sourceSha256);
  }
  assert.deepEqual(backport.verifyInstallation({ projectRoot: root }), result);
  assert.deepEqual(backport.verifyInstallation({ projectRoot: root, apply: true }), result);
});

for (const damage of ['rsa', 'support', 'package', 'version', 'missing']) {
  test(`source or identity drift fails closed before any apply: ${damage}`, (t) => {
    const { root, packageDir } = fixture(t);
    restoreOriginal(packageDir);
    const before = fs.readFileSync(path.join(packageDir, 'lib/rsa.js'));
    const nested = path.join(root, 'node_modules/parent/node_modules/node-forge');
    fs.mkdirSync(path.dirname(nested), { recursive: true });
    fs.cpSync(packageDir, nested, { recursive: true });
    if (damage === 'rsa') fs.appendFileSync(path.join(nested, 'lib/rsa.js'), '\n// drift');
    if (damage === 'support') fs.appendFileSync(path.join(nested, 'lib/asn1.js'), '\n// drift');
    if (damage === 'package') fs.appendFileSync(path.join(nested, 'package.json'), '\n');
    if (damage === 'version') {
      const metadata = JSON.parse(fs.readFileSync(path.join(nested, 'package.json')));
      metadata.version = '1.4.1';
      fs.writeFileSync(path.join(nested, 'package.json'), JSON.stringify(metadata));
    }
    if (damage === 'missing') fs.unlinkSync(path.join(nested, 'lib/rsa.js'));
    assert.throws(() => backport.verifyInstallation({ projectRoot: root, apply: true }));
    assert.deepEqual(fs.readFileSync(path.join(packageDir, 'lib/rsa.js')), before);
  });
}

test('fixed patch drift fails closed even when the library is already patched', (t) => {
  const { root } = fixture(t);
  backport.verifyInstallation({ projectRoot: root, apply: true });
  const validatorDir = path.join(root, 'scripts');
  fs.mkdirSync(validatorDir);
  fs.copyFileSync(path.join(__dirname, 'node-forge-backport.cjs'), path.join(validatorDir, 'node-forge-backport.cjs'));
  fs.mkdirSync(path.join(root, 'mobile/patches'), { recursive: true });
  fs.writeFileSync(path.join(root, 'mobile/patches/node-forge+1.4.0.patch'), fs.readFileSync(patchFile, 'utf8') + '\n');
  const validator = require(path.join(validatorDir, 'node-forge-backport.cjs'));
  assert.throws(() => validator.verifyInstalledCopy({ projectRoot: root, lockPath: 'node_modules/node-forge' }), /patch digest mismatch/);
});

test('missing copies, path traversal, and linked packages cannot produce evidence', (t) => {
  const { root, packageDir } = fixture(t);
  for (const lockPath of ['../node-forge', 'node_modules/../node-forge', '/node_modules/node-forge',
    'node_modules/node-forge/../node-forge', 'node_modules/foo/lib/node-forge']) {
    assert.throws(() => backport.verifyInstalledCopy({ projectRoot: root, lockPath }), /Invalid/);
  }
  const elsewhere = path.join(root, 'elsewhere');
  fs.renameSync(packageDir, elsewhere);
  assert.throws(() => backport.verifyInstallation({ projectRoot: root }), /No installed/);
  fs.symlinkSync(elsewhere, packageDir, 'dir');
  assert.throws(() => backport.verifyInstallation({ projectRoot: root, apply: true }), /Linked/);
  assert.throws(() => backport.verifyInstalledCopy({ projectRoot: root, lockPath: 'node_modules/node-forge' }), /Non-regular/);
});

test('rsa file and library directory links are rejected without touching their target', (t) => {
  const { root, packageDir } = fixture(t);
  const file = path.join(packageDir, 'lib/rsa.js');
  const outside = path.join(root, 'rsa.js');
  fs.renameSync(file, outside);
  fs.symlinkSync(outside, file);
  const before = fs.readFileSync(outside);
  assert.throws(() => backport.verifyInstallation({ projectRoot: root, apply: true }), /Non-regular/);
  assert.deepEqual(fs.readFileSync(outside), before);
});

test('hard-linked source cannot redirect an apply outside the package', (t) => {
  const { root, packageDir } = fixture(t);
  const file = path.join(packageDir, 'lib/rsa.js');
  const outside = path.join(root, 'linked-rsa.js');
  fs.linkSync(file, outside);
  const before = fs.readFileSync(outside);
  assert.throws(() => backport.verifyInstallation({ projectRoot: root, apply: true }), /Non-regular/);
  assert.deepEqual(fs.readFileSync(outside), before);
});
