import Foundation

public protocol LabUploadServicing: Sendable {
    func importReport(fileURL: URL) async throws -> LabUploadResult
}

public struct LabUploadResult: Decodable, Equatable, Sendable {
    public let message: String
    public let examID: Int
    public let examDate: String?
    public let examType: String?
    public let hospitalName: String?
    public let itemsCount: Int?
    public let abnormalCount: Int?
    public let conclusionsCount: Int?
    public let conclusion: String?

    public init(
        message: String,
        examID: Int,
        examDate: String? = nil,
        examType: String? = nil,
        hospitalName: String? = nil,
        itemsCount: Int? = nil,
        abnormalCount: Int? = nil,
        conclusionsCount: Int? = nil,
        conclusion: String? = nil
    ) {
        self.message = message
        self.examID = examID
        self.examDate = examDate
        self.examType = examType
        self.hospitalName = hospitalName
        self.itemsCount = itemsCount
        self.abnormalCount = abnormalCount
        self.conclusionsCount = conclusionsCount
        self.conclusion = conclusion
    }

    private enum CodingKeys: String, CodingKey {
        case message
        case examID = "exam_id"
        case examDate = "exam_date"
        case examType = "exam_type"
        case hospitalName = "hospital_name"
        case itemsCount = "items_count"
        case abnormalCount = "abnormal_count"
        case conclusionsCount = "conclusions_count"
        case conclusion
    }
}

public enum LabReportUploadMime {
    public static func mimeType(forExtension fileExtension: String) -> String {
        switch normalized(fileExtension) {
        case "pdf":
            return "application/pdf"
        case "jpg", "jpeg":
            return "image/jpeg"
        case "png":
            return "image/png"
        case "heic":
            return "image/heic"
        case "webp":
            return "image/webp"
        default:
            return "application/octet-stream"
        }
    }

    public static func isSupported(forExtension fileExtension: String) -> Bool {
        endpointPath(forExtension: fileExtension) != nil
    }

    static func endpointPath(forExtension fileExtension: String) -> String? {
        switch normalized(fileExtension) {
        case "pdf":
            return "medical-exams/import/pdf"
        case "jpg", "jpeg", "png", "heic", "webp":
            return "medical-exams/import/image"
        default:
            return nil
        }
    }

    private static func normalized(_ fileExtension: String) -> String {
        fileExtension.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
    }
}

public enum LabUploadError: LocalizedError, Equatable {
    case unsupportedFileType(String)

    public var errorDescription: String? {
        switch self {
        case .unsupportedFileType(let fileExtension):
            let label = fileExtension.isEmpty ? "unknown" : fileExtension
            return "不支持的化验文件类型：\(label)。请上传 PDF、JPG、PNG、HEIC 或 WebP。"
        }
    }
}

public final class LabUploadClient: LabUploadServicing, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func importReport(fileURL: URL) async throws -> LabUploadResult {
        let fileExtension = fileURL.pathExtension
        guard let endpointPath = LabReportUploadMime.endpointPath(forExtension: fileExtension) else {
            throw LabUploadError.unsupportedFileType(fileExtension)
        }
        let data = try Data(contentsOf: fileURL)
        return try await apiClient.uploadFile(
            endpointPath,
            fileData: data,
            fileName: fileURL.lastPathComponent,
            fieldName: "file",
            mimeType: LabReportUploadMime.mimeType(forExtension: fileExtension)
        )
    }
}
