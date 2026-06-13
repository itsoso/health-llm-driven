public enum SidebarDestination: String, CaseIterable, Identifiable, Sendable {
    case today
    case agent
    case record
    case data
    case dataSources
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

    /// Primary sidebar set. Settings is included so sign-out / account
    /// switching is discoverable without knowing the cmd+, shortcut.
    /// Jobs/Trace remain reachable via right-rail panels or the command palette.
    public static let sidebarVisible: [SidebarDestination] = [
        .today, .agent, .record, .data, .dataSources, .prescriptions, .liver, .healthExtras, .genetics, .knowledge, .workouts, .goals, .settings
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
        case .dataSources: L10n.text("Data Sources", language: language)
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
        case .agent: "bubble.left.and.bubble.right"
        case .record: "plus.circle"
        case .data: "chart.line.uptrend.xyaxis"
        case .dataSources: "applewatch"
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
