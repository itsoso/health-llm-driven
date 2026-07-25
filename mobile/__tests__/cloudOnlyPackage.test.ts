import fs from 'fs';
import path from 'path';

const mobileRoot = path.resolve(__dirname, '..');

function walk(root: string): string[] {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(root, entry.name);
    return entry.isDirectory() ? walk(absolute) : [absolute];
  });
}

describe('cloud-only mobile package', () => {
  it('does not ship an embedded inference model', () => {
    const forbiddenExtensions = new Set([
      '.bin',
      '.gguf',
      '.mlmodel',
      '.mlmodelc',
      '.mlpackage',
      '.onnx',
      '.pte',
      '.tflite',
    ]);
    const packagedModelFiles = walk(path.join(mobileRoot, 'modules')).filter((file) => {
      const segments = file.split(path.sep);
      return segments.some((segment) => forbiddenExtensions.has(path.extname(segment)));
    });

    expect(packagedModelFiles).toEqual([]);
  });

  it('does not expose retired local or offline modes', () => {
    const sourceFiles = [
      path.join(mobileRoot, 'app', '_layout.tsx'),
      path.join(mobileRoot, 'app', 'login.tsx'),
      path.join(mobileRoot, 'app', 'settings.tsx'),
    ];
    const source = sourceFiles.map((file) => fs.readFileSync(file, 'utf8')).join('\n');

    expect(source).not.toMatch(/LocalMode|NetworkBanner|app-mode|无需注册，立即本地使用/);
  });
});
