#!/usr/bin/env node
// Anonymous route availability only; never sends cookies or stores page contents.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
function option(name, fallback) {
  const index = args.indexOf(name);
  return index < 0 ? fallback : args[index + 1];
}
const base = new URL(option('--base-url', 'https://health.executor.life'));
if (!['https:', 'http:'].includes(base.protocol) || base.username || base.password || base.pathname !== '/' || base.search || base.hash) {
  throw new Error('base-url must be an HTTP(S) origin without credentials, path, query or fragment');
}
const source = ts.createSourceFile('Navigation.tsx', fs.readFileSync(path.join(root, 'src/components/Navigation.tsx'), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const routes = new Set();
function visit(node) {
  if (ts.isPropertyAssignment(node) && node.name.getText(source) === 'href' && ts.isStringLiteral(node.initializer) && node.initializer.text.startsWith('/')) routes.add(node.initializer.text);
  if (ts.isJsxAttribute(node) && node.name.getText(source) === 'href' && node.initializer && ts.isStringLiteral(node.initializer) && node.initializer.text.startsWith('/')) routes.add(node.initializer.text);
  ts.forEachChild(node, visit);
}
visit(source);
function request(url) {
  return new Promise(resolve => {
    const transport = url.protocol === 'https:' ? https : http;
    const req = transport.get(url, { headers: { 'User-Agent': 'HealthPageAudit/1.0' } }, response => {
      let body = '', bytes = 0;
      response.on('data', chunk => { bytes += chunk.length; if (bytes <= 65536) body += chunk.toString('utf8'); });
      response.on('end', () => resolve({ status: response.statusCode, location: response.headers.location,
        notFound: /<h1[^>]*>404<\/h1>|This page could not be found/.test(body) }));
      response.on('error', error => resolve({ status: null, errorType: error.code || error.name }));
    });
    req.setTimeout(15000, () => req.destroy(Object.assign(new Error('timeout'), { code: 'TIMEOUT' })));
    req.on('error', error => resolve({ status: null, errorType: error.code || error.name }));
  });
}
async function check(route) {
  let url = new URL(route, base), redirects = [];
  for (let attempt = 0; attempt < 4; attempt++) {
    const result = await request(url);
    if (result.status >= 300 && result.status < 400 && result.location) {
      const destination = new URL(result.location, url);
      if (destination.origin !== base.origin) return { path: route, status: result.status, errorType: 'REDIRECT_OUTSIDE_ORIGIN', redirects };
      redirects.push({ status: result.status, destination: destination.pathname });
      url = destination;
      continue;
    }
    return { path: route, status: result.status, notFound: result.notFound || false,
      finalPath: url.pathname, redirects, ...(result.errorType ? { errorType: result.errorType } : {}) };
  }
  return { path: route, status: null, errorType: 'REDIRECT_LIMIT', redirects };
}
(async () => {
  const pending = [...routes].sort(), results = [];
  async function worker() { while (pending.length) results.push(await check(pending.shift())); }
  await Promise.all(Array.from({ length: Math.min(3, pending.length) }, worker));
  results.sort((a, b) => a.path.localeCompare(b.path));
  const problems = results.filter(item => item.status !== 200 || item.notFound || item.errorType);
  const report = { checkedAt: new Date().toISOString(), baseUrl: base.origin,
    scope: 'anonymous HTTP route availability; authenticated data and interactions not verified',
    routesChecked: results.length, problemCount: problems.length, results };
  const out = option('--out');
  if (out) fs.writeFileSync(path.resolve(out), JSON.stringify(report, null, 2) + '\n');
  process.stdout.write(JSON.stringify({ routesChecked: report.routesChecked, problemCount: problems.length, problems }) + '\n');
  process.exitCode = problems.length ? 1 : 0;
})().catch(error => { process.stderr.write(`Audit failed: ${error.code || error.name}\n`); process.exitCode = 2; });
