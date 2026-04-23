/**
 * Expo Config Plugin — withIntentsExtension
 *
 * Adds the HealthPilotIntents App Extension target to the Xcode project
 * so that `expo prebuild --clean` won't lose the Siri Intents config.
 *
 * Usage in app.json:
 *   "plugins": ["./plugins/withIntentsExtension"]
 */
const { withXcodeProject, withEntitlementsPlist, withInfoPlist } = require('@expo/config-plugins');
const path = require('path');
const fs = require('fs');

const EXTENSION_NAME = 'HealthPilotIntents';
const BUNDLE_ID_SUFFIX = '.intents';
const APP_GROUP = 'group.life.executor.health';
const DEPLOYMENT_TARGET = '16.0';

function withIntentsExtension(config) {
  // 1. Add Siri entitlement + App Groups to main app
  config = withEntitlementsPlist(config, (mod) => {
    mod.modResults['com.apple.developer.siri'] = true;
    mod.modResults['com.apple.security.application-groups'] = [APP_GROUP];
    return mod;
  });

  // 2. Add NSSiriUsageDescription to main Info.plist
  config = withInfoPlist(config, (mod) => {
    if (!mod.modResults.NSSiriUsageDescription) {
      mod.modResults.NSSiriUsageDescription = '使用 Siri 语音记录健康数据';
    }
    return mod;
  });

  // 3. Add extension target to Xcode project
  config = withXcodeProject(config, (mod) => {
    const proj = mod.modRequest.projectRoot;
    const bundleId = config.ios?.bundleIdentifier ?? 'life.executor.health';
    const extBundleId = bundleId + BUNDLE_ID_SUFFIX;
    const xcodeProject = mod.modResults;

    const extPath = path.join(proj, 'ios', EXTENSION_NAME);

    // Write extension source files if they don't exist
    if (!fs.existsSync(extPath)) {
      fs.mkdirSync(extPath, { recursive: true });
    }

    writeIfMissing(path.join(extPath, 'Info.plist'), EXTENSION_INFO_PLIST);
    writeIfMissing(
      path.join(extPath, `${EXTENSION_NAME}.entitlements`),
      EXTENSION_ENTITLEMENTS,
    );

    // Write shared Swift files
    const sharedPath = path.join(proj, 'ios', 'Shared');
    if (!fs.existsSync(sharedPath)) {
      fs.mkdirSync(sharedPath, { recursive: true });
    }
    writeIfMissing(path.join(sharedPath, 'SharedKeychain.swift'), SHARED_KEYCHAIN_SWIFT);
    writeIfMissing(path.join(extPath, 'HealthCommandIntent.swift'), HEALTH_COMMAND_INTENT_SWIFT);
    writeIfMissing(path.join(extPath, 'HealthPilotShortcuts.swift'), HEALTH_PILOT_SHORTCUTS_SWIFT);

    // Add the extension target to the Xcode project
    const targetUuid = xcodeProject.generateUuid();
    const extGroup = xcodeProject.addPbxGroup(
      ['Info.plist', `${EXTENSION_NAME}.entitlements`, 'HealthCommandIntent.swift', 'HealthPilotShortcuts.swift'],
      EXTENSION_NAME,
      EXTENSION_NAME,
    );

    const target = xcodeProject.addTarget(
      EXTENSION_NAME,
      'app_extension',
      EXTENSION_NAME,
      extBundleId,
    );

    if (target) {
      // Add build settings to extension target
      xcodeProject.addBuildProperty('IPHONEOS_DEPLOYMENT_TARGET', DEPLOYMENT_TARGET, EXTENSION_NAME);
      xcodeProject.addBuildProperty('SWIFT_VERSION', '5.0', EXTENSION_NAME);
      xcodeProject.addBuildProperty('CODE_SIGN_ENTITLEMENTS', `${EXTENSION_NAME}/${EXTENSION_NAME}.entitlements`, EXTENSION_NAME);
      xcodeProject.addBuildProperty('INFOPLIST_FILE', `${EXTENSION_NAME}/Info.plist`, EXTENSION_NAME);
      xcodeProject.addBuildProperty('GENERATE_INFOPLIST_FILE', 'YES', EXTENSION_NAME);

      // Add source files to extension target build phase
      const sourceFiles = [
        'HealthCommandIntent.swift',
        'HealthPilotShortcuts.swift',
        '../Shared/SharedKeychain.swift',
      ];
      for (const file of sourceFiles) {
        xcodeProject.addSourceFile(
          path.join(EXTENSION_NAME, file),
          { target: target.uuid },
          extGroup.uuid,
        );
      }
    }

    return mod;
  });

  return config;
}

function writeIfMissing(filePath, content) {
  if (!fs.existsSync(filePath)) {
    fs.writeFileSync(filePath, content, 'utf-8');
  }
}

const EXTENSION_INFO_PLIST = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSExtension</key>
  <dict>
    <key>NSExtensionPointIdentifier</key>
    <string>com.apple.intents-service</string>
    <key>NSExtensionPrincipalClass</key>
    <string>$(PRODUCT_MODULE_NAME).HealthCommandIntent</string>
  </dict>
</dict>
</plist>
`;

const EXTENSION_ENTITLEMENTS = `<?xml version="1.0" encoding="UTF-8"?>
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

const SHARED_KEYCHAIN_SWIFT = `import Foundation
import Security

struct SharedKeychain {
    static let service = "life.executor.health.shared"
    static let appGroup = "${APP_GROUP}"
    static let tokenKey = "siri_auth_token"

    static func loadToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenKey,
            kSecAttrAccessGroup as String: appGroup,
            kSecReturnData as String: true,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }
}
`;

const HEALTH_COMMAND_INTENT_SWIFT = `import AppIntents
import Foundation

struct QuickRecordResponse: Decodable {
    let summary: String?
    let message: String?
}

struct HealthCommandIntent: AppIntent {
    static let title: LocalizedStringResource = "记录健康数据"
    static let description = IntentDescription("使用 Siri 语音记录健康数据，如"喝了500ml水"、"吃了一个苹果"")
    static let openAppWhenRun = false

    @Parameter(title: "内容")
    var content: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let token = SharedKeychain.loadToken(), !token.isEmpty else {
            return .result(dialog: "请先打开 HealthPilot App 登录")
        }

        guard let url = URL(string: "https://health-api.executor.life/api/v1/agent/stream") else {
            return .result(dialog: "服务地址配置错误")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let body: [String: Any] = ["message": content, "stream": false]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return .result(dialog: "网络请求失败")
            }
            if httpResponse.statusCode == 401 {
                return .result(dialog: "登录已过期，请打开 HealthPilot 重新登录")
            }
            if httpResponse.statusCode >= 400 {
                return .result(dialog: "服务暂时不可用，请稍后再试")
            }
            if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                let lines = text.components(separatedBy: "\\n")
                var lastContent = ""
                for line in lines {
                    if line.hasPrefix("data: ") {
                        let jsonStr = String(line.dropFirst(6))
                        if let jsonData = jsonStr.data(using: .utf8),
                           let json = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any],
                           let content = json["content"] as? String {
                            lastContent += content
                        }
                    }
                }
                let trimmed = lastContent.trimmingCharacters(in: .whitespacesAndNewlines)
                let display = trimmed.isEmpty ? "已记录" : (trimmed.count > 200 ? String(trimmed.prefix(200)) + "..." : trimmed)
                return .result(dialog: "\\(display)")
            }
            return .result(dialog: "已记录：\\(content)")
        } catch {
            return .result(dialog: "网络错误，请检查网络连接")
        }
    }
}
`;

const HEALTH_PILOT_SHORTCUTS_SWIFT = `import AppIntents

struct HealthPilotShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: HealthCommandIntent(),
            phrases: [
                "用\\(.applicationName)记录\\(\\$content)",
                "\\(.applicationName)记一下\\(\\$content)",
                "告诉\\(.applicationName)\\(\\$content)",
            ],
            shortTitle: "记录健康数据",
            systemImageName: "heart.text.square"
        )
    }
}
`;

module.exports = withIntentsExtension;
