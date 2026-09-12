import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const script = new URL('../install.sh', import.meta.url).pathname;

test('installer is valid Bash', () => {
  const result = spawnSync('/bin/bash', ['-n', script], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
});

for (const scenario of ['missing-node', 'old-node', 'missing-npm']) {
  test(`installer rejects ${scenario} before dependency mutation`, () => {
    const directory = mkdtempSync(join(tmpdir(), 'reva-pi-install-'));
    const marker = join(directory, 'npm-called');
    try {
      if (scenario !== 'missing-node') writeFileSync(join(directory, 'node'), '#!/bin/bash\nexit 1\n', { mode: 0o755 });
      if (scenario !== 'missing-npm') writeFileSync(join(directory, 'npm'), `#!/bin/bash\n: > '${marker}'\nexit 0\n`, { mode: 0o755 });
      const result = spawnSync('/bin/bash', [script], { encoding: 'utf8', env: { PATH: directory } });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /Pi runtime requires/);
      assert.equal(existsSync(marker), false);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
}
