/**
 * Expo Config Plugin — withIntentsExtension
 *
 * Adds AppIntents (iOS 16+) Swift files to the main app target
 * for Siri Shortcuts integration. No extension target needed —
 * AppShortcutsProvider is discovered automatically from the main app.
 *
 * Usage in app.json:
 *   "plugins": ["./plugins/withIntentsExtension"]
 */
const { withXcodeProject, withEntitlementsPlist, withInfoPlist } = require('@expo/config-plugins');
const path = require('path');
const fs = require('fs');

const APP_GROUP = 'group.life.executor.health';

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

  // 3. Add Swift source files to main app target
  config = withXcodeProject(config, (mod) => {
    const proj = mod.modRequest.projectRoot;
    const xcodeProject = mod.modResults;

    // Write Swift files into ios/HealthPilot/SiriIntents/
    const siriPath = path.join(proj, 'ios', 'HealthPilot', 'SiriIntents');
    if (!fs.existsSync(siriPath)) {
      fs.mkdirSync(siriPath, { recursive: true });
    }

    const files = {
      'SharedKeychain.swift': SHARED_KEYCHAIN_SWIFT,
      'HealthCommandIntent.swift': HEALTH_COMMAND_INTENT_SWIFT,
      'HealthPilotShortcuts.swift': HEALTH_PILOT_SHORTCUTS_SWIFT,
    };

    for (const [name, content] of Object.entries(files)) {
      const filePath = path.join(siriPath, name);
      // Always overwrite to pick up code changes
      fs.writeFileSync(filePath, content, 'utf-8');
    }

    // Add files to the main app target's Sources build phase
    const mainTargetName = 'HealthPilot';
    // Find the main target
    const targets = xcodeProject.pbxNativeTargetSection();
    let mainTargetUuid = null;
    for (const [uuid, target] of Object.entries(targets)) {
      if (target.name === mainTargetName && !uuid.endsWith('_comment')) {
        mainTargetUuid = uuid;
        break;
      }
    }

    // Add a PBX group for our Siri files
    const siriGroup = xcodeProject.addPbxGroup(
      Object.keys(files),
      'SiriIntents',
      'HealthPilot/SiriIntents',
    );

    // Add to main group
    const mainGroup = xcodeProject.getFirstProject().firstProject.mainGroup;
    xcodeProject.addToPbxGroup(siriGroup.uuid, mainGroup);

    // Add each Swift file to the main target's Sources build phase
    if (mainTargetUuid) {
      for (const name of Object.keys(files)) {
        xcodeProject.addSourceFile(
          name,
          { target: mainTargetUuid },
          siriGroup.uuid,
        );
      }
    }

    return mod;
  });

  return config;
}

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

struct HealthCommandIntent: AppIntent {
    static let title: LocalizedStringResource = "记录健康数据"
    static let description = IntentDescription("通过 Siri 语音快速记录饮食、饮水、运动等健康数据")
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
                           let c = json["content"] as? String {
                            lastContent += c
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
                "用\\(.applicationName)记录健康数据",
                "\\(.applicationName)记一下",
                "告诉\\(.applicationName)",
            ],
            shortTitle: "记录健康数据",
            systemImageName: "heart.text.square"
        )
    }
}
`;

module.exports = withIntentsExtension;
