const assert = require('node:assert/strict');
const config = require('../next.config.js');
(async () => {
  const previous = process.env.EDU_SSO_ORIGIN;
  try {
    delete process.env.EDU_SSO_ORIGIN;
    let rules = await config.headers();
    assert.equal(rules.length, 3);
    assert.match(rules.find(r => r.source === '/connect/edu').headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self' https:\/\/edu.executor.life;/);
    assert.match(rules[0].headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self';/);
    process.env.EDU_SSO_ORIGIN = 'https://library.example.test';
    rules = await config.headers();
    const main = rules.find(r => r.source === '/:path*');
    const login = rules.find(r => r.source === '/connect/edu');
    assert.match(main.headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self';/);
    assert.match(login.headers.find(h => h.key === 'Content-Security-Policy').value, /form-action 'self' https:\/\/library.example.test;/);
    assert.equal(login.headers.find(h => h.key === 'Referrer-Policy').value, 'strict-origin');
    for (const invalid of ['http://library.example.test', 'https://library.example.test/path', 'https://user:pass@library.example.test', "https://library.example.test; script-src *"]) {
      process.env.EDU_SSO_ORIGIN = invalid;
      await assert.rejects(config.headers());
    }
    const rewrites = await config.rewrites();
    const eduRoute = rewrites.findIndex(r => r.source === '/api/v1/auth/sso/edu');
    assert.ok(eduRoute >= 0 && eduRoute < rewrites.findIndex(r => r.source === '/api/:path*'));
    assert.equal(rewrites[eduRoute].destination, `${process.env.BACKEND_URL || 'http://localhost:8000'}/api/v1/auth/sso/edu`);
    console.log('Edu SSO CSP and proxy smoke passed');
  } finally {
    if (previous === undefined) delete process.env.EDU_SSO_ORIGIN;
    else process.env.EDU_SSO_ORIGIN = previous;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
