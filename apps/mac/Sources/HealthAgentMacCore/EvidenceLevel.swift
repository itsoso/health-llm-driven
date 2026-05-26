import Foundation

/// 4-tier evidence taxonomy used by Action Cards and surfaced on agent
/// answers so users can tell apart curated guidelines from theoretical
/// associations.
///
/// Source of truth: `backend/app/models/action_card.py` (2026-05-12).
public enum EvidenceLevel: String, CaseIterable, Sendable {
    case high            // CPIC / Garmin 实测 / 强共识
    case medium          // 单临床 / 关联性
    case low             // 理论假设 / 弱证据
    case medicalGrade    // 高风险, 需医生介入

    public var displayLabel: String {
        switch self {
        case .high: "Evidence: High"
        case .medium: "Evidence: Medium"
        case .low: "Evidence: Low"
        case .medicalGrade: "Evidence: Medical"
        }
    }

    public var systemImage: String {
        switch self {
        case .high: "checkmark.seal.fill"
        case .medium: "checkmark.circle"
        case .low: "questionmark.circle"
        case .medicalGrade: "cross.case.fill"
        }
    }

    /// Best-effort classification for the free-form source labels the
    /// agent emits on the SSE `done` event. Falls back to `.low` for
    /// anything we don't recognize so we never silently drop a chip.
    public static func classify(sourceLabel raw: String) -> EvidenceLevel {
        let s = raw.lowercased()

        // Medical-grade: drug exposure, prescription, dosage adjustments.
        if s.contains("药物") || s.contains("用药") || s.contains("处方")
            || s.contains("medication") || s.contains("drug") || s.contains("prescription") {
            return .medicalGrade
        }

        // High: measured user data, validated wearables, lab readings,
        // CPIC / guideline-grade knowledge.
        if s.contains("garmin") || s.contains("化验") || s.contains("lab")
            || s.contains("cgm") || s.contains("血氧") || s.contains("基因")
            || s.contains("genome") || s.contains("dna")
            || s.contains("cpic") || s.contains("guideline") || s.contains("系统知识库") {
            return .high
        }

        // Medium: curated secondary literature, intervention history.
        if s.contains("得到") || s.contains("dedao") || s.contains("wiki")
            || s.contains("pubmed") || s.contains("actioncard") || s.contains("action_card")
            || s.contains("干预") {
            return .medium
        }

        return .low
    }
}
