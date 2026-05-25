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

    private static func groupKey(for finding: GenomicFindingSummary) -> String {
        [
            finding.category ?? "",
            finding.displayTitle,
            finding.resultLabel ?? "",
            finding.riskLevel ?? "",
            finding.evidenceLevel ?? "",
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
