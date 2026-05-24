import Foundation

public struct DesktopTaskCenterPresentation: Equatable, Sendable {
    public let jobs: [DesktopJobSummary]
    public let actionCards: [ActionCardSummary]

    public var totalCount: Int {
        jobs.count + actionCards.count
    }

    public var runningJobCount: Int {
        jobs.filter { Self.activeStatuses.contains($0.status) }.count
    }

    public var failedJobCount: Int {
        jobs.filter { $0.status == "failed" }.count
    }

    public var isEmpty: Bool {
        jobs.isEmpty && actionCards.isEmpty
    }

    public init(jobs: [DesktopJobSummary], actionCards: [ActionCardSummary]) {
        self.jobs = jobs
        self.actionCards = actionCards
            .filter { ($0.status ?? "active") != "archived" }
            .sorted {
                if ($0.priority ?? 0) == ($1.priority ?? 0) {
                    return $0.id < $1.id
                }
                return ($0.priority ?? 0) > ($1.priority ?? 0)
            }
    }

    private static let activeStatuses: Set<String> = ["queued", "running"]
}
