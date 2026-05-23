import Foundation

public enum DesktopCommandPaletteIntent: Equatable, Sendable {
    case navigate(SidebarDestination)
    case quickPrompt
    case refresh
}

public struct DesktopCommandPaletteCommand: Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let subtitle: String
    public let systemImage: String
    public let keywords: [String]
    public let intent: DesktopCommandPaletteIntent

    public init(
        id: String,
        title: String,
        subtitle: String,
        systemImage: String,
        keywords: [String],
        intent: DesktopCommandPaletteIntent
    ) {
        self.id = id
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.keywords = keywords
        self.intent = intent
    }
}

public enum DesktopCommandPalette {
    public static func defaultCommands(language: AppLanguage) -> [DesktopCommandPaletteCommand] {
        [
            navigateCommand(.today, language: language, keywords: ["dashboard", "home", "today", "看板", "首页", "今日"]),
            navigateCommand(.agent, language: language, keywords: ["agent", "chat", "analysis", "assistant", "问", "助手", "分析"]),
            navigateCommand(.record, language: language, keywords: ["record", "food", "water", "supplement", "diet", "饮食", "饮水", "补剂", "记录"]),
            navigateCommand(.data, language: language, keywords: ["data", "labs", "records", "trend", "化验", "趋势", "健康数据"]),
            navigateCommand(.genetics, language: language, keywords: ["gene", "genome", "genetic", "wegene", "23andme", "基因", "位点"]),
            navigateCommand(.knowledge, language: language, keywords: ["knowledge", "kb", "dedao", "source", "知识", "得到", "证据"]),
            navigateCommand(.jobs, language: language, keywords: ["jobs", "task", "import", "任务", "导入"]),
            navigateCommand(.trace, language: language, keywords: ["trace", "evidence", "tool", "追踪", "工具", "证据"]),
            .init(
                id: "quick_prompt",
                title: L10n.text("Ask Agent with Current Context", language: language),
                subtitle: L10n.text("Open Agent with the selected context basket.", language: language),
                systemImage: "sparkles",
                keywords: ["ask", "agent", "context", "prompt", "问助手", "上下文"],
                intent: .quickPrompt
            ),
            .init(
                id: "refresh",
                title: L10n.text("Refresh Desktop Data", language: language),
                subtitle: L10n.text("Reload dashboard, records, genes, knowledge, and jobs.", language: language),
                systemImage: "arrow.clockwise",
                keywords: ["refresh", "reload", "sync", "刷新", "同步"],
                intent: .refresh
            )
        ]
    }

    public static func filter(
        _ commands: [DesktopCommandPaletteCommand],
        query: String
    ) -> [DesktopCommandPaletteCommand] {
        let normalizedQuery = normalize(query)
        guard !normalizedQuery.isEmpty else {
            return commands
        }

        return commands
            .compactMap { command -> (DesktopCommandPaletteCommand, Int)? in
                guard let score = matchScore(command, query: normalizedQuery) else {
                    return nil
                }
                return (command, score)
            }
            .sorted {
                if $0.1 == $1.1 {
                    return $0.0.title.localizedStandardCompare($1.0.title) == .orderedAscending
                }
                return $0.1 < $1.1
            }
            .map(\.0)
    }

    private static func navigateCommand(
        _ destination: SidebarDestination,
        language: AppLanguage,
        keywords: [String]
    ) -> DesktopCommandPaletteCommand {
        .init(
            id: "nav_\(destination.rawValue)",
            title: L10n.text("Open \(destination.title)", language: language),
            subtitle: destinationSubtitle(destination, language: language),
            systemImage: destination.systemImage,
            keywords: keywords,
            intent: .navigate(destination)
        )
    }

    private static func destinationSubtitle(
        _ destination: SidebarDestination,
        language: AppLanguage
    ) -> String {
        switch destination {
        case .today:
            L10n.text("Daily dashboard, priorities, and recent context.", language: language)
        case .agent:
            L10n.text("Ask questions with files, selected context, and evidence.", language: language)
        case .record:
            L10n.text("Record diet, water, supplements, vitals, and symptoms.", language: language)
        case .data:
            L10n.text("Inspect records, trends, labs, and wearable summaries.", language: language)
        case .genetics:
            L10n.text("Review genome findings, risk boundaries, and imports.", language: language)
        case .knowledge:
            L10n.text("Review source coverage, claims, and evidence.", language: language)
        case .jobs:
            L10n.text("Inspect import, reanalysis, and rebuild jobs.", language: language)
        case .trace:
            L10n.text("Inspect Agent model, tool, source, and timing traces.", language: language)
        case .settings:
            L10n.text("Manage login, API, language, voice, and privacy.", language: language)
        }
    }

    private static func matchScore(
        _ command: DesktopCommandPaletteCommand,
        query: String
    ) -> Int? {
        let fields = [command.title, command.subtitle] + command.keywords
        var bestScore: Int?

        for field in fields {
            let normalizedField = normalize(field)
            if normalizedField == query {
                bestScore = min(bestScore ?? 0, 0)
            } else if normalizedField.hasPrefix(query) {
                bestScore = min(bestScore ?? 1, 1)
            } else if normalizedField.contains(query) {
                bestScore = min(bestScore ?? 2, 2)
            }
        }

        return bestScore
    }

    private static func normalize(_ value: String) -> String {
        value
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .folding(options: [.caseInsensitive, .diacriticInsensitive, .widthInsensitive], locale: .current)
            .lowercased()
    }
}
