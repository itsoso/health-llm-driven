const assert = require('node:assert/strict');
const { test } = require('node:test');
const { createRequire } = require('node:module');
const path = require('node:path');

const easRoot = path.dirname(require.resolve('eas-cli/package.json'));
const easRequire = createRequire(path.join(easRoot, 'package.json'));

test('patch is idempotent and rejects unknown or partially changed vendor bytes', () => {
  const { adaptSource } = require('./apply-compat-patches.cjs');
  const source = require('node:fs').readFileSync(path.join(easRoot, 'build/commandUtils/new/projectFiles.js'), 'utf8');
  const patched = adaptSource(source);
  assert.equal(adaptSource(patched), patched);
  assert.throws(() => adaptSource(source + '\n// unexpected drift'), /source drift/);
  assert.throws(() => adaptSource(source.replace('generateAppConfigAsync', 'changed')), /source drift/);
});

test('real EAS project config merges normal fields and rejects unsafe prototype keys', async () => {
  // Only filesystem boundaries are mocked; execute the installed EAS and merge implementations.
  const fs = easRequire('fs-extra');
  const originalRead = fs.readJson;
  const originalWrite = fs.writeJson;
  let written;
  fs.readJson = async () => ({ expo: JSON.parse('{"ios":{"supportsTablet":false},"extra":{"safe":true,"toString":0,"__proto__":{"polluted":true}}}') });
  fs.writeJson = async (_file, value) => { written = value; };
  try {
    const { generateAppConfigAsync } = require(path.join(easRoot, 'build/commandUtils/new/projectFiles.js'));
    await generateAppConfigAsync('/synthetic-project', {
      id: '00000000-0000-4000-8000-000000000001', slug: 'fixture', name: 'Fixture',
      ownerAccount: { name: 'fixture' },
    });
    assert.equal(written.expo.ios.supportsTablet, false);
    assert.equal(written.expo.ios.bundleIdentifier, 'com.fixture.fixture');
    assert.equal(written.expo.extra.safe, true);
    assert.equal(written.expo.extra.eas.projectId, '00000000-0000-4000-8000-000000000001');
    assert.equal(typeof written.expo.extra.toString, 'function');
    assert.equal(Object.hasOwn(written.expo.extra, '__proto__'), false);
    assert.equal({}.polluted, undefined);
  } finally {
    fs.readJson = originalRead;
    fs.writeJson = originalWrite;
  }
});
