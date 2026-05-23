public enum SidebarDestination: String, CaseIterable, Identifiable, Sendable {
    case today
    case agent
    case record
    case data
    case genetics
    case knowledge
    case jobs
    case settings

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .today: "Today"
        case .agent: "Agent"
        case .record: "Record"
        case .data: "Data"
        case .genetics: "Genetics"
        case .knowledge: "Knowledge"
        case .jobs: "Jobs"
        case .settings: "Settings"
        }
    }

    public var systemImage: String {
        switch self {
        case .today: "sparkles"
        case .agent: "bubble.left.and.bubble.right"
        case .record: "plus.circle"
        case .data: "chart.line.uptrend.xyaxis"
        case .genetics: "helix"
        case .knowledge: "books.vertical"
        case .jobs: "clock.arrow.circlepath"
        case .settings: "gearshape"
        }
    }
}
