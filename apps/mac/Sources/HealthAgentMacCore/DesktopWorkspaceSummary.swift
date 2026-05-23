import Foundation

public enum DesktopWorkspaceKind: String, CaseIterable, Identifiable, Sendable {
    case data
    case genetics
    case knowledge

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .data: "Data"
        case .genetics: "Genetics"
        case .knowledge: "Knowledge"
        }
    }

    public var subtitle: String {
        switch self {
        case .data: "Labs, records, trajectory, and active medical imports."
        case .genetics: "Genome reanalysis jobs, source hashes, and risk-boundary handoff."
        case .knowledge: "Dedao compilation, system KB rebuilds, and source coverage."
        }
    }
}

public struct DesktopWorkspaceMetric: Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let value: String
}

public struct DesktopWorkspaceSummary: Equatable, Sendable {
    public let kind: DesktopWorkspaceKind
    public let title: String
    public let subtitle: String
    public let metrics: [DesktopWorkspaceMetric]
    public let focusDomains: [String]
    public let recentMemory: [MemoryFactSummary]
    public let jobs: [DesktopJobSummary]
}

public extension DesktopBootstrap {
    func workspaceSummary(for kind: DesktopWorkspaceKind) -> DesktopWorkspaceSummary {
        DesktopWorkspaceSummary(
            kind: kind,
            title: kind.title,
            subtitle: kind.subtitle,
            metrics: metrics(for: kind),
            focusDomains: trajectory.focusDomains ?? [],
            recentMemory: recentMemory,
            jobs: jobs(for: kind)
        )
    }

    private func metrics(for kind: DesktopWorkspaceKind) -> [DesktopWorkspaceMetric] {
        switch kind {
        case .data:
            return [
                .init(id: "diet_calories", title: "Diet", value: "\(recentRecordsSummary.diet?.todayCalories ?? 0) kcal"),
                .init(id: "water_ml", title: "Water", value: "\(recentRecordsSummary.water?.todayTotalMl ?? 0) ml"),
                .init(id: "focus_domains", title: "Focus", value: "\(trajectory.focusDomains?.count ?? 0)")
            ]
        case .genetics:
            let running = jobs(for: .genetics).filter { $0.status == "queued" || $0.status == "running" }.count
            return [
                .init(id: "gene_jobs", title: "Gene Jobs", value: "\(jobs(for: .genetics).count)"),
                .init(id: "running", title: "Running", value: "\(running)"),
                .init(id: "memory", title: "Memory", value: "\(recentMemory.count)")
            ]
        case .knowledge:
            let running = jobs(for: .knowledge).filter { $0.status == "queued" || $0.status == "running" }.count
            return [
                .init(id: "kb_jobs", title: "KB Jobs", value: "\(jobs(for: .knowledge).count)"),
                .init(id: "running", title: "Running", value: "\(running)"),
                .init(id: "sources", title: "Sources", value: "\(recentMemory.count)")
            ]
        }
    }

    private func jobs(for kind: DesktopWorkspaceKind) -> [DesktopJobSummary] {
        activeJobs.filter { job in
            switch kind {
            case .data:
                return job.jobType == "medical_import"
            case .genetics:
                return job.jobType == "gene_reanalysis"
            case .knowledge:
                return job.jobType == "system_kb_rebuild" || job.jobType == "dedao_compile"
            }
        }
    }
}
