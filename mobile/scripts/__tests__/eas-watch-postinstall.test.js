const path = require('path');
const { spawnSync } = require('child_process');

describe('eas-watch-postinstall', () => {
  it('does not inject Watch targets into the standard production build', () => {
    const script = path.resolve(__dirname, '..', 'eas-watch-postinstall.js');
    const env = { ...process.env, EAS_BUILD_PLATFORM: 'ios' };
    delete env.INCLUDE_WATCH_APP;

    const result = spawnSync(process.execPath, [script], {
      env,
      encoding: 'utf8',
    });

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('[watch] skip: INCLUDE_WATCH_APP is not enabled');
  });
});
