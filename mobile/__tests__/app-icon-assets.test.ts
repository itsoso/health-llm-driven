const fs = require('fs');
const path = require('path');
const appJson = require('../app.json');

const MOBILE_ROOT = path.resolve(__dirname, '..');

function assetPath(configPath: string): string {
  return path.resolve(MOBILE_ROOT, configPath);
}

function readPng(configPath: string) {
  const buffer = fs.readFileSync(assetPath(configPath));
  const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  expect(buffer.subarray(0, 8)).toEqual(pngSignature);

  return {
    buffer,
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
    colorType: buffer.readUInt8(25),
  };
}

describe('app icon assets', () => {
  it('keeps the approved light icon palette wired to every launcher surface', () => {
    const expo = appJson.expo;

    expect(expo.icon).toBe('./assets/images/icon.png');
    expect(expo.android.adaptiveIcon.foregroundImage).toBe('./assets/images/adaptive-icon.png');
    expect(expo.splash.image).toBe('./assets/images/splash-icon.png');
    expect(expo.splash.backgroundColor).toBe('#DDEFE8');
  });

  it('keeps canonical and adaptive launcher art byte-identical at 1024 px', () => {
    const icon = readPng(appJson.expo.icon);
    const adaptive = readPng(appJson.expo.android.adaptiveIcon.foregroundImage);

    expect([icon.width, icon.height]).toEqual([1024, 1024]);
    expect([adaptive.width, adaptive.height]).toEqual([1024, 1024]);
    expect(adaptive.buffer).toEqual(icon.buffer);
  });

  it('keeps splash artwork at 512 px', () => {
    const splash = readPng(appJson.expo.splash.image);

    expect([splash.width, splash.height]).toEqual([512, 512]);
  });

  it('keeps every App Store icon asset fully opaque', () => {
    const icon = readPng(appJson.expo.icon);
    const adaptive = readPng(appJson.expo.android.adaptiveIcon.foregroundImage);
    const splash = readPng(appJson.expo.splash.image);

    expect(icon.colorType).toBe(2);
    expect(adaptive.colorType).toBe(2);
    expect(splash.colorType).toBe(2);
  });
});
