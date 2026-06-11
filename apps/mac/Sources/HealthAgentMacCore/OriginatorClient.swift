import Foundation

// MARK: - Originator (原研药) models
//
// 消费后端 /prescriptions/* 端点 (Phase 1 见 PR #113)。所有字段都按后端契约
// 可空解码:后端字段缺失 / 为 null 时绝不让整条记录解码失败,也绝不臆造数据 ——
// 没有原研数据就如实显示「暂无」。

/// 一种原研药 (品牌 + 厂家)。对应后端响应里的 `originator` 子对象。
public struct OriginatorDrug: Codable, Equatable, Sendable {
    public let generic: String
    public let brand: String
    public let manufacturer: String

    public init(generic: String, brand: String, manufacturer: String) {
        self.generic = generic
        self.brand = brand
        self.manufacturer = manufacturer
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.generic = try container.decodeIfPresent(String.self, forKey: .generic) ?? ""
        self.brand = try container.decodeIfPresent(String.self, forKey: .brand) ?? ""
        self.manufacturer = try container.decodeIfPresent(String.self, forKey: .manufacturer) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case generic
        case brand
        case manufacturer
    }
}

/// 处方识别出的一条药。`originator` 可能为 null (无原研收录),`hasOriginator`
/// 是后端给的权威布尔 —— UI 以它为准决定是否显示原研块。
public struct PrescriptionItem: Codable, Equatable, Sendable, Identifiable {
    public let rawName: String?
    public let genericName: String?
    public let dosage: String?
    public let frequency: String?
    public let originator: OriginatorDrug?
    public let hasOriginator: Bool

    /// 没有稳定服务端 id;用内容拼一个用于 SwiftUI ForEach。
    public let id: String

    public init(
        rawName: String? = nil,
        genericName: String? = nil,
        dosage: String? = nil,
        frequency: String? = nil,
        originator: OriginatorDrug? = nil,
        hasOriginator: Bool = false
    ) {
        self.rawName = rawName
        self.genericName = genericName
        self.dosage = dosage
        self.frequency = frequency
        self.originator = originator
        self.hasOriginator = hasOriginator
        self.id = Self.makeID(rawName: rawName, genericName: genericName, dosage: dosage)
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.rawName = try container.decodeIfPresent(String.self, forKey: .rawName)
        self.genericName = try container.decodeIfPresent(String.self, forKey: .genericName)
        self.dosage = try container.decodeIfPresent(String.self, forKey: .dosage)
        self.frequency = try container.decodeIfPresent(String.self, forKey: .frequency)
        self.originator = try container.decodeIfPresent(OriginatorDrug.self, forKey: .originator)
        self.hasOriginator = try container.decodeIfPresent(Bool.self, forKey: .hasOriginator) ?? false
        self.id = Self.makeID(rawName: rawName, genericName: genericName, dosage: dosage)
    }

    private static func makeID(rawName: String?, genericName: String?, dosage: String?) -> String {
        let parts = [rawName, genericName, dosage].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? UUID().uuidString : parts.joined(separator: "|")
    }

    /// 给人看的主名:优先原始处方名,退回通用名,都没有显示占位。
    public var displayName: String {
        if let rawName, !rawName.isEmpty { return rawName }
        if let genericName, !genericName.isEmpty { return genericName }
        return ""
    }

    enum CodingKeys: String, CodingKey {
        case rawName = "raw_name"
        case genericName = "generic_name"
        case dosage
        case frequency
        case originator
        case hasOriginator = "has_originator"
    }
}

/// 对应 `POST /prescriptions/recognize` 整体响应。
public struct PrescriptionRecognizeResponse: Codable, Equatable, Sendable {
    public let items: [PrescriptionItem]
    public let matchedOriginators: Int
    public let note: String?

    public init(items: [PrescriptionItem] = [], matchedOriginators: Int = 0, note: String? = nil) {
        self.items = items
        self.matchedOriginators = matchedOriginators
        self.note = note
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.items = try container.decodeIfPresent([PrescriptionItem].self, forKey: .items) ?? []
        self.matchedOriginators = try container.decodeIfPresent(Int.self, forKey: .matchedOriginators) ?? 0
        self.note = try container.decodeIfPresent(String.self, forKey: .note)
    }

    enum CodingKeys: String, CodingKey {
        case items
        case matchedOriginators = "matched_originators"
        case note
    }
}

/// 一条原研药换药建议 (对应 `recommendations[]` 单条)。
public struct OriginatorRecommendation: Codable, Equatable, Sendable, Identifiable {
    public let medName: String
    public let genericName: String
    public let genericKey: String
    public let brand: String
    public let manufacturer: String

    /// `generic_key` 在一个用户的建议列表里唯一 —— 用作稳定 id。
    public var id: String { genericKey.isEmpty ? genericName : genericKey }

    public init(
        medName: String,
        genericName: String,
        genericKey: String,
        brand: String,
        manufacturer: String
    ) {
        self.medName = medName
        self.genericName = genericName
        self.genericKey = genericKey
        self.brand = brand
        self.manufacturer = manufacturer
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.medName = try container.decodeIfPresent(String.self, forKey: .medName) ?? ""
        self.genericName = try container.decodeIfPresent(String.self, forKey: .genericName) ?? ""
        self.genericKey = try container.decodeIfPresent(String.self, forKey: .genericKey) ?? ""
        self.brand = try container.decodeIfPresent(String.self, forKey: .brand) ?? ""
        self.manufacturer = try container.decodeIfPresent(String.self, forKey: .manufacturer) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case medName = "med_name"
        case genericName = "generic_name"
        case genericKey = "generic_key"
        case brand
        case manufacturer
    }
}

/// 对应 `GET /prescriptions/recommendations` 整体响应。
public struct OriginatorRecommendationsResponse: Codable, Equatable, Sendable {
    public let recommendations: [OriginatorRecommendation]

    public init(recommendations: [OriginatorRecommendation] = []) {
        self.recommendations = recommendations
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.recommendations = try container.decodeIfPresent(
            [OriginatorRecommendation].self, forKey: .recommendations
        ) ?? []
    }

    enum CodingKeys: String, CodingKey {
        case recommendations
    }
}

/// 建议状态。`adopted` = 采纳系统推荐;`dismissed` = 不需要;两者都抑制后续推荐。
public enum OriginatorRecommendationStatus: String, Codable, Equatable, Sendable {
    case suggested
    case adopted
    case dismissed
}

/// `POST /prescriptions/recommendations/status` 请求体。
public struct OriginatorStatusRequest: Codable, Equatable, Sendable {
    public let genericName: String
    public let status: OriginatorRecommendationStatus
    public let brand: String?
    public let manufacturer: String?

    public init(
        genericName: String,
        status: OriginatorRecommendationStatus,
        brand: String? = nil,
        manufacturer: String? = nil
    ) {
        self.genericName = genericName
        self.status = status
        self.brand = brand
        self.manufacturer = manufacturer
    }

    enum CodingKeys: String, CodingKey {
        case genericName = "generic_name"
        case status
        case brand
        case manufacturer
    }
}

/// `POST /prescriptions/recommendations/status` 响应。
public struct OriginatorStatusResponse: Codable, Equatable, Sendable {
    public let genericName: String
    public let status: String

    public init(genericName: String, status: String) {
        self.genericName = genericName
        self.status = status
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.genericName = try container.decodeIfPresent(String.self, forKey: .genericName) ?? ""
        self.status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case genericName = "generic_name"
        case status
    }
}

/// `GET /prescriptions/originator?name=X` 响应 (按名直查,本期 UI 暂未直接用,
/// 但封装齐全便于后续「手动查一种药」入口)。
public struct OriginatorLookupResponse: Codable, Equatable, Sendable {
    public let query: String
    public let originator: OriginatorDrug?
    public let hasOriginator: Bool

    public init(query: String, originator: OriginatorDrug? = nil, hasOriginator: Bool = false) {
        self.query = query
        self.originator = originator
        self.hasOriginator = hasOriginator
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.query = try container.decodeIfPresent(String.self, forKey: .query) ?? ""
        self.originator = try container.decodeIfPresent(OriginatorDrug.self, forKey: .originator)
        self.hasOriginator = try container.decodeIfPresent(Bool.self, forKey: .hasOriginator) ?? false
    }

    enum CodingKeys: String, CodingKey {
        case query
        case originator
        case hasOriginator = "has_originator"
    }
}

// MARK: - MIME helper (pure, testable)

/// 把图片文件扩展名映射成 multipart 上传用的 MIME 类型。后端只收
/// jpg/png/heic/webp;未知扩展名退回 `application/octet-stream`,让后端去拒绝
/// 而不是客户端臆测。
public enum PrescriptionImageMime {
    public static func mimeType(forExtension ext: String) -> String {
        switch ext.lowercased() {
        case "jpg", "jpeg": return "image/jpeg"
        case "png": return "image/png"
        case "heic": return "image/heic"
        case "webp": return "image/webp"
        default: return "application/octet-stream"
        }
    }

    /// 后端接受的处方图片扩展名 (NSOpenPanel allowedContentTypes 用)。
    public static let allowedExtensions: [String] = ["jpg", "jpeg", "png", "heic", "webp"]
}

// MARK: - Client

/// 处方查原研药 + 原研药推荐。对标 `DeviceSourcesClient`:主路径失败抛错让 UI
/// 显示错误态;建议列表也走抛错路径 (有错要让用户知道,而不是默默空白)。
public final class OriginatorClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// 上传处方图片识别 + 匹配原研药。失败抛错 (UI 显示错误态)。
    public func recognize(imageData: Data, fileName: String) async throws -> PrescriptionRecognizeResponse {
        let ext = (fileName as NSString).pathExtension
        let mime = PrescriptionImageMime.mimeType(forExtension: ext)
        return try await apiClient.uploadFile(
            "prescriptions/recognize",
            fileData: imageData,
            fileName: fileName,
            fieldName: "file",
            mimeType: mime
        )
    }

    /// 拉可换原研的在用药建议 (已采纳/忽略的后端不返回)。
    public func fetchRecommendations() async throws -> OriginatorRecommendationsResponse {
        try await apiClient.get("prescriptions/recommendations")
    }

    /// 设置某条建议的状态 (采纳 / 不需要 / 重新标记建议)。
    public func setStatus(
        genericName: String,
        status: OriginatorRecommendationStatus,
        brand: String? = nil,
        manufacturer: String? = nil
    ) async throws -> OriginatorStatusResponse {
        let body = OriginatorStatusRequest(
            genericName: genericName,
            status: status,
            brand: brand,
            manufacturer: manufacturer
        )
        return try await apiClient.post("prescriptions/recommendations/status", body: body)
    }

    /// 按药名直查原研药。
    public func lookupOriginator(name: String) async throws -> OriginatorLookupResponse {
        let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? name
        return try await apiClient.get("prescriptions/originator?name=\(encoded)")
    }
}
