// Expo config-plugin:把 RevaWatch watchOS App + complication + iPhone WC bridge 注入 ios/。
// 策略:prebuild 生成 ios/ 后,用 withDangerousMod 拷源(单一真相源 = apps/watch)+ 跑已验证的
// ruby xcodeproj 注入脚本(比 JS xcode lib 可靠地建 watch target)。bridge 激活用 withAppDelegate。
// 这样 EAS prebuild(--clean)每次自动重建 watch target,survive 清理。
const { withDangerousMod, withAppDelegate } = require('@expo/config-plugins');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PHOTO_LIBRARY_USAGE_DESCRIPTION =
  '用于你主动选择餐盘、补剂标签、检查报告或健康相关图片，生成记录草稿和健康分析';
const PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION = '用于你主动保存健康报告、截图或导出图片到照片图库';
const APP_GROUP = 'group.life.executor.health';

const WATCH_INFO_PLIST = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>$(DEVELOPMENT_LANGUAGE)</string>
  <key>CFBundleExecutable</key><string>$(EXECUTABLE_NAME)</string>
  <key>CFBundleIconFiles</key>
  <array>
    <string>AppIcon-24x24@2x</string>
    <string>AppIcon-27.5x27.5@2x</string>
    <string>AppIcon-29x29@2x</string>
    <string>AppIcon-29x29@3x</string>
    <string>AppIcon-40x40@2x</string>
    <string>AppIcon-44x44@2x</string>
    <string>AppIcon-50x50@2x</string>
    <string>AppIcon-86x86@2x</string>
    <string>AppIcon-98x98@2x</string>
    <string>AppIcon-108x108@2x</string>
  </array>
  <key>CFBundleIconName</key><string>AppIcon</string>
  <key>CFBundleIdentifier</key><string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
  <key>CFBundleDisplayName</key><string>小巴健康</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>小巴健康</string>
  <key>CFBundlePackageType</key><string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
  <key>CFBundleShortVersionString</key><string>$(MARKETING_VERSION)</string>
  <key>CFBundleVersion</key><string>$(CURRENT_PROJECT_VERSION)</string>
  <key>NSPhotoLibraryUsageDescription</key><string>${PHOTO_LIBRARY_USAGE_DESCRIPTION}</string>
  <key>NSPhotoLibraryAddUsageDescription</key><string>${PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION}</string>
  <key>WKApplication</key><true/>
  <key>WKCompanionAppBundleIdentifier</key><string>life.executor.health</string>
</dict>
</plist>
`;

const WIDGET_INFO_PLIST = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>$(DEVELOPMENT_LANGUAGE)</string>
  <key>CFBundleDisplayName</key><string>小巴健康</string>
  <key>CFBundleExecutable</key><string>$(EXECUTABLE_NAME)</string>
  <key>CFBundleIdentifier</key><string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>小巴健康</string>
  <key>CFBundlePackageType</key><string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
  <key>CFBundleShortVersionString</key><string>$(MARKETING_VERSION)</string>
  <key>CFBundleVersion</key><string>$(CURRENT_PROJECT_VERSION)</string>
  <key>NSPhotoLibraryUsageDescription</key><string>${PHOTO_LIBRARY_USAGE_DESCRIPTION}</string>
  <key>NSPhotoLibraryAddUsageDescription</key><string>${PHOTO_LIBRARY_ADD_USAGE_DESCRIPTION}</string>
  <key>NSExtension</key>
  <dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.widgetkit-extension</string>
  </dict>
</dict>
</plist>
`;

function entitlementsPlist() {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.application-groups</key>
  <array>
    <string>${APP_GROUP}</string>
  </array>
</dict>
</plist>
`;
}

function copySwift(srcDir, destDir, files) {
  fs.mkdirSync(destDir, { recursive: true });
  for (const f of files) {
    const src = path.join(srcDir, f);
    if (fs.existsSync(src)) fs.copyFileSync(src, path.join(destDir, path.basename(f)));
  }
}

function copyDirectory(srcDir, destDir) {
  if (!fs.existsSync(srcDir)) return;
  fs.rmSync(destDir, { recursive: true, force: true });
  fs.cpSync(srcDir, destDir, { recursive: true });
}

function buildWatchInjectionEnv(exp, baseEnv = process.env) {
  const version =
    exp?.version ||
    exp?.modRequest?.exp?.version ||
    exp?.modRequest?.config?.version ||
    '1.0';

  return {
    ...baseEnv,
    LANG: 'en_US.UTF-8',
    LC_ALL: 'en_US.UTF-8',
    REVA_MARKETING_VERSION: version,
  };
}

function resolveGeneratedXcodeprojPath(iosRoot, modRequest = {}) {
  const projectName = modRequest.projectName;
  if (projectName) {
    const projectPath = path.join(iosRoot, `${projectName}.xcodeproj`);
    if (fs.existsSync(projectPath)) return projectPath;
  }

  const projects = fs.readdirSync(iosRoot)
    .filter((entry) => entry.endsWith('.xcodeproj'))
    .map((entry) => path.join(iosRoot, entry))
    .filter((entry) => fs.statSync(entry).isDirectory())
    .sort();

  const legacy = projects.find((entry) => path.basename(entry) === 'HealthPilot.xcodeproj');
  if (legacy) return legacy;
  if (projects.length === 1) return projects[0];
  if (projects.length > 1) {
    throw new Error(`withWatchApp found multiple xcodeproj files: ${projects.join(', ')}`);
  }

  throw new Error(`withWatchApp could not find generated xcodeproj under ${iosRoot}`);
}

function getIosBundleIdentifier(cfg) {
  return cfg.ios?.bundleIdentifier
    || cfg.modRequest?.exp?.ios?.bundleIdentifier
    || cfg.modRequest?.config?.ios?.bundleIdentifier
    || 'life.executor.health';
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
      copyDirectory(path.join(watchRoot, 'Assets.xcassets'), path.join(iosRoot, 'RevaWatch', 'Assets.xcassets'));
      fs.writeFileSync(path.join(iosRoot, 'RevaWatch', 'Info.plist'), WATCH_INFO_PLIST, 'utf-8');
      fs.writeFileSync(path.join(iosRoot, 'RevaWatch', 'RevaWatch.entitlements'), entitlementsPlist(), 'utf-8');

      // 2) complication widget 源 = RevaComplication + ComplicationState + WatchSummary + shared cache + Info.plist
      const compDir = path.join(iosRoot, 'RevaComplication');
      copySwift(path.join(watchRoot, 'WatchComplication'), compDir, ['RevaComplication.swift']);
      copySwift(core, compDir, ['ComplicationState.swift', 'WatchSummary.swift', 'ComplicationCache.swift']);
      fs.writeFileSync(path.join(compDir, 'Info.plist'), WIDGET_INFO_PLIST, 'utf-8');
      fs.writeFileSync(path.join(compDir, 'RevaComplication.entitlements'), entitlementsPlist(), 'utf-8');

      // 3) 跑已验证的 ruby 注入(建 target + 嵌入 + 加 bridge 进主 target)。EAS 构建机有 xcodeproj gem。
      const script = path.join(watchRoot, 'scripts', 'inject_watch_target.rb');
      const proj = resolveGeneratedXcodeprojPath(iosRoot, cfg.modRequest);
      const mainProjectName = path.basename(proj, '.xcodeproj');
      execSync(`ruby "${script}" "${proj}"`, {
        stdio: 'inherit',
        env: buildWatchInjectionEnv(cfg, {
          ...process.env,
          REVA_MAIN_TARGET_NAME: mainProjectName,
          REVA_MAIN_GROUP_PATH: mainProjectName,
          REVA_IOS_INFOPLIST_FILE: `${mainProjectName}/Info.plist`,
          REVA_IOS_BUNDLE_ID: getIosBundleIdentifier(cfg),
        }),
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
module.exports.buildWatchInjectionEnv = buildWatchInjectionEnv;
module.exports._resolveGeneratedXcodeprojPath = resolveGeneratedXcodeprojPath;
