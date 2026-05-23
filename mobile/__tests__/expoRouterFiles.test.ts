import fs from 'fs';
import path from 'path';

function listFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name);
    return entry.isDirectory() ? listFiles(fullPath) : [fullPath];
  });
}

describe('Expo Router app directory', () => {
  it('keeps helper modules out of route discovery', () => {
    const appDir = path.join(__dirname, '..', 'app');
    const helperModules = listFiles(appDir)
      .filter((file) => /\.(styles|helpers|utils)\.[jt]sx?$/.test(path.basename(file)))
      .map((file) => path.relative(appDir, file));

    expect(helperModules).toEqual([]);
  });
});
