const test = require('node:test');
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');

for (const format of ['CJS', 'ESM']) {
  test(`Zod v3 ${format} rejects oversized collections before walking elements`, async () => {
    const { z } = format === 'CJS' ? require('zod/v3') : await import('zod/v3');
    let walked = 0;
    const element = z.string().refine(() => { walked += 1; return true; });
    for (const [schema, input] of [
      [z.array(element).max(2), Array(100).fill('a')],
      [z.array(element).length(2), Array(100).fill('a')],
      [z.set(element).max(2), new Set(['a', 'b', 'c'])],
      [z.set(element).size(2), new Set(['a', 'b', 'c'])],
    ]) {
      for (const result of [schema.safeParse(input), await schema.safeParseAsync(input)]) {
        assert.equal(result.success, false);
        assert.equal(result.error.issues.length, 1);
        assert.equal(result.error.issues[0].code, 'too_big');
      }
      assert.equal(walked, 0);
    }
    assert.deepEqual(z.array(element).max(2).parse(['a']), ['a']);
    assert.deepEqual([...z.set(element).max(2).parse(new Set(['a']))], ['a']);
    assert.equal(z.array(z.string()).length(2).safeParse(['a']).success, false);
    assert.equal(z.set(z.string()).min(2).safeParse(new Set(['a'])).success, false);
  });
}

test('Expo MCP factory preserves constraints through the v3 converter', () => {
  const { z } = require('zod/v3');
  const { zodToJsonSchema } = require('zod-to-json-schema');
  const base = '../node_modules/expo/node_modules/@expo/cli/build/src/start/server/';
  const { createMCPDevToolsExtensionSchema } = require(base + 'createMCPDevToolsExtensionSchema.js');
  const { PluginSchema, DevToolsPluginOutputSchema } = require(base + 'DevToolsPlugin.schema.js');
  const plugin = { packageName: 'synthetic-test', packageRoot: '/tmp/synthetic', cliExtensions: {
    description: 'test', entryPoint: 'index.js', commands: [{ name: 'check', title: 'Check',
      environments: ['cli', 'mcp'], parameters: [{ name: 'count', type: 'number' },
        { name: 'enabled', type: 'confirm' }, { name: 'label', type: 'text' }] }],
  } };
  assert.equal(PluginSchema.safeParse(plugin).success, true);
  assert.equal(PluginSchema.safeParse({ ...plugin, packageName: '' }).success, false);
  const schema = createMCPDevToolsExtensionSchema(plugin);
  // @expo/mcp-tunnel 0.2.4 registerTool wraps the raw shape this way.
  const wire = zodToJsonSchema(z.object({ parameters: schema }));
  const parameters = wire.properties.parameters;
  assert.equal(parameters.type, 'object');
  assert.equal(parameters.additionalProperties, false);
  assert.deepEqual(parameters.required, ['command']);
  assert.deepEqual(parameters.properties.command.enum, ['check']);
  assert.equal(parameters.properties.count.type, 'number');
  assert.equal(parameters.properties.enabled.type, 'boolean');
  assert.equal(parameters.properties.label.type, 'string');
  assert.equal(schema.safeParse({ command: 'check', count: 1, enabled: true, label: 'test' }).success, true);
  for (const input of [{ command: 'unknown' }, { command: 'check', count: '1' }, { command: 'check', injected: true }]) {
    assert.equal(schema.safeParse(input).success, false);
  }
  assert.equal(DevToolsPluginOutputSchema.safeParse([{ type: 'text', text: 'ok', level: 'info' }]).success, true);
  assert.equal(DevToolsPluginOutputSchema.safeParse([{ type: 'audio', url: 'invalid' }]).success, false);
});

test('body-parser survives trailing compressed bytes and parses subsequent requests', () => {
  const source = `
    const http = require('node:http'); const zlib = require('node:zlib');
    const parse = require('body-parser').json();
    const server = http.createServer((req,res) => parse(req,res,error => {
      res.statusCode = error ? 400 : 200; res.end(error ? 'rejected' : JSON.stringify(req.body));
    }));
    async function send(port, body, encoding) { return new Promise((resolve,reject) => {
      const req = http.request({port, host:'127.0.0.1', method:'POST', headers:{
        'content-type':'application/json', 'content-length':body.length,
        ...(encoding ? {'content-encoding':encoding} : {})}}, res => {
          let data='';res.on('data',chunk=>data+=chunk);res.on('end',()=>resolve([res.statusCode,data]));
      });req.on('error',reject);req.end(body);
    }); }
    server.listen(0,'127.0.0.1',async()=>{try {
      const port=server.address().port;
      await send(port,Buffer.concat([zlib.gzipSync('{}'),Buffer.from([255,255,255])]),'gzip');
      await new Promise(resolve=>setTimeout(resolve,50));
      const result=await send(port,Buffer.from('{"ok":true}'));
      if(result[0]!==200 || JSON.parse(result[1]).ok!==true)throw Error('parser not healthy');
      server.close();
    }catch(error){console.error(error.message);process.exit(1);}});
  `;
  const result = spawnSync(process.execPath, ['-e', source], { cwd: require('node:path').resolve(__dirname, '..'), encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 0, result.stderr || String(result.error));
});

test('cross-realm sensitive headers stay on origin and are stripped on cross-origin redirects', { timeout: 20000 }, async () => {
  const http = require('node:http');
  const vm = require('node:vm');
  const { once } = require('node:events');
  const follow = require(process.env.FOLLOW_REDIRECTS_TEST_SOURCE || 'follow-redirects').http;
  const target = http.createServer((req, res) => { res.end(JSON.stringify(req.headers)); });
  target.listen(0, '127.0.0.1'); await once(target, 'listening');
  const origin = http.createServer((req, res) => {
    if (req.url === '/echo') return res.end(JSON.stringify(req.headers));
    res.writeHead(302, { Location: req.url === '/cross'
      ? `http://127.0.0.1:${target.address().port}/echo` : '/echo' }); res.end();
  });
  origin.listen(0, '127.0.0.1'); await once(origin, 'listening');
  try {
    for (const sensitiveHeaders of [['X-API-Key'], vm.runInNewContext("['X-API-Key']")]) {
      for (const route of ['/same', '/cross']) {
        const headers = await new Promise((resolve, reject) => {
          const req = follow.get(`http://127.0.0.1:${origin.address().port}${route}`, {
            sensitiveHeaders, headers: { 'X-API-Key': 'synthetic-secret', 'X-Harmless': 'preserved' },
          }, res => { let body = ''; res.on('data', chunk => { body += chunk; });
            res.on('end', () => { try { resolve(JSON.parse(body)); } catch (error) { reject(error); } });
            res.on('error', reject);
          });
          req.on('error', reject); req.setTimeout(5000, () => req.destroy(new Error('redirect test timeout')));
        });
        assert.equal(headers['x-api-key'], route === '/same' ? 'synthetic-secret' : undefined);
        assert.equal(headers['x-harmless'], 'preserved');
      }
    }
  } finally {
    await Promise.all([origin, target].map(server => new Promise(resolve => server.close(resolve))));
  }
});
