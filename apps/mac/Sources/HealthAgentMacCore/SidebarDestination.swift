public enum SidebarDestination: String, CaseIterable, Identifiable, Sendable {
    case today
    case agent
    case record
    case data
    case genetics
    case knowledge
    case jobs
    case trace
    case settings

    public var id: String { rawValue }

    /// Primary sidebar set. Settings is included so sign-out / account
    /// switching is discoverable without knowing the cmd+, shortcut.
    /// Jobs/Trace remain reachable via right-rail panels or the command palette.
    public static let sidebarVisible: [SidebarDestination] = [
        .today, .agent, .record, .data, .genetics, .knowledge, .settings
    ]

    public var title: String {
        title(language: .en)
    }

    public func title(language: AppLanguage) -> String {
        switch self {
        case .today: L10n.text("Today", language: language)
        case .agent: L10n.text("Agent", language: language)
        case .record: L10n.text("Record", language: language)
        case .data: L10n.text("Data", language: language)
        case .genetics: L10n.text("Genetics", language: language)
        case .knowledge: L10n.text("Knowledge", language: language)
        case .jobs: L10n.text("Jobs", language: language)
        case .trace: L10n.text("Trace", language: language)
        case .settings: L10n.text("Settings", language: language)
        }
    }

    public var systemImage: String {
        switch self {
        case .today: "sparkles"
        case .agent: "bubble.left.and.bubble.right"
        case .record: "plus.circle"
        case .data: "chart.line.uptrend.xyaxis"
        case .genetics: "atom"
        case .knowledge: "books.vertical"
        case .jobs: "clock.arrow.circlepath"
        case .trace: "point.3.connected.trianglepath.dotted"
        case .settings: "gearshape"
        }
    }
}
