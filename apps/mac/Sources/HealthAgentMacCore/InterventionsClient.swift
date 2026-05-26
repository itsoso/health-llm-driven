import Foundation

public struct InterventionEvent: Sendable, Equatable, Identifiable, Hashable {
    public enum Kind: String, Sendable {
        case supplement
        case medication
    }

    public let id: String
    public let date: String   // YYYY-MM-DD
    public let label: String
    public let kind: Kind
    public let isActive: Bool

    public init(id: String, date: String, label: String, kind: Kind, isActive: Bool) {
        self.id = id
        self.date = date
        self.label = label
        self.kind = kind
        self.isActive = isActive
    }
}

private struct MedicationDTO: Decodable {
    let id: Int
    let name: String?
    let dosage: String?
    let start_date: String?
    let created_at: String?
    let is_active: Bool?
}

private struct SupplementDefinitionDTO: Decodable {
    let id: Int
    let name: String?
    let dosage: String?
    let created_at: String?
    let is_active: Bool?
}

public final class InterventionsClient: @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// Fetch all interventions (active + retired) and reduce to date-keyed events for timeline overlay.
    public func fetchEvents() async -> [InterventionEvent] {
        async let meds = fetchMedications()
        async let supps = fetchSupplements()
        let all = (await meds) + (await supps)
        return all.sorted { lhs, rhs in
            if lhs.date != rhs.date { return lhs.date < rhs.date }
            return lhs.label < rhs.label
        }
    }

    private func fetchMedications() async -> [InterventionEvent] {
        do {
            let dtos: [MedicationDTO] = try await apiClient.get("medication/medications/me?active_only=false")
            return dtos.compactMap { dto in
                guard let date = Self.preferDate(start: dto.start_date, fallback: dto.created_at) else { return nil }
                let raw = (dto.name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let dose = (dto.dosage ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let label = dose.isEmpty ? raw : "\(raw) (\(dose))"
                return InterventionEvent(
                    id: "med-\(dto.id)",
                    date: date,
                    label: label.isEmpty ? "Medication" : label,
                    kind: .medication,
                    isActive: dto.is_active ?? true
                )
            }
        } catch {
            return []
        }
    }

    private func fetchSupplements() async -> [InterventionEvent] {
        do {
            let dtos: [SupplementDefinitionDTO] = try await apiClient.get("supplements/me/definitions")
            return dtos.compactMap { dto in
                guard let date = Self.preferDate(start: nil, fallback: dto.created_at) else { return nil }
                let raw = (dto.name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let dose = (dto.dosage ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let label = dose.isEmpty ? raw : "\(raw) (\(dose))"
                return InterventionEvent(
                    id: "supp-\(dto.id)",
                    date: date,
                    label: label.isEmpty ? "Supplement" : label,
                    kind: .supplement,
                    isActive: dto.is_active ?? true
                )
            }
        } catch {
            return []
        }
    }

    /// Normalize input dates to "YYYY-MM-DD". Accepts a plain date or a leading ISO datetime.
    static func preferDate(start: String?, fallback: String?) -> String? {
        for candidate in [start, fallback] {
            guard let raw = candidate?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { continue }
            if raw.count >= 10 {
                let prefix = String(raw.prefix(10))
                if prefix.range(of: #"^\d{4}-\d{2}-\d{2}$"#, options: .regularExpression) != nil {
                    return prefix
                }
            }
        }
        return nil
    }
}
