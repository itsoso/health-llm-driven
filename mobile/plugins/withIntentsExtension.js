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
  // 1. Add Siri entitlement + App Groups + Keychain Sharing to main app
  //
  // ⚠️ keychain-access-groups 和 application-groups 是两个独立 entitlement。
  // 即便 value 用同一个 ID, 两个都得声明, 否则 SecItemAdd 会静默返回
  // errSecMissingEntitlement —— Siri extension 读不到 token, 报"请先登录"。
  //
  // value 必须带 $(AppIdentifierPrefix) 前缀: EAS 管理的 provisioning profile
  // 里的 keychain-access-groups 值是 "<TeamID>.group.life.executor.health",
  // fastlane 做字面对比, 短名会报 "doesn't match" 导致 build 失败。
  // Xcode 构建时展开 $(AppIdentifierPrefix) 为 Team ID 前缀。
  config = withEntitlementsPlist(config, (mod) => {
    mod.modResults['com.apple.developer.siri'] = true;
    mod.modResults['com.apple.security.application-groups'] = [APP_GROUP];
    mod.modResults['keychain-access-groups'] = [
      `$(AppIdentifierPrefix)${APP_GROUP}`,
    ];
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
      'FreeTextEntity.swift': FREE_TEXT_ENTITY_SWIFT,
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
    static let markerKey = "siri_debug_marker"

    static func loadToken() -> String? {
        if let defaults = UserDefaults(suiteName: appGroup),
           let token = defaults.string(forKey: tokenKey),
           !token.isEmpty {
            return token
        }

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

    /// 诊断: token 读不到时返回详细状态, Siri 会读出这句话。
    /// 包含: UD suite 是否开/是否有 marker/keychain status / token bytes.
    static func loadTokenDiagnostic() -> String {
        var parts: [String] = []

        if let defaults = UserDefaults(suiteName: appGroup) {
            let hasMarker = defaults.string(forKey: markerKey)
            parts.append("UD open")
            parts.append("marker=\\(hasMarker ?? "nil")")
            let tok = defaults.string(forKey: tokenKey)
            parts.append("token=\\(tok?.isEmpty == false ? "\\(tok!.count)ch" : "nil")")
        } else {
            parts.append("UD nil")
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenKey,
            kSecAttrAccessGroup as String: appGroup,
            kSecReturnData as String: true,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        parts.append("KC=\\(status)")

        return parts.joined(separator: ", ")
    }
}
`;

// FreeTextEntity: 包装用户任意语音输入作为 AppEntity, 这样 AppShortcut 的 phrase
// 里才能带 parameter 占位符 \\(\\.$xxx) —— iOS AppIntents 规定 phrase 占位符
// 只能是 AppEntity/AppEnum 类型, 不能是 String。EntityStringQuery 让 Siri 能把
// 识别到的任意语音字符串直接构造成 entity。
//
// 用户说 "使用健康助理记录我做了20个俯卧撑":
//   1. Siri 匹配 phrase "使用\\(.applicationName)记录\\(\\.$content)"
//   2. 提取 "我做了20个俯卧撑" 作为 content
//   3. 调 FreeTextEntityQuery.entities(matching: "我做了20个俯卧撑")
//   4. 返回 FreeTextEntity(text: "我做了20个俯卧撑")
//   5. intent 的 content.text 就是完整用户说的话
const FREE_TEXT_ENTITY_SWIFT = `import AppIntents
import Foundation

struct FreeTextEntity: AppEntity {
    var id: String { text }
    let text: String

    static var typeDisplayRepresentation: TypeDisplayRepresentation {
        TypeDisplayRepresentation(name: "文本")
    }

    static var defaultQuery = FreeTextEntityQuery()

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\\(text)")
    }
}

struct FreeTextEntityQuery: EntityQuery, EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [FreeTextEntity] {
        identifiers.map { FreeTextEntity(text: $0) }
    }

    func suggestedEntities() async throws -> [FreeTextEntity] {
        []
    }

    /// Siri 识别到的语音字符串走这里, 允许任意自由文本。
    func entities(matching string: String) async throws -> [FreeTextEntity] {
        [FreeTextEntity(text: string)]
    }
}
`;

const HEALTH_COMMAND_INTENT_SWIFT = `import AppIntents
import Foundation

struct HealthCommandIntent: AppIntent {
    static let title: LocalizedStringResource = "记录健康数据"
    static let description = IntentDescription("语音快速记录饮食、饮水、运动等健康数据")
    static let openAppWhenRun = false

    @Parameter(
        title: "内容",
        description: "要记录的饮食/饮水/运动等",
        requestValueDialog: "要记录什么？例如:我做了20个俯卧撑"
    )
    var content: FreeTextEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let token = SharedKeychain.loadToken(), !token.isEmpty else {
            return .result(dialog: "请先打开健康助理 App 登录")
        }

        guard let url = URL(string: "https://health.executor.life/api/v1/agent/stream") else {
            return .result(dialog: "服务地址配置错误")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        let body: [String: Any] = ["message": content.text, "stream": false]
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

    @Parameter(
        title: "问题",
        description: "要分析什么？如:我最近的睡眠怎么样",
        requestValueDialog: "要分析什么？比如我最近的睡眠或运动表现"
    )
    var query: FreeTextEntity

    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let token = SharedKeychain.loadToken(), !token.isEmpty else {
            return .result(dialog: "请先打开健康助理 App 登录")
        }

        guard let url = URL(string: "https://health.executor.life/api/v1/orchestrator/chat/stream") else {
            return .result(dialog: "服务地址配置错误")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 60  // 多专家合成可能较慢

        let body: [String: Any] = ["query": query.text, "stream": true, "source": "siri"]
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

    @Parameter(
        title: "问题",
        description: "要分析什么？如:我最近的睡眠怎么样",
        requestValueDialog: "要分析什么？比如我最近的睡眠或运动表现"
    )
    var query: FreeTextEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        let encoded = query.text.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? ""
        if let url = URL(string: "mobile://chat?prompt=\\(encoded)&autoSend=1") {
            await UIApplication.shared.open(url)
        }
        return .result()
    }
}
`;

const HEALTH_PILOT_SHORTCUTS_SWIFT = `import AppIntents

struct HealthPilotShortcuts: AppShortcutsProvider {
    // phrase 里 \\(\\.$content) / \\(\\.$query) 是 KeyPath literal,
    // 允许用户把参数值直接说在一句话里, content/query 类型必须是 AppEntity/AppEnum
    // (我们用 FreeTextEntity 包装任意字符串)。
    //
    // 同一个 AppShortcut 的所有 phrase 必须保持一致的 parameter 结构:
    // 要么全带同样的占位符, 要么全不带。下面全带。
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: HealthCommandIntent(),
            phrases: [
                "使用\\(.applicationName)记录\\(\\.$content)",
                "使用\\(.applicationName)帮我记录\\(\\.$content)",
                "用\\(.applicationName)记录\\(\\.$content)",
                "用\\(.applicationName)帮我记\\(\\.$content)",
                "让\\(.applicationName)记下\\(\\.$content)",
                "\\(.applicationName)记一下\\(\\.$content)",
                "告诉\\(.applicationName)\\(\\.$content)",
            ],
            shortTitle: "记录健康数据",
            systemImageName: "heart.text.square"
        )
        AppShortcut(
            intent: HealthAnalysisIntent(),
            phrases: [
                "使用\\(.applicationName)分析\\(\\.$query)",
                "使用\\(.applicationName)帮我分析\\(\\.$query)",
                "用\\(.applicationName)分析\\(\\.$query)",
                "让\\(.applicationName)分析\\(\\.$query)",
                "问\\(.applicationName)\\(\\.$query)",
                "\\(.applicationName)告诉我\\(\\.$query)",
            ],
            shortTitle: "综合分析",
            systemImageName: "sparkles"
        )
        AppShortcut(
            intent: HealthAnalysisOpenIntent(),
            phrases: [
                "打开\\(.applicationName)分析\\(\\.$query)",
                "用\\(.applicationName)打开并分析\\(\\.$query)",
                "\\(.applicationName)打开并分析\\(\\.$query)",
            ],
            shortTitle: "打开并分析",
            systemImageName: "arrow.up.forward.app"
        )
    }
}
`;

module.exports = withIntentsExtension;
