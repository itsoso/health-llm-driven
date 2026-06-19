const { _patchPodfileContents } = require('../withRokidIosPods');

const BASE_PODFILE = `require File.join(File.dirname(\`node --print "require.resolve('expo/package.json')"\`), "scripts/autolinking")

platform :ios, podfile_properties['ios.deploymentTarget'] || '15.1'

target 'HealthPilot' do
  use_expo_modules!
  pod 'SomethingElse'
end
`;

describe('withRokidIosPods Podfile patch', () => {
  it('injects the RGCxrClient local pod INSIDE the HealthPilot target, gated on rokid env', () => {
    const patched = _patchPodfileContents(BASE_PODFILE);

    // 一等本地 pod, :path 指向仓库内刷新框架目录
    expect(patched).toContain("pod 'RGCxrClient', :path => '../modules/rokid-bridge/ios/vendor'");
    // 必须门控, 普通 production build 不应拉这个 pod
    expect(patched).toContain('if reva_rokid_ios_sdk_enabled?');
    // 仍保留 RGCoreKit dynamic_framework 修复
    expect(patched).toContain('reva_rokid_dynamic_framework_pods');

    // pod 行必须落在 target 块内部(在 target 行之后)
    const targetIdx = patched.indexOf("target 'HealthPilot' do");
    const podIdx = patched.indexOf("pod 'RGCxrClient'");
    expect(targetIdx).toBeGreaterThan(-1);
    expect(podIdx).toBeGreaterThan(targetIdx);
  });

  it('is idempotent — patching twice does not duplicate the injection', () => {
    const once = _patchPodfileContents(BASE_PODFILE);
    const twice = _patchPodfileContents(once);
    expect(twice).toBe(once);
    const occurrences = twice.split("pod 'RGCxrClient'").length - 1;
    expect(occurrences).toBe(1);
  });

  it('throws if the HealthPilot target anchor is missing', () => {
    expect(() => _patchPodfileContents('platform :ios\n')).toThrow(/HealthPilot Podfile target/);
  });
});
