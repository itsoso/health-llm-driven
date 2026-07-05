public enum SidebarDestination: String, CaseIterable, Identifiable, Sendable {
    case today
    case schedule
    case agenda
    case review
    case timeline
    case calendar
    case agent
    case record
    case data
    case dataSources
    case dataConnections
    case prescriptions
    case liver
    case healthExtras
    case genetics
    case knowledge
    case workouts
    case goals
    case jobs
    case trace
    case settings

    public var id: String { rawValue }

    /// Grouped sidebar sections — the single source of truth for sidebar ordering.
    /// Settings is pinned separately at the bottom of the sidebar (not in a section).
    /// Jobs/Trace remain reachable via right-rail panels or the command palette.
    public static let sidebarSections: [SidebarSection] = [
        // 小巴(助手)= 默认第一入口。无标题的顶部主操作区,置于所有分组之上。
        SidebarSection(id: "primary", titleKey: "",
                       items: [.agent, .record]),
        // 每日:今日(仪表盘)+ 日程(时间线·议程·日历 三合一标签页)。
        SidebarSection(id: "daily", titleKey: "Daily",
                       items: [.today, .schedule]),
        SidebarSection(id: "health", titleKey: "Health",
                       items: [.data, .workouts, .goals]),
        // 洞察:复盘(回顾/预测回测,非当日规划)归入此处 + 深度分析视图。
        SidebarSection(id: "insights", titleKey: "Insights",
                       items: [.review, .healthExtras, .liver, .genetics, .prescriptions]),
        SidebarSection(id: "resources", titleKey: "Resources",
                       items: [.dataSources, .dataConnections, .knowledge]),
    ]

    /// Flat list of all sidebar-visible destinations (sections + Settings), derived
    /// from `sidebarSections` so ordering can never drift. Settings is included so
    /// sign-out / account switching is discoverable without the cmd+, shortcut.
    public static let sidebarVisible: [SidebarDestination] =
        sidebarSections.flatMap(\.items) + [.settings]

    public var title: String {
        title(language: .en)
    }

    public func title(language: AppLanguage) -> String {
        switch self {
        case .today: L10n.text("Today", language: language)
        case .schedule: L10n.text("Schedule", language: language)
        case .agenda: L10n.text("Agenda", language: language)
        case .review: L10n.text("Review", language: language)
        case .timeline: L10n.text("Today Timeline", language: language)
        case .calendar: L10n.text("Calendar", language: language)
        case .agent: L10n.text("Agent", language: language)
        case .record: L10n.text("Record", language: language)
        case .data: L10n.text("Data", language: language)
        case .dataSources: L10n.text("Data Sources", language: language)
        case .dataConnections: L10n.text("Data Connections", language: language)
        case .prescriptions: L10n.text("Originator Drugs", language: language)
        case .liver: L10n.text("Liver Trend", language: language)
        case .healthExtras: L10n.text("Health Extras", language: language)
        case .genetics: L10n.text("Genetics", language: language)
        case .knowledge: L10n.text("Knowledge", language: language)
        case .workouts: L10n.text("Workouts", language: language)
        case .goals: L10n.text("Goals", language: language)
        case .jobs: L10n.text("Jobs", language: language)
        case .trace: L10n.text("Trace", language: language)
        case .settings: L10n.text("Settings", language: language)
        }
    }

    public var systemImage: String {
        switch self {
        case .today: "sparkles"
        case .schedule: "calendar.day.timeline.left"
        case .agenda: "calendar.badge.checkmark"
        case .review: "arrow.triangle.2.circlepath"
        case .timeline: "calendar.day.timeline.left"
        case .calendar: "calendar.badge.clock"
        case .agent: "bubble.left.and.bubble.right"
        case .record: "plus.circle"
        case .data: "chart.line.uptrend.xyaxis"
        case .dataSources: "applewatch"
        case .dataConnections: "shield.lefthalf.filled"
        case .prescriptions: "pills"
        case .liver: "waveform.path.ecg"
        case .healthExtras: "heart.text.square"
        case .genetics: "atom"
        case .knowledge: "books.vertical"
        case .workouts: "figure.run"
        case .goals: "target"
        case .jobs: "clock.arrow.circlepath"
        case .trace: "point.3.connected.trianglepath.dotted"
        case .settings: "gearshape"
        }
    }
}

/// A titled group of sidebar destinations. `titleKey` is an English L10n key
/// resolved via `L10n.text` (mirrors `SidebarDestination.title(language:)`).
public struct SidebarSection: Identifiable, Sendable {
    public let id: String
    public let titleKey: String
    public let items: [SidebarDestination]

    public init(id: String, titleKey: String, items: [SidebarDestination]) {
        self.id = id
        self.titleKey = titleKey
        self.items = items
    }

    public func title(language: AppLanguage) -> String {
        L10n.text(titleKey, language: language)
    }
}
