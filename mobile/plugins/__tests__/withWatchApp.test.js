const fs = require('fs');
const path = require('path');

describe('withWatchApp privacy manifests', () => {
  it('keeps photo library purpose strings in generated watch plist templates', () => {
    const pluginSource = fs.readFileSync(path.join(__dirname, '..', 'withWatchApp.js'), 'utf8');

    expect(pluginSource).toContain('NSPhotoLibraryUsageDescription');
    expect(pluginSource).toContain('NSPhotoLibraryAddUsageDescription');
  });
});
