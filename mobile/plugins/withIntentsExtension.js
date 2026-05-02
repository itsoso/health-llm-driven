/**
 * Expo Config Plugin — withIntentsExtension
 *
 * Adds AppIntents (iOS 16+) Swift files to the main app target
 * for Siri Shortcuts integration. No extension target needed —
 * AppShortcutsProvider is discovered automatically from the main app.
 *
 * 三个 AppIntent：
 *   1. HealthCommandIntent        —— 语音记录健康数据（走 OpenClaw /agent/stream）
 *   2. HealthAnalysisIntent       —— 语音发起多专家综合分析，Siri 直接播报结论（不开 App）
 *   3. HealthAnalysisOpenIntent   —— 打开 App 到 AI Chat 并自动触发分析（通过 mobile:// scheme）
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
      'HealthAnalysisIntent.swift': HEALTH_ANALYSIS_INTENT_SWIFT,
      'HealthAnalysisOpenIntent.swift': HEALTH_ANALYSIS_OPEN_INTENT_SWIFT,
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

    // Add a PBX group for our Siri files (empty initially —
    // addSourceFile below will register each file into the group *and*
    // into the Sources build phase in one shot).
    const siriGroup = xcodeProject.addPbxGroup(
      [],
      'SiriIntents',
      'HealthPilot/SiriIntents',
    );

    // Add to main group
    const mainGroup = xcodeProject.getFirstProject().firstProject.mainGroup;
    xcodeProject.addToPbxGroup(siriGroup.uuid, mainGroup);

    // Add each Swift file to the main target's Sources build phase.
    // IMPORTANT: group must be empty above, otherwise xcode.addFile
    // short-circuits (returns false) and the PBXBuildFile /
    // PBXSourcesBuildPhase entries are never written — which is
    // exactly what silently broke build #27 (AppShortcutsProvider
    // never shipped).
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
    static let description = IntentDescription("语音快速记录饮食、饮水、运动等健康数据")
    static let openAppWhenRun = false

    @Parameter(title: "内容")
    var content: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let token = SharedKeychain.loadToken(), !token.isEmpty else {
            return .result(dialog: "请先打开健康助理 App 登录")
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
                return .result(dialog: "登录已过期，请打开健康助理 重新登录")
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

// ---------- A 方案：纯语音多专家分析（不开 App） ----------
// 调 /api/v1/orchestrator/chat/stream，聚合 SSE 中 event:chunk 的文本作为结论播报
const HEALTH_ANALYSIS_INTENT_SWIFT = `import AppIntents
import Foundation

struct HealthAnalysisIntent: AppIntent {
    static let title: LocalizedStringResource = "健康综合分析"
    static let description = IntentDescription("不打开 App，直接语音发起多专家综合分析并播报结论")
    static let openAppWhenRun = false

    @Parameter(title: "问题", description: "要分析什么？如: 我最近的睡眠怎么样")
    var query: String

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let token = SharedKeychain.loadToken(), !token.isEmpty else {
            return .result(dialog: "请先打开健康助理 App 登录")
        }

        guard let url = URL(string: "https://health-api.executor.life/api/v1/orchestrator/chat/stream") else {
            return .result(dialog: "服务地址配置错误")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 60  // 多专家合成可能较慢

        let body: [String: Any] = ["query": query, "stream": true, "source": "siri"]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return .result(dialog: "网络请求失败")
            }
            if httpResponse.statusCode == 401 {
                return .result(dialog: "登录已过期，请打开健康助理 重新登录")
            }
            if httpResponse.statusCode >= 400 {
                return .result(dialog: "分析服务暂时不可用，请稍后再试")
            }

            guard let text = String(data: data, encoding: .utf8), !text.isEmpty else {
                return .result(dialog: "分析结果为空，请稍后再试")
            }

            // 解析 SSE：只收集 event:chunk 的 data 字段（LLM 合成文本）
            var synthesis = ""
            var currentEvent: String? = nil
            for rawLine in text.components(separatedBy: "\\n") {
                let line = rawLine.trimmingCharacters(in: .whitespaces)
                if line.isEmpty {
                    currentEvent = nil
                    continue
                }
                if line.hasPrefix("event: ") {
                    currentEvent = String(line.dropFirst(7)).trimmingCharacters(in: .whitespaces)
                } else if line.hasPrefix("data: ") {
                    let payload = String(line.dropFirst(6))
                    // chunk 事件的 data 是 JSON-encoded 字符串，decode 即可
                    if currentEvent == "chunk" {
                        if let d = payload.data(using: .utf8),
                           let s = try? JSONSerialization.jsonObject(with: d, options: [.fragmentsAllowed]) as? String {
                            synthesis += s
                        } else {
                            synthesis += payload
                        }
                    }
                }
            }

            let trimmed = synthesis.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                return .result(dialog: "暂无分析结论，请稍后再试")
            }
            // 语音播报上限约 600 字；取前 300 字足够一段简短结论
            let display = trimmed.count > 300 ? String(trimmed.prefix(300)) + "…" : trimmed
            return .result(dialog: "\\(display)")
        } catch {
            return .result(dialog: "网络错误，请检查网络连接")
        }
    }
}
`;

// ---------- B 方案：打开 App 并自动触发分析 ----------
// openAppWhenRun=true → 系统打开 App；perform() 里 open(mobile://chat?...) 把 query 带进去
const HEALTH_ANALYSIS_OPEN_INTENT_SWIFT = `import AppIntents
import Foundation
import UIKit

struct HealthAnalysisOpenIntent: AppIntent {
    static let title: LocalizedStringResource = "打开健康助理 并分析"
    static let description = IntentDescription("打开 App 进入 AI 健康助理，自动把问题发送给多专家分析")
    static let openAppWhenRun = true

    @Parameter(title: "问题", description: "要分析什么？如: 我最近的睡眠怎么样")
    var query: String

    @MainActor
    func perform() async throws -> some IntentResult {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        if let url = URL(string: "mobile://chat?prompt=\\(encoded)&autoSend=1") {
            await UIApplication.shared.open(url)
        }
        return .result()
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
        AppShortcut(
            intent: HealthAnalysisIntent(),
            phrases: [
                "用\\(.applicationName)分析",
                "\\(.applicationName)综合分析",
                "让\\(.applicationName)分析一下",
                "问\\(.applicationName)",
            ],
            shortTitle: "综合分析",
            systemImageName: "sparkles"
        )
        AppShortcut(
            intent: HealthAnalysisOpenIntent(),
            phrases: [
                "打开\\(.applicationName)分析",
                "用\\(.applicationName)打开分析",
                "\\(.applicationName)打开并分析",
            ],
            shortTitle: "打开并分析",
            systemImageName: "arrow.up.forward.app"
        )
    }
}
`;

module.exports = withIntentsExtension;
