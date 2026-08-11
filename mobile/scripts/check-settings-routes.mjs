import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const mobileRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const settingsPath = join(mobileRoot, 'app', 'settings.tsx');
const source = readFileSync(settingsPath, 'utf8');
const routes = [...source.matchAll(/router\.push\('([^']+)'/g)].map(match => match[1]);

if (routes.length === 0) {
  console.error('No settings routes found; update the route checker if navigation syntax changed.');
  process.exit(1);
}

const missing = [...new Set(routes)].filter(route => {
  const relative = route.replace(/^\//, '');
  return ![
    join(mobileRoot, 'app', `${relative}.tsx`),
    join(mobileRoot, 'app', relative, 'index.tsx'),
    join(mobileRoot, 'app', '(tabs)', `${relative}.tsx`),
    join(mobileRoot, 'app', '(tabs)', relative, 'index.tsx'),
  ].some(existsSync);
});

if (missing.length > 0) {
  console.error(`Settings routes without a screen: ${missing.join(', ')}`);
  process.exit(1);
}

console.log(`Verified ${new Set(routes).size} settings routes.`);
