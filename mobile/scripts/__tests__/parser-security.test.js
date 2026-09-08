/* global __dirname */
const { spawnSync } = require('child_process');
const path = require('path');

// Exercise the real Node build-tool dependencies, not Jest's transformed mocks.
function runParserCheck(source) {
  const result = spawnSync(process.execPath, ['-e', source], {
    cwd: path.resolve(__dirname, '../..'),
    encoding: 'utf8',
    timeout: 5000,
  });
  expect(result.error).toBeUndefined();
  expect(result.stderr).toBe('');
  expect(result.status).toBe(0);
}

describe('build parser security regressions', () => {
  it.each(['@istanbuljs/load-nyc-config', '@eslint/eslintrc'])(
    '%s YAML parser counts empty merge sources toward its limit', (consumer) => {
      runParserCheck(`
        const assert = require('node:assert/strict');
        const { createRequire } = require('node:module');
        const yaml = createRequire(require.resolve(${JSON.stringify(consumer)}))('js-yaml');
        assert.throws(() => yaml.load('base: &base [{}, {}, {}, {}, {}, {}]\\nmerged:\\n  <<: *base\\n',
          { maxTotalMergeKeys: 4 }), /maxTotalMergeKeys/);
        assert.deepEqual(yaml.load('base: &base {enabled: true}\\nmerged:\\n  <<: *base\\n'),
          { base: { enabled: true }, merged: { enabled: true } });
      `);
    },
  );

  it('rejects a mutated doctype name during well-formed XML serialization', () => {
    runParserCheck(`
      const assert = require('node:assert/strict');
      const { DOMImplementation, XMLSerializer } = require('@xmldom/xmldom');
      const impl = new DOMImplementation();
      const doctype = impl.createDocumentType('root', '', '');
      const doc = impl.createDocument(null, 'root', doctype);
      doctype.name = 'root><injected/';
      assert.throws(() => new XMLSerializer().serializeToString(doc, false, null,
        { requireWellFormed: true }));
    `);
  });

  it.each(['@expo/plist', 'plist'])('%s preserves normal iOS configuration roundtrips', (moduleName) => {
    runParserCheck(`
      const assert = require('node:assert/strict');
      const imported = require(${JSON.stringify(moduleName)});
      const plist = imported.default || imported;
      const input = { CFBundleDisplayName: '小巴健康', CFBundleIdentifier: 'life.executor.health',
        UIRequiresFullScreen: true, UIDeviceFamily: [1], NSAppTransportSecurity: { NSAllowsArbitraryLoads: false } };
      // Expo deliberately returns null-prototype dictionaries; compare their data.
      assert.deepEqual(JSON.parse(JSON.stringify(plist.parse(plist.build(input)))), input);
    `);
  });
});
