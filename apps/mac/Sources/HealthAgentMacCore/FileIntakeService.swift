import CryptoKit
import Foundation

public enum FileSourceKind: String, Equatable, Sendable {
    case genomeText = "genome_txt"
    case dedaoFolder = "dedao_folder"
    case appleHealthExport = "apple_health_export"
    case medicalFile = "medical_file"
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
        if ["pdf", "jpg", "jpeg", "png", "heic", "webp"].contains(ext) {
            return .medicalFile
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
