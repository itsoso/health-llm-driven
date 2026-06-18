const { withDangerousMod } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');

const ROKID_PODFILE_MARKER = '# Reva Rokid iOS SDK dynamic framework fix';

const ROKID_PODFILE_HOOK = `${ROKID_PODFILE_MARKER}
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

function patchPodfileContents(contents) {
  if (contents.includes(ROKID_PODFILE_MARKER)) {
    return contents;
  }

  const targetAnchor = "target 'HealthPilot' do";
  if (!contents.includes(targetAnchor)) {
    throw new Error('withRokidIosPods could not find the HealthPilot Podfile target');
  }

  return contents.replace(targetAnchor, `${ROKID_PODFILE_HOOK}\n${targetAnchor}`);
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
