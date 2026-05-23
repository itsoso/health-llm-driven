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

public struct DesktopWorkspaceGuidanceRow: Equatable, Identifiable, Sendable {
    public let id: String
    public let title: String
    public let detail: String
    public let systemImage: String
    public let tone: String
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
    public let guidanceRows: [DesktopWorkspaceGuidanceRow]
    public let jobs: [DesktopJobSummary]
    public let genomicSummary: GenomicSummary?
    public let knowledgeSummary: KnowledgeSummary?
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
            guidanceRows: guidanceRows(for: kind),
            jobs: jobs(for: kind),
            genomicSummary: kind == .genetics ? genomicSummary : nil,
            knowledgeSummary: kind == .knowledge ? knowledgeSummary : nil
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
            if let genomicSummary, genomicSummary.recordCount > 0 {
                return [
                    .init(id: "variants", title: "Variants", value: formatWorkspaceNumber(Double(genomicSummary.recordCount))),
                    .init(id: "high_risk", title: "High Risk", value: formatWorkspaceNumber(Double(genomicSummary.highRiskCount))),
                    .init(id: "medium_risk", title: "Medium Risk", value: formatWorkspaceNumber(Double(genomicSummary.mediumRiskCount))),
                    .init(id: "categories", title: "Categories", value: formatWorkspaceNumber(Double(genomicSummary.categoryCount)))
                ]
            }
            let running = jobs(for: .genetics).filter { $0.status == "queued" || $0.status == "running" }.count
            return [
                .init(id: "gene_jobs", title: "Gene Jobs", value: "\(jobs(for: .genetics).count)"),
                .init(id: "running", title: "Running", value: "\(running)"),
                .init(id: "action_cards", title: "Action Cards", value: "\(actionCards(for: .genetics).count)"),
                .init(id: "memory", title: "Memory", value: "\(recentMemory.filter { !$0.objectValue.isLowSignalWorkspaceMemory }.count)")
            ]
        case .knowledge:
            if let knowledgeSummary, knowledgeSummary.documentCount > 0 {
                return [
                    .init(id: "documents", title: "Documents", value: formatWorkspaceNumber(Double(knowledgeSummary.documentCount))),
                    .init(id: "claims", title: "Claims", value: formatWorkspaceNumber(Double(knowledgeSummary.claimCount))),
                    .init(id: "sources", title: "Sources", value: formatWorkspaceNumber(Double(knowledgeSummary.sourceCounts.count))),
                    .init(id: "edges", title: "Edges", value: formatWorkspaceNumber(Double(knowledgeSummary.edgeCount)))
                ]
            }
            let running = jobs(for: .knowledge).filter { $0.status == "queued" || $0.status == "running" }.count
            return [
                .init(id: "kb_jobs", title: "KB Jobs", value: "\(jobs(for: .knowledge).count)"),
                .init(id: "running", title: "Running", value: "\(running)"),
                .init(id: "focus_domains", title: "Focus", value: "\(trajectory.focusDomains?.count ?? 0)"),
                .init(id: "memory", title: "Memory", value: "\(recentMemory.filter { !$0.objectValue.isLowSignalWorkspaceMemory }.count)")
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
                if haystack.contains("基因") || haystack.contains("gene") {
                    return false
                }
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
            return actionCards.filter { card in
                let haystack = card.title.lowercased()
                return haystack.contains("知识")
                    || haystack.contains("得到")
                    || haystack.contains("dedao")
                    || haystack.contains("kb")
                    || haystack.contains("source")
            }
        }
    }

    private func guidanceRows(for kind: DesktopWorkspaceKind) -> [DesktopWorkspaceGuidanceRow] {
        switch kind {
        case .data:
            return [
                .init(id: "refresh_data", title: "Refresh recent health data", detail: "Update labs, records, wearable trajectory, and medical imports before analysis.", systemImage: "arrow.clockwise", tone: "blue"),
                .init(id: "review_intake", title: "Review weekly intake", detail: "Use the 7-day diet, water, and supplement baseline before making daily decisions.", systemImage: "chart.xyaxis.line", tone: "teal"),
                .init(id: "medical_import", title: "Create medical import", detail: "Register lab PDFs or Apple Health exports as auditable desktop jobs.", systemImage: "doc.badge.plus", tone: "orange")
            ]
        case .genetics:
            return [
                .init(id: "import_genome", title: "Import genome file", detail: "Drop WeGene, 23andMe, or other raw genotype txt files to create a reanalysis job.", systemImage: "dna", tone: "purple"),
                .init(id: "risk_reanalysis", title: "Run risk reanalysis", detail: "Rebuild risk calls with source hashes, confidence, and uncertainty boundaries.", systemImage: "waveform.path.ecg.rectangle", tone: "teal"),
                .init(id: "clinical_boundary", title: "Keep clinical boundary", detail: "Treat genetic results as risk stratification, not diagnosis or medication decisions.", systemImage: "exclamationmark.shield.fill", tone: "orange")
            ]
        case .knowledge:
            return [
                .init(id: "import_dedao", title: "Import Dedao folder", detail: "Use the local down-dedao health courses and ebooks as source material.", systemImage: "folder.badge.plus", tone: "blue"),
                .init(id: "rebuild_kb", title: "Rebuild system KB", detail: "Compile claims, evidence refs, and source coverage for safer Agent answers.", systemImage: "books.vertical.fill", tone: "teal"),
                .init(id: "audit_sources", title: "Audit source coverage", detail: "Check whether answers cite enough dedao, pubmed, and system evidence.", systemImage: "checklist.checked", tone: "indigo")
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
