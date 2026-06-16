// Expo config-plugin:把 RevaWatch watchOS App + complication + iPhone WC bridge 注入 ios/。
// 策略:prebuild 生成 ios/ 后,用 withDangerousMod 拷源(单一真相源 = apps/watch)+ 跑已验证的
// ruby xcodeproj 注入脚本(比 JS xcode lib 可靠地建 watch target)。bridge 激活用 withAppDelegate。
// 这样 EAS prebuild(--clean)每次自动重建 watch target,survive 清理。
const { withDangerousMod, withAppDelegate } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const WIDGET_INFO_PLIST = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSExtension</key>
  <dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.widgetkit-extension</string>
  </dict>
</dict>
</plist>
`;

function copySwift(srcDir, destDir, files) {
  fs.mkdirSync(destDir, { recursive: true });
  for (const f of files) {
    const src = path.join(srcDir, f);
    if (fs.existsSync(src)) fs.copyFileSync(src, path.join(destDir, path.basename(f)));
  }
}

function withWatchSources(config) {
  return withDangerousMod(config, [
    'ios',
    (cfg) => {
      const iosRoot = cfg.modRequest.platformProjectRoot;          // mobile/ios
      const watchRoot = path.join(cfg.modRequest.projectRoot, '..', 'apps', 'watch');
      const core = path.join(watchRoot, 'Sources', 'WatchCompanionCore');

      // 1) watch app target 源 = WatchApp/* + Core/*
      const appFiles = fs.readdirSync(path.join(watchRoot, 'WatchApp')).filter((f) => f.endsWith('.swift'));
      copySwift(path.join(watchRoot, 'WatchApp'), path.join(iosRoot, 'RevaWatch'), appFiles);
      const coreFiles = fs.readdirSync(core).filter((f) => f.endsWith('.swift'));
      copySwift(core, path.join(iosRoot, 'RevaWatch'), coreFiles);

      // 2) complication widget 源 = RevaComplication + ComplicationState + WatchSummary + Info.plist
      const compDir = path.join(iosRoot, 'RevaComplication');
      copySwift(path.join(watchRoot, 'WatchComplication'), compDir, ['RevaComplication.swift']);
      copySwift(core, compDir, ['ComplicationState.swift', 'WatchSummary.swift']);
      fs.writeFileSync(path.join(compDir, 'Info.plist'), WIDGET_INFO_PLIST, 'utf-8');

      // 3) 跑已验证的 ruby 注入(建 target + 嵌入 + 加 bridge 进主 target)。EAS 构建机有 xcodeproj gem。
      const script = path.join(watchRoot, 'scripts', 'inject_watch_target.rb');
      const proj = path.join(iosRoot, 'HealthPilot.xcodeproj');
      execSync(`ruby "${script}" "${proj}"`, {
        stdio: 'inherit',
        env: { ...process.env, LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8' },
      });
      return cfg;
    },
  ]);
}

function withBridgeActivation(config) {
  return withAppDelegate(config, (cfg) => {
    let src = cfg.modResults.contents;
    if (src.includes('WatchPhoneBridge.shared.activate()')) return cfg; // 幂等
    const anchor = 'return super.application(application, didFinishLaunchingWithOptions: launchOptions)';
    if (src.includes(anchor)) {
      src = src.replace(
        anchor,
        '#if canImport(WatchConnectivity)\n    WatchPhoneBridge.shared.activate()\n    #endif\n    ' + anchor,
      );
      cfg.modResults.contents = src;
    }
    return cfg;
  });
}

module.exports = function withWatchApp(config) {
  config = withWatchSources(config);
  config = withBridgeActivation(config);
  return config;
};
