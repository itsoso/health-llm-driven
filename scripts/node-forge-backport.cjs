'use strict';
// Fixed upstream release verifier; historical CLI name retained for release callers.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const PIN = Object.freeze({
  version: '1.4.1',
  packageSha256: '6d5f46f222e0b7e2d2986694018cc9fcd86f8300d1b80fb446b659d8fd16a06a',
  sourceSha256: '6632e195295ce76f6bb9131ee770dcd6cc1ee4ffac7906302208b00faf95a87f',
  librarySha256: 'cf45888813b48d869e71bf73531c48100b3ed632a53869d073019dcb829a52c7',
});
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
  if (digest !== PIN.sourceSha256) throw new Error('node-forge rsa.js source drift');
  if (libraryHash(packageDir) !== PIN.librarySha256) throw new Error('node-forge supporting library drift');
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
  publicVerification(copy.packageDir);
  return { package: 'node-forge', version: PIN.version, lockPath,
    sourceSha256: PIN.sourceSha256, librarySha256: PIN.librarySha256,
    remediation: 'upstream-fixed-release', behaviorVerified: true };
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
  // --apply is retained for existing callers. Verification never changes vendor bytes.
  paths.forEach((lockPath) => inspectCopy(projectRoot, lockPath));
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
