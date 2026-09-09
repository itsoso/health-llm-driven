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
  it('decodes navigation parameters through the real query-string consumer', () => {
    runParserCheck(`
      const assert = require('node:assert/strict');
      const query = require('query-string');
      assert.equal(query.parse('message=%E4%BD%A0%E5%A5%BD').message, '你好');
      assert.equal(query.parse('message=%E0%A4').message, '%E0%A4');
      const hostile = '%E0%A4'.repeat(20000);
      assert.equal(query.parse('message=' + hostile).message, hostile);
      assert.equal(query.parse('message=a+b').message, 'a b');
    `);
  });

  it('opens a React Navigation route with decoded query parameters', () => {
    runParserCheck(`
      const assert = require('node:assert/strict');
      const path = require('node:path');
      const { pathToFileURL } = require('node:url');
      const root = path.dirname(require.resolve('@react-navigation/core/package.json'));
      import(pathToFileURL(path.join(root, 'lib/module/getStateFromPath.js')).href).then(({ getStateFromPath }) => {
        const state = getStateFromPath('/chat?message=%E4%BD%A0%E5%A5%BD', { screens: { Chat: 'chat' } });
        assert.equal(state.routes[0].name, 'Chat');
        assert.equal(state.routes[0].params.message, '你好');
      }).catch(error => { console.error(error); process.exitCode = 1; });
    `);
  });

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
