const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const platform = process.env.EAS_BUILD_PLATFORM;
if (platform && platform !== 'ios') {
  console.log(`[watch] skip post-install hook for platform=${platform}`);
  process.exit(0);
}

const mobileRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(mobileRoot, '..');
const project = path.join(mobileRoot, 'ios', 'HealthPilot.xcodeproj');
const script = path.join(repoRoot, 'apps', 'watch', 'scripts', 'inject_watch_target.rb');

if (!fs.existsSync(project)) {
  console.log(`[watch] skip: ${project} does not exist`);
  process.exit(0);
}
if (!fs.existsSync(script)) {
  console.log(`[watch] skip: ${script} does not exist`);
  process.exit(0);
}

execFileSync('ruby', [script, project], {
  stdio: 'inherit',
  env: {
    ...process.env,
    LANG: process.env.LANG || 'en_US.UTF-8',
    LC_ALL: process.env.LC_ALL || 'en_US.UTF-8',
  },
});
