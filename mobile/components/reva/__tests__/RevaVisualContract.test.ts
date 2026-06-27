import fs from 'fs';
import path from 'path';

describe('Reva visual contract', () => {
  it('does not use negative letter spacing in Reva surfaces', () => {
    const revaRoot = path.resolve(__dirname, '..');
    const offenders = listSourceFiles(revaRoot).flatMap((file) => {
      const rel = path.relative(revaRoot, file);
      return fs
        .readFileSync(file, 'utf8')
        .split('\n')
        .flatMap((line, index) =>
          /letterSpacing:\s*-\d/.test(line) ? [`${rel}:${index + 1}:${line.trim()}`] : [],
        );
    });

    expect(offenders).toEqual([]);
  });
});

function listSourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return listSourceFiles(full);
    return /\.(tsx?|jsx?)$/.test(entry.name) ? [full] : [];
  });
}
