const assert = require('node:assert/strict');
const config = require('../next.config.js');
(async () => {
  const previous = process.env.KBASE_SSO_ORIGIN;
  try {
    delete process.env.KBASE_SSO_ORIGIN;
    let rules = await config.headers();
    assert.equal(rules.length, 2);
    assert.match(rules[1].headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self' https:\/\/kbase.executor.life;/);
    assert.match(rules[0].headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self';/);
    process.env.KBASE_SSO_ORIGIN = 'https://library.example.test';
    rules = await config.headers();
    const main = rules.find(r => r.source === '/:path*');
    const login = rules.find(r => r.source === '/connect/kbase');
    assert.match(main.headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self';/);
    assert.match(login.headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self' https:\/\/library.example.test;/);
    assert.equal(login.headers.find(h => h.key === 'Referrer-Policy').value, 'strict-origin');
    for (const invalid of ['http://library.example.test', 'https://library.example.test/path', 'https://user:pass@library.example.test', "https://library.example.test; script-src *"]) {
      process.env.KBASE_SSO_ORIGIN = invalid;
      await assert.rejects(config.headers());
    }
    console.log('KBase SSO CSP smoke passed');
  } finally {
    if (previous === undefined) delete process.env.KBASE_SSO_ORIGIN;
    else process.env.KBASE_SSO_ORIGIN = previous;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
