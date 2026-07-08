import CryptoKit
import Foundation

public enum FileSourceKind: String, Equatable, Sendable {
    case genomeText = "genome_txt"
    case dedaoFolder = "dedao_folder"
    case appleHealthExport = "apple_health_export"
    /// A document that is almost certainly a lab report / prescription: PDFs land
    /// here and are eligible for medical-exam OCR import.
    case medicalFile = "medical_file"
    /// A plain photo (jpg/png/heic/webp). Could be a food photo, a whiteboard, a
    /// screenshot — anything. It is NOT force-routed to lab-report OCR; it flows to
    /// the agent as a normal chat image so the multimodal/vision path handles it.
    /// An image that genuinely IS a lab report is still importable via the explicit
    /// "import lab report" UI, which accepts `.image` too.
    case image
    case unknown
}

public struct FileIntakeItem: Equatable, Identifiable, Sendable {
    public let url: URL
    public let name: String
    public let sourceKind: FileSourceKind
    public let sha256: String

    public var id: String { sha256 }

    public init(url: URL, name: String, sourceKind: FileSourceKind, sha256: String) {
        self.url = url
        self.name = name
        self.sourceKind = sourceKind
        self.sha256 = sha256
    }
}

public enum FileIntakeService {
    public static func inspect(url: URL) async throws -> FileIntakeItem {
        var isDirectory: ObjCBool = false
        FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)

        let sourceKind = try classify(url: url, isDirectory: isDirectory.boolValue)
        return FileIntakeItem(
            url: url,
            name: url.lastPathComponent,
            sourceKind: sourceKind,
            sha256: try sha256(url: url, isDirectory: isDirectory.boolValue)
        )
    }

    private static func classify(url: URL, isDirectory: Bool) throws -> FileSourceKind {
        let name = url.lastPathComponent.lowercased()
        if isDirectory {
            return name.contains("dedao") ? .dedaoFolder : .unknown
        }

        let ext = url.pathExtension.lowercased()
        if ext == "txt" {
            if name.contains("wegene") || name.contains("23andme") {
                return .genomeText
            }
            let prefix = try String(contentsOf: url, encoding: .utf8).prefix(256).lowercased()
            if prefix.contains("rsid") && prefix.contains("genotype") {
                return .genomeText
            }
        }
        if ["xml", "zip"].contains(ext) {
            return .appleHealthExport
        }
        if ext == "pdf" {
            // A PDF dropped here is almost always a lab report / medical document.
            return .medicalFile
        }
        if ["jpg", "jpeg", "png", "heic", "webp"].contains(ext) {
            // A plain photo — do NOT assume it is a lab report. Route it to the
            // agent's multimodal path; explicit lab-report import can still consume it.
            return .image
        }
        return .unknown
    }

    private static func sha256(url: URL, isDirectory: Bool) throws -> String {
        let data: Data
        if isDirectory {
            data = Data(url.path.utf8)
        } else {
            data = try Data(contentsOf: url)
        }
        let digest = SHA256.hash(data: data)
        return "sha256:" + digest.map { String(format: "%02x", $0) }.joined()
    }
}
