import Foundation

public struct SupplementProductListResponse: Decodable, Equatable, Sendable {
    public let items: [SupplementProductSummary]
    public let total: Int
}

public struct SupplementProductSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let name: String
    public let brand: String
    public let category: String?
    public let description: String?
    public let servingSize: String?
    public let priceCny: Double?
    public let rating: Double?
    public let healthTags: [String]

    public var displayName: String {
        [brand, name]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case brand
        case category
        case description
        case servingSize = "serving_size"
        case priceCny = "price_cny"
        case rating
        case healthTags = "health_tags"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(Int.self, forKey: .id)
        self.name = try container.decode(String.self, forKey: .name)
        self.brand = try container.decode(String.self, forKey: .brand)
        self.category = try container.decodeIfPresent(String.self, forKey: .category)
        self.description = try container.decodeIfPresent(String.self, forKey: .description)
        self.servingSize = try container.decodeIfPresent(String.self, forKey: .servingSize)
        self.priceCny = try Self.decodeFlexibleDouble(container, key: .priceCny)
        self.rating = try Self.decodeFlexibleDouble(container, key: .rating)
        self.healthTags = try container.decodeIfPresent([String].self, forKey: .healthTags) ?? []
    }

    private static func decodeFlexibleDouble(
        _ container: KeyedDecodingContainer<CodingKeys>,
        key: CodingKeys
    ) throws -> Double? {
        if let double = try container.decodeIfPresent(Double.self, forKey: key) {
            return double
        }
        if let string = try container.decodeIfPresent(String.self, forKey: key) {
            return Double(string)
        }
        return nil
    }
}

public final class SupplementProductLibraryClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func searchProducts(query: String, limit: Int = 10) async throws -> SupplementProductListResponse {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        let encodedQuery = trimmed.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? trimmed
        return try await apiClient.get("supplements/products?search=\(encodedQuery)&limit=\(limit)")
    }
}
