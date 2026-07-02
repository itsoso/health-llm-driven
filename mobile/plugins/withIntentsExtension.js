/**
 * Expo Config Plugin — withIntentsExtension
 *
 * Single-file Swift bundle approach: all Siri code lives in ONE file
 * (HealthPilotSiri.swift) to eliminate multi-file addSourceFile risk
 * that silently dropped AppShortcutsProvider registration in some builds.
 *
 * Three AppIntents:
 *   1. HealthCommandIntent        — voice-log health data (不开 App)
 *   2. HealthAnalysisIntent       — voice multi-specialist analysis (不开 App, source=siri 后端走 fast path)
 *   3. HealthAnalysisOpenIntent   — open App to voice-chat page, connected voice dialogue
 *
 * Usage in app.json:
 *   "plugins": ["./plugins/withIntentsExtension"]
 */
const { withXcodeProject, withEntitlementsPlist, withInfoPlist } = require('@expo/config-plugins');
const path = require('path');
const fs = require('fs');

const APP_GROUP = 'group.life.executor.health';

function withIntentsExtension(config) {
  // 1. Entitlements: Siri + App Group + Keychain Sharing (legacy fallback)
  config = withEntitlementsPlist(config, (mod) => {
    mod.modResults['com.apple.developer.siri'] = true;
    mod.modResults['com.apple.security.application-groups'] = [APP_GROUP];
    mod.modResults['keychain-access-groups'] = [
      `$(AppIdentifierPrefix)${APP_GROUP}`,
    ];
    return mod;
  });

  // 2. Info.plist Siri usage description
  config = withInfoPlist(config, (mod) => {
    if (!mod.modResults.NSSiriUsageDescription) {
      mod.modResults.NSSiriUsageDescription = '使用 Siri 语音记录健康数据';
    }
    return mod;
  });

  // 3. Write single Swift file to main app target
  config = withXcodeProject(config, (mod) => {
    const proj = mod.modRequest.projectRoot;
    const xcodeProject = mod.modResults;

    const siriPath = path.join(proj, 'ios', 'HealthPilot', 'SiriIntents');
    if (!fs.existsSync(siriPath)) {
      fs.mkdirSync(siriPath, { recursive: true });
    }

    // Clean up legacy multi-file setup — previous builds left 5 .swift files,
    // if they remain on disk but not tracked in pbxproj they would cause
    // "file not found" warnings or worse, duplicate symbol links.
    for (const stale of [
      'SharedKeychain.swift',
      'FreeTextEntity.swift',
      'HealthCommandIntent.swift',
      'HealthAnalysisIntent.swift',
      'HealthAnalysisOpenIntent.swift',
      'HealthPilotShortcuts.swift',
    ]) {
      const p = path.join(siriPath, stale);
      if (fs.existsSync(p)) fs.unlinkSync(p);
    }

    const singleFile = 'HealthPilotSiri.swift';
    const filePath = path.join(siriPath, singleFile);
    fs.writeFileSync(filePath, buildSiriSwift(APP_GROUP), 'utf-8');

    // Add single file to main app target's Sources build phase
    const mainTargetName = 'HealthPilot';
    const targets = xcodeProject.pbxNativeTargetSection();
    let mainTargetUuid = null;
    for (const [uuid, target] of Object.entries(targets)) {
      if (target.name === mainTargetName && !uuid.endsWith('_comment')) {
        mainTargetUuid = uuid;
        break;
      }
    }

    const siriGroup = xcodeProject.addPbxGroup(
      [],
      'SiriIntents',
      'HealthPilot/SiriIntents',
    );
    const mainGroup = xcodeProject.getFirstProject().firstProject.mainGroup;
    xcodeProject.addToPbxGroup(siriGroup.uuid, mainGroup);

    if (mainTargetUuid) {
      xcodeProject.addSourceFile(
        singleFile,
        { target: mainTargetUuid },
        siriGroup.uuid,
      );
    }

    return mod;
  });

  return config;
}

function buildSiriSwift(appGroup) {
  return `import AppIntents
import Foundation
import Security
import UIKit

// ============================================================================
// SharedKeychain — cross-process token sharing with Siri extension.
// Writes & reads both App Group UserDefaults (primary) + shared Keychain (legacy).
// ============================================================================

struct SharedKeychain {
    static let service = "life.executor.health.shared"
    static let appGroup = "${appGroup}"
    static let tokenKey = "siri_auth_token"

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
}

// ============================================================================
// FreeTextEntity — wrap arbitrary voice text as AppEntity, enabling phrase
// placeholders like "使用健康助理记录\\(\\.$content)".
// ============================================================================

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
    func suggestedEntities() async throws -> [FreeTextEntity] { [] }
    func entities(matching string: String) async throws -> [FreeTextEntity] {
        [FreeTextEntity(text: string)]
    }
}

// ============================================================================
// HealthCommandIntent — voice-log health data, no App open.
// ============================================================================

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

        let body: [String: Any] = ["message": content.text, "channel": "siri"]
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
            // SSE 线格式: 每行 \`data: {"event":"token","data":{"content":"..."}}\`。
            // token 累积 data.content; done 结束; error → 该次记录失败, 绝不播报"已记录"。
            guard let text = String(data: data, encoding: .utf8), !text.isEmpty else {
                return .result(dialog: "记录失败，请打开健康助理 App 确认")
            }
            var accumulated = ""
            var sawError = false
            for line in text.components(separatedBy: "\\n") {
                guard line.hasPrefix("data: ") else { continue }
                let jsonStr = String(line.dropFirst(6))
                guard let jsonData = jsonStr.data(using: .utf8),
                      let json = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any] else {
                    continue
                }
                let eventType = json["event"] as? String
                let payload = json["data"] as? [String: Any]
                if eventType == "error" {
                    sawError = true
                    break
                }
                if eventType == "token", let c = payload?["content"] as? String {
                    accumulated += c
                }
                // done: 结束标记, 无需额外累积 (elapsed_ms 可读但不入播报)。
            }
            if sawError {
                return .result(dialog: "记录失败，请打开健康助理 App 确认")
            }
            let trimmed = accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty {
                // 空回复 = 无法确认是否写入, 保守按失败处理, 不假报成功。
                return .result(dialog: "记录失败，请打开健康助理 App 确认")
            }
            let display = trimmed.count > 200 ? String(trimmed.prefix(200)) + "..." : trimmed
            return .result(dialog: "\\(display)")
        } catch {
            return .result(dialog: "网络错误，请检查网络连接")
        }
    }
}

// ============================================================================
// HealthAnalysisIntent — voice analysis, no App open.
// source=siri triggers backend fast path (Twin + LLM only, ~3-5s).
// ============================================================================

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
        guard let url = URL(string: "https://health.executor.life/api/v1/orchestrator/chat") else {
            return .result(dialog: "服务地址配置错误")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \\(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 25

        let body: [String: Any] = ["query": query.text, "stream": false, "source": "siri"]
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
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let synthesis = json["synthesis"] as? String, !synthesis.isEmpty else {
                return .result(dialog: "暂无分析结论，请稍后再试")
            }
            let trimmed = synthesis.trimmingCharacters(in: .whitespacesAndNewlines)
            let display = trimmed.count > 300 ? String(trimmed.prefix(300)) + "…" : trimmed
            return .result(dialog: "\\(display)")
        } catch {
            return .result(dialog: "网络错误，请检查网络连接")
        }
    }
}

// ============================================================================
// HealthAnalysisOpenIntent — open App to voice chat page.
// ============================================================================

struct HealthAnalysisOpenIntent: AppIntent {
    static let title: LocalizedStringResource = "打开健康助理 并分析"
    static let description = IntentDescription("打开 App 进入语音对话, 直接和健康助理连续聊")
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
        if let url = URL(string: "mobile://voice?autoStart=1&prompt=\\(encoded)") {
            await UIApplication.shared.open(url)
        }
        return .result()
    }
}

// ============================================================================
// QuickWaterIntent — 手腕零听写速记。固定一句"喝了一杯水", 抬腕说四个字即记,
// 表上极简确认(不念后端长回复)。无参数 → Apple Watch Siri 上摩擦最低的打卡。
// openAppWhenRun=false: 不唤起 App, 表上原地完成。
// ============================================================================

struct QuickWaterIntent: AppIntent {
    static let title: LocalizedStringResource = "记一杯水"
    static let description = IntentDescription("抬腕一句话记录喝了一杯水, 无需听写整句")
    static let openAppWhenRun = false

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
        let body: [String: Any] = ["message": "记录我喝了一杯水(约250毫升)", "channel": "siri"]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return .result(dialog: "网络请求失败")
            }
            if httpResponse.statusCode == 401 {
                return .result(dialog: "登录已过期, 请打开健康助理 重新登录")
            }
            if httpResponse.statusCode >= 400 {
                return .result(dialog: "服务暂时不可用, 请稍后再试")
            }
            // SSE 线格式: 每行 \`data: {"event":"token","data":{"content":"..."}}\`。
            // 表上极简确认, 但必须先确认后端真写入: error 或空回复 → 报失败, 绝不假说"已记录"。
            guard let text = String(data: data, encoding: .utf8), !text.isEmpty else {
                return .result(dialog: "记录失败, 请打开健康助理 App 确认")
            }
            var accumulated = ""
            var sawError = false
            for line in text.components(separatedBy: "\\n") {
                guard line.hasPrefix("data: ") else { continue }
                let jsonStr = String(line.dropFirst(6))
                guard let jsonData = jsonStr.data(using: .utf8),
                      let json = try? JSONSerialization.jsonObject(with: jsonData) as? [String: Any] else {
                    continue
                }
                let eventType = json["event"] as? String
                let payload = json["data"] as? [String: Any]
                if eventType == "error" {
                    sawError = true
                    break
                }
                if eventType == "token", let c = payload?["content"] as? String {
                    accumulated += c
                }
            }
            if sawError || accumulated.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return .result(dialog: "记录失败, 请打开健康助理 App 确认")
            }
            // 后端确实产出了回复才播报成功; 表上仍用极简固定一句, 不回放长文本。
            return .result(dialog: "已记录一杯水")
        } catch {
            return .result(dialog: "网络错误, 请检查网络连接")
        }
    }
}

// ============================================================================
// AppShortcutsProvider — registers all 4 intents with Siri.
// phrase 里 \\(\\.$content) / \\(\\.$query) 只有当 parameter 类型是
// AppEntity/AppEnum 时才合法, 我们用 FreeTextEntity 包装任意字符串。
// ============================================================================

struct HealthPilotShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: HealthCommandIntent(),
            phrases: [
                "使用\\(.applicationName)记录",
                "用\\(.applicationName)记录",
                "让\\(.applicationName)记录",
                "告诉\\(.applicationName)",
                "\\(.applicationName)记一下",
                "打开\\(.applicationName)记录",
            ],
            shortTitle: "记录健康数据",
            systemImageName: "heart.text.square"
        )
        AppShortcut(
            intent: QuickWaterIntent(),
            phrases: [
                "使用\\(.applicationName)记一杯水",
                "用\\(.applicationName)记一杯水",
                "\\(.applicationName)记一杯水",
                "\\(.applicationName)喝水打卡",
            ],
            shortTitle: "记一杯水",
            systemImageName: "drop.fill"
        )
        AppShortcut(
            intent: HealthAnalysisIntent(),
            phrases: [
                "使用\\(.applicationName)分析",
                "用\\(.applicationName)分析",
                "让\\(.applicationName)分析",
                "问\\(.applicationName)",
                "\\(.applicationName)分析一下",
            ],
            shortTitle: "综合分析",
            systemImageName: "sparkles"
        )
        AppShortcut(
            intent: HealthAnalysisOpenIntent(),
            phrases: [
                "打开\\(.applicationName)",
                "启动\\(.applicationName)",
            ],
            shortTitle: "打开并分析",
            systemImageName: "arrow.up.forward.app"
        )
    }
}
`;
}

module.exports = withIntentsExtension;
// Exported for template-content tests (mirrors _patchPodfileContents convention).
module.exports._buildSiriSwift = buildSiriSwift;
