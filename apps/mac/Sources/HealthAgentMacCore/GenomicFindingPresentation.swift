import Foundation

public struct GenomicFindingDisplayGroup: Equatable, Identifiable, Sendable {
    public let id: String
    public let primary: GenomicFindingSummary
    public let findings: [GenomicFindingSummary]
    public let title: String
    public let rsids: [String]

    public var variantCount: Int {
        findings.count
    }

    public var rsidSummary: String {
        rsids.joined(separator: ", ")
    }
}

public enum GenomicFindingPresentation {
    public static func badgeLabel(for finding: GenomicFindingSummary) -> String {
        switch normalizedClinicalStatus(finding) {
        case "pharmacogenomic_screening":
            return "用药确认"
        case "requires_confirmation":
            return "待确认"
        default:
            return (finding.riskLevel ?? "info").uppercased()
        }
    }

    public static func boundaryText(for finding: GenomicFindingSummary) -> String? {
        switch normalizedClinicalStatus(finding) {
        case "pharmacogenomic_screening":
            return "PGx result is a medication risk flag; confirm with a clinician or pharmacist before starting, stopping, or changing medication."
        case "requires_confirmation":
            return "DTC genetic data is a screening flag; confirm clinically before disease or carrier-status decisions."
        default:
            return nil
        }
    }

    public static func groups(from findings: [GenomicFindingSummary]) -> [GenomicFindingDisplayGroup] {
        var orderedKeys: [String] = []
        var buckets: [String: [GenomicFindingSummary]] = [:]

        for finding in findings {
            let key = groupKey(for: finding)
            if buckets[key] == nil {
                orderedKeys.append(key)
                buckets[key] = []
            }
            buckets[key]?.append(finding)
        }

        return orderedKeys.compactMap { key in
            guard let bucket = buckets[key], let primary = bucket.first else {
                return nil
            }
            let rsids = bucket
                .compactMap(\.rsid)
                .filter { !$0.isEmpty }
                .uniquedPreservingOrder()
            return GenomicFindingDisplayGroup(
                id: key,
                primary: primary,
                findings: bucket,
                title: primary.displayTitle,
                rsids: rsids
            )
        }
    }

    private static func normalizedClinicalStatus(_ finding: GenomicFindingSummary) -> String {
        let status = (finding.clinicalStatus ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !status.isEmpty { return status }
        if (finding.category ?? "").lowercased() == "drug_sensitivity" {
            return "pharmacogenomic_screening"
        }
        return ""
    }

    private static func groupKey(for finding: GenomicFindingSummary) -> String {
        [
            finding.category ?? "",
            finding.displayTitle,
            finding.resultLabel ?? "",
            finding.riskLevel ?? "",
            finding.evidenceLevel ?? "",
            finding.clinicalStatus ?? "",
            finding.description ?? ""
        ]
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        .joined(separator: "|")
    }
}

private extension Array where Element == String {
    func uniquedPreservingOrder() -> [String] {
        var seen: Set<String> = []
        var result: [String] = []
        for item in self where !seen.contains(item) {
            seen.insert(item)
            result.append(item)
        }
        return result
    }
}
