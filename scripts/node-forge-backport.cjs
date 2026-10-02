'use strict';
// Fixed backport of digitalbazaar/forge@ceba34402e329f0365134f23fe19898756527d65.
// This verifies a local mitigation; it does not assert an upstream fixed release.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const PIN = Object.freeze({
  advisory: 'GHSA-86w9-cpqp-85rv', version: '1.4.0',
  upstreamRevision: 'ceba34402e329f0365134f23fe19898756527d65',
  originalSha256: 'fd4740238145ec26470eb3f06a627c72039538ce1307dbdce40521f94dfd0a50',
  sourceSha256: 'acc22e5d36e27832c34e02dd3933aad7977d45b047eead5016520735efedc9c5',
  patchSha256: '661a391930d80461fc22397197e78bc00a55f6aadc32291f3f5195c3b4d8c1ae',
  packageSha256: 'a907bca8a62d97478062f2bd8ed5cd47d00b79385d3f08a8cad1c3bd7e3eb5bf',
  originalLibrarySha256: '74adb7d489d27a78a23e10b1210f2b3a07d44a050b8b864e7391d0207a83cbbb',
  librarySha256: '8c37afbc674974fd0926f86f318fada19206316553c23ee0bfebb7738b24bd20',
});
const PATCH_FILE = path.resolve(__dirname, '../mobile/patches/node-forge+1.4.0.patch');
const sha = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');

function regular(file, directory = false) {
  const stat = fs.lstatSync(file);
  if (stat.isSymbolicLink() || (directory ? !stat.isDirectory() : !stat.isFile() || stat.nlink !== 1)) {
    throw new Error(`Non-regular backport path: ${file}`);
  }
}

function checkedLocation(projectRoot, lockPath) {
  const root = fs.realpathSync(projectRoot);
  if (typeof lockPath !== 'string' || lockPath.includes('\\') || path.posix.normalize(lockPath) !== lockPath
      || !/^node_modules\/(?:(?:@[^/]+\/)?[^/]+\/node_modules\/)*node-forge$/.test(lockPath)
      || lockPath.split('/').some((part) => part === '..' || part === '.')) {
    throw new Error('Invalid node-forge lock path');
  }
  let location = root;
  for (const part of lockPath.split('/')) {
    location = path.join(location, part);
    regular(location, true);
  }
  return location;
}

function patchText() {
  regular(PATCH_FILE);
  const bytes = fs.readFileSync(PATCH_FILE);
  if (sha(bytes) !== PIN.patchSha256) throw new Error('Fixed node-forge patch digest mismatch');
  const text = bytes.toString('utf8');
  const hunks = text.split(/^@@.*@@.*\n/m);
  if (hunks.length !== 2) throw new Error('Unexpected fixed patch shape');
  const lines = hunks[1].split('\n');
  lines.pop();
  const before = lines.filter((line) => line[0] !== '+').map((line) => line.slice(1)).join('\n') + '\n';
  const after = lines.filter((line) => line[0] !== '-').map((line) => line.slice(1)).join('\n') + '\n';
  return { before, after };
}

function libraryHash(packageDir) {
  const files = [];
  function walk(dir) {
    regular(dir, true);
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isSymbolicLink()) throw new Error(`Symlink in node-forge library: ${file}`);
      if (entry.isDirectory()) walk(file);
      else if (entry.name.endsWith('.js')) {
        regular(file);
        files.push([path.relative(packageDir, file).split(path.sep).join('/'), sha(fs.readFileSync(file))]);
      }
    }
  }
  walk(path.join(packageDir, 'lib'));
  return sha(files.sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)
    .map(([name, digest]) => `${name}\0${digest}\n`).join(''));
}

function inspectCopy(projectRoot, lockPath) {
  patchText();
  const packageDir = checkedLocation(projectRoot, lockPath);
  const metadataPath = path.join(packageDir, 'package.json');
  regular(metadataPath);
  const metadataBytes = fs.readFileSync(metadataPath);
  const metadata = JSON.parse(metadataBytes);
  if (metadata.name !== 'node-forge' || metadata.version !== PIN.version
      || sha(metadataBytes) !== PIN.packageSha256) throw new Error('node-forge package identity drift');
  const rsaPath = path.join(packageDir, 'lib/rsa.js');
  regular(rsaPath);
  const bytes = fs.readFileSync(rsaPath);
  const digest = sha(bytes);
  if (![PIN.originalSha256, PIN.sourceSha256].includes(digest)) throw new Error('node-forge rsa.js source drift');
  const expectedLibrary = digest === PIN.sourceSha256 ? PIN.librarySha256 : PIN.originalLibrarySha256;
  if (libraryHash(packageDir) !== expectedLibrary) throw new Error('node-forge supporting library drift');
  return { packageDir, rsaPath, bytes, digest };
}

function publicVerification(packageDir) {
  // Re-read the inspected copy, never a previously cached or package.main module.
  for (const key of Object.keys(require.cache)) {
    if (key.startsWith(packageDir + path.sep)) delete require.cache[key];
  }
  const forge = require(path.join(packageDir, 'lib/index.js'));
  const pair = crypto.generateKeyPairSync('rsa', { modulusLength: 1024, publicExponent: 3 });
  const publicKey = forge.pki.publicKeyFromPem(pair.publicKey.export({ type: 'spki', format: 'pem' }));
  const digest = crypto.createHash('sha256').update('Reva fixed node-forge backport verification').digest();
  const oid = Buffer.from('0609608648016503040201', 'hex');
  function signature(children) {
    const algorithm = Buffer.concat([Buffer.from([0x30, children.length]), children]);
    const info = Buffer.concat([algorithm, Buffer.from([0x04, digest.length]), digest]);
    const der = Buffer.concat([Buffer.from([0x30, info.length]), info]);
    const encoded = Buffer.concat([Buffer.from([0, 1]), Buffer.alloc(128 - der.length - 3, 255), Buffer.from([0]), der]);
    return crypto.privateEncrypt({ key: pair.privateKey, padding: crypto.constants.RSA_NO_PADDING }, encoded).toString('binary');
  }
  const oidOnly = signature(oid);
  const oidNull = signature(Buffer.concat([oid, Buffer.from([5, 0])]));
  const nestedExtra = signature(Buffer.concat([oid, Buffer.from([5, 0, 4, 1, 0])]));
  assert.equal(publicKey.verify(digest.toString('binary'), oidOnly), true, 'OID-only verification failed');
  assert.equal(publicKey.verify(digest.toString('binary'), oidNull), true, 'OID+NULL verification failed');
  assert.equal(publicKey.verify(Buffer.alloc(32).toString('binary'), oidNull), false, 'Wrong signature accepted');
  assert.throws(() => publicKey.verify(digest.toString('binary'), nestedExtra),
    /ASN\.1 object does not contain a valid RSASSA-PKCS1-v1_5 DigestInfo value\./,
    'Extra nested DigestAlgorithm element accepted');
}

function verifyInstalledCopy({ projectRoot, lockPath }) {
  const copy = inspectCopy(projectRoot, lockPath);
  if (copy.digest !== PIN.sourceSha256) throw new Error(`node-forge backport not applied: ${lockPath}`);
  publicVerification(copy.packageDir);
  return { advisory: PIN.advisory, package: 'node-forge', version: PIN.version, lockPath,
    sourceSha256: PIN.sourceSha256, patchSha256: PIN.patchSha256,
    upstreamRevision: PIN.upstreamRevision, behaviorVerified: true };
}

function installedCopies(projectRoot) {
  const root = fs.realpathSync(projectRoot);
  const copies = [];
  function packages(modules) {
    regular(modules, true);
    for (const entry of fs.readdirSync(modules, { withFileTypes: true })) {
      if (entry.name.startsWith('.')) continue;
      const candidate = path.join(modules, entry.name);
      // Linked packages could conceal another installed copy; do not skip them.
      if (entry.isSymbolicLink()) throw new Error(`Linked package is not auditable: ${candidate}`);
      if (!entry.isDirectory()) continue;
      if (entry.name.startsWith('@')) { packages(candidate); continue; }
      if (entry.name === 'node-forge') copies.push(path.relative(root, candidate).split(path.sep).join('/'));
      const nested = path.join(candidate, 'node_modules');
      if (fs.existsSync(nested)) packages(nested);
    }
  }
  packages(path.join(root, 'node_modules'));
  if (copies.length === 0) throw new Error('No installed node-forge copy to verify');
  return copies.sort();
}

function verifyInstallation({ projectRoot, apply = false }) {
  if (typeof apply !== 'boolean') throw new Error('apply must be a boolean');
  const paths = installedCopies(projectRoot);
  // Check every copy before modifying any, so drift cannot produce a partial apply.
  const inspected = paths.map((lockPath) => ({ lockPath, ...inspectCopy(projectRoot, lockPath) }));
  if (apply) {
    const patch = patchText();
    for (const copy of inspected) {
      if (copy.digest === PIN.sourceSha256) continue;
      const original = copy.bytes.toString('utf8');
      if (original.split(patch.before).length !== 2) throw new Error('Fixed patch context mismatch');
      const patched = original.replace(patch.before, patch.after);
      if (sha(patched) !== PIN.sourceSha256) throw new Error('Fixed patch result digest mismatch');
      fs.writeFileSync(copy.rsaPath, patched, { flag: 'r+' });
    }
  }
  return { copies: paths.map((lockPath) => verifyInstalledCopy({ projectRoot, lockPath })) };
}

module.exports = { verifyInstalledCopy, verifyInstallation, PIN };
if (require.main === module) {
  try {
    const args = process.argv.slice(2);
    const apply = args.includes('--apply');
    const withoutApply = args.filter((arg) => arg !== '--apply');
    if (withoutApply.length !== 2 || withoutApply[0] !== '--root'
        || args.filter((arg) => arg === '--apply').length > 1) {
      throw new Error('Usage: node scripts/node-forge-backport.cjs --root ROOT [--apply]');
    }
    process.stdout.write(JSON.stringify(verifyInstallation({ projectRoot: withoutApply[1], apply })) + '\n');
  } catch (error) {
    process.stderr.write(`node-forge backport verification failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}
