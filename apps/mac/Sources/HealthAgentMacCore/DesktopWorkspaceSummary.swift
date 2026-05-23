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
    public let recentRecords: [DesktopRecordMetric]
    public let actionCards: [ActionCardSummary]
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
            recentMemory: recentMemory.filter { !$0.objectValue.isLowSignalWorkspaceMemory },
            recentRecords: recentRecords(for: kind),
            actionCards: actionCards(for: kind),
            jobs: jobs(for: kind)
        )
    }

    private func metrics(for kind: DesktopWorkspaceKind) -> [DesktopWorkspaceMetric] {
        switch kind {
        case .data:
            return [
                .init(id: "diet_calories", title: "Diet 7d", value: "\(formatWorkspaceNumber(recentRecordsSummary.diet?.last7Calories ?? recentRecordsSummary.diet?.todayCalories ?? 0)) kcal"),
                .init(id: "water_ml", title: "Water 7d", value: "\(formatWorkspaceNumber(Double(recentRecordsSummary.water?.last7TotalMl ?? recentRecordsSummary.water?.todayTotalMl ?? 0))) ml"),
                .init(id: "supplements", title: "Supplements 7d", value: "\(recentRecordsSummary.supplements?.last7Count ?? recentRecordsSummary.supplements?.todayCount ?? 0)"),
                .init(id: "latest_weight", title: "Latest Weight", value: recentRecordsSummary.latestWeight?.displayValue ?? "—"),
                .init(id: "latest_bp", title: "Latest BP", value: recentRecordsSummary.latestBloodPressure?.displayValue ?? "—"),
                .init(id: "steps", title: "Steps", value: recentRecordsSummary.latestGarmin?.steps.map { formatWorkspaceNumber(Double($0)) } ?? "—")
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

    private func recentRecords(for kind: DesktopWorkspaceKind) -> [DesktopRecordMetric] {
        guard kind == .data else { return [] }
        return Array((recentRecordsSummary.recentRecords ?? []).prefix(8))
    }

    private func actionCards(for kind: DesktopWorkspaceKind) -> [ActionCardSummary] {
        switch kind {
        case .data:
            return actionCards.filter { card in
                let haystack = card.title.lowercased()
                return haystack.contains("hba1c")
                    || haystack.contains("血")
                    || haystack.contains("体重")
                    || haystack.contains("饮")
                    || haystack.contains("补剂")
                    || haystack.contains("睡")
                    || haystack.contains("运动")
            }
        case .genetics:
            return actionCards.filter { $0.title.lowercased().contains("基因") || $0.title.lowercased().contains("gene") }
        case .knowledge:
            return []
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

private extension String {
    var isLowSignalWorkspaceMemory: Bool {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count >= 4 else { return true }
        return trimmed.allSatisfy { $0.isNumber || $0 == "." || $0 == "%" }
    }
}

private func formatWorkspaceNumber(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.numberStyle = .decimal
    formatter.usesGroupingSeparator = true
    formatter.minimumFractionDigits = 0
    formatter.maximumFractionDigits = value.rounded() == value ? 0 : 1
    return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
}
