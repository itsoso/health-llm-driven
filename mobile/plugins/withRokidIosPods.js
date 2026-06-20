const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const ROKID_PODFILE_HOOK_MARKER = '# Reva Rokid iOS SDK dynamic framework fix';
const ROKID_TARGET_POD_MARKER = '# Reva Rokid iOS SDK RGCxrClient local pod';
const ROKID_TARGET_POD_LINE = "pod 'RGCxrClient', :path => '../modules/rokid-bridge/ios/vendor'";

const ROKID_PODFILE_HOOK = `${ROKID_PODFILE_HOOK_MARKER}
def reva_rokid_ios_sdk_enabled?
  ['1', 'true', 'yes'].include?(
    (ENV['ROKID_IOS_SDK_ENABLED'] || ENV['ROKID_SDK_ENABLED']).to_s.downcase
  )
end

pre_install do |installer|
  next unless reva_rokid_ios_sdk_enabled?

  reva_rokid_dynamic_framework_pods = ['RGCoreKit', 'CocoaLumberjack']
  installer.pod_targets.each do |pod|
    next unless reva_rokid_dynamic_framework_pods.include?(pod.name)

    def pod.build_type
      Pod::BuildType.dynamic_framework
    end
  end
end
`;

// 把刷新后的 RGCxrClient 作为一等本地 pod 注入 target 内部。必须放在 target 块里
// (pod 声明只在 target 内合法)。RokidBridge.podspec 之前用 s.vendored_frameworks
// 接它, 但在 Expo static_framework 里 vendored_frameworks 不传播 -F 搜索路径 →
// canImport(RGCxrClient)=false → SDK 静默缺席(EAS build f0878b7b 实测)。作为一等
// pod 才能像官方 sample 那样正确接 module / 搜索路径 / 链接。
const ROKID_TARGET_POD = `  ${ROKID_TARGET_POD_MARKER}
  if reva_rokid_ios_sdk_enabled?
    ${ROKID_TARGET_POD_LINE}
  end
`;

function patchPodfileContents(contents) {
  const targetAnchor = "target 'HealthPilot' do";
  if (!contents.includes(targetAnchor)) {
    throw new Error('withRokidIosPods could not find the HealthPilot Podfile target');
  }

  let patched = contents;
  if (!patched.includes(ROKID_PODFILE_HOOK_MARKER)) {
    patched = patched.replace(targetAnchor, `${ROKID_PODFILE_HOOK}\n${targetAnchor}`);
  }
  if (!patched.includes(ROKID_TARGET_POD_LINE)) {
    patched = patched.replace(targetAnchor, `${targetAnchor}\n${ROKID_TARGET_POD}`);
  }
  return patched;
}

function withRokidIosPods(config) {
  return withDangerousMod(config, [
    'ios',
    (cfg) => {
      const podfilePath = path.join(cfg.modRequest.platformProjectRoot, 'Podfile');
      const contents = fs.readFileSync(podfilePath, 'utf8');
      const patched = patchPodfileContents(contents);
      if (patched !== contents) {
        fs.writeFileSync(podfilePath, patched, 'utf8');
      }
      return cfg;
    },
  ]);
}

module.exports = withRokidIosPods;
module.exports._patchPodfileContents = patchPodfileContents;
