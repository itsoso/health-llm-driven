import Foundation

public final class SystemLocalHealthVaultFiles: LocalHealthVaultFileClient,
    @unchecked Sendable {
    public let rootDirectory: URL
    public let databaseURL: URL
    public let exportDirectory: URL
    private let fileManager: FileManager
    private let sentinelURL: URL

    public init(fileManager: FileManager = .default) throws {
        self.fileManager = fileManager
        let applicationSupport = try fileManager.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        )
        rootDirectory = applicationSupport.appendingPathComponent(
            "LocalHealthKernel",
            isDirectory: true
        )
        databaseURL = rootDirectory.appendingPathComponent("vault.sqlite")
        exportDirectory = rootDirectory.appendingPathComponent(
            "Exports",
            isDirectory: true
        )
        sentinelURL = rootDirectory.appendingPathComponent(".install-sentinel")
    }

    public var installSentinelExists: Bool {
        fileManager.fileExists(atPath: sentinelURL.path)
    }

    public var vaultArtifactsExist: Bool {
        let databaseArtifacts = [
            databaseURL,
            URL(fileURLWithPath: databaseURL.path + "-wal"),
            URL(fileURLWithPath: databaseURL.path + "-shm"),
        ]
        if databaseArtifacts.contains(where: {
            fileManager.fileExists(atPath: $0.path)
        }) {
            return true
        }
        guard let exportFiles = try? fileManager.contentsOfDirectory(
            at: exportDirectory,
            includingPropertiesForKeys: nil
        ) else {
            return false
        }
        return !exportFiles.isEmpty
    }

    public func createInstallSentinel() throws {
        try createProtectedDirectory(rootDirectory)
        if !installSentinelExists {
            try Data().write(to: sentinelURL, options: [.atomic])
        }
        try applyCompleteProtection(to: sentinelURL)
    }

    public func deleteVaultArtifacts() throws {
        for url in [
            databaseURL,
            URL(fileURLWithPath: databaseURL.path + "-wal"),
            URL(fileURLWithPath: databaseURL.path + "-shm"),
            exportDirectory,
        ] where fileManager.fileExists(atPath: url.path) {
            try fileManager.removeItem(at: url)
        }
    }

    public func prepareDirectories() throws {
        try createProtectedDirectory(rootDirectory)
        try createProtectedDirectory(exportDirectory)
    }

    private func createProtectedDirectory(_ url: URL) throws {
        try fileManager.createDirectory(
            at: url,
            withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.complete]
        )
        try applyCompleteProtection(to: url)
    }

    private func applyCompleteProtection(to url: URL) throws {
        #if os(iOS)
        try fileManager.setAttributes(
            [.protectionKey: FileProtectionType.complete],
            ofItemAtPath: url.path
        )
        #endif
    }
}
