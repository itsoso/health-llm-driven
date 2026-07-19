import SwiftUI
import UIKit

@main
struct LocalFoodVisionBenchmarkHostApp: App {
    private static let enableMarker = "LOCAL_FOOD_VISION_BENCHMARK=1"
    @State private var status = "Preparing authorized local benchmark…"

    var body: some Scene {
        WindowGroup {
            ScrollView {
                Text(status)
                    .font(.system(.body, design: .monospaced))
                    .padding()
            }
            .task { await runBenchmark() }
        }
    }

    @MainActor
    private func runBenchmark() async {
        _ = Self.enableMarker
        guard LocalFoodVisionBenchmarkConfig.evidenceCollectionEnabled else {
            status = "Compile-only host. Evidence collection is disabled."
            return
        }
        guard let calibrationManifestSHA256 =
            LocalFoodVisionBenchmarkConfig.calibrationManifestSHA256 else {
            status = "Benchmark configuration is missing calibration provenance."
            return
        }
        do {
            let manifest = try loadManifest()
            let modelURL = try bundledModelURL()
            let labelBankURL = try bundledLabelBankURL()
            let provenance = LocalFoodVisionProvenance(
                modelArtifactSHA256: LocalFoodVisionBenchmarkConfig.modelArtifactSHA256,
                labelBankVersion: LocalFoodVisionBenchmarkConfig.labelBankVersion,
                calibrationVersion: LocalFoodVisionBenchmarkConfig.calibrationVersion,
                precisionVariant: LocalFoodVisionBenchmarkConfig.precisionVariant
            )
            let engine = LocalChineseClipVisionEngine(
                modelURL: modelURL,
                labelBankURL: labelBankURL,
                provenance: provenance,
                rankingPolicy: .init(
                    minimumScore: LocalFoodVisionBenchmarkConfig.minimumScore,
                    minimumMargin: LocalFoodVisionBenchmarkConfig.minimumMargin,
                    maximumCandidates: LocalFoodVisionBenchmarkConfig.maximumCandidates
                ),
                proposer: LocalFoodVisionSaliencyProposer(),
                preprocessor: LocalFoodVisionPreprocessor(),
                modelLoader: LocalChineseClipCoreMLModelLoader(),
                labelLoader: LocalChineseClipLabelBankLoader(),
                runtimeGuard: LocalFoodProcessRuntimeGuard()
            )
            let cases = try manifest.cases.filter { $0.split == "test" }.map { fixture in
                LocalFoodVisionBenchmarkCase(
                    caseID: fixture.caseId,
                    fixtureRef: fixture.fixtureId,
                    request: .init(image: try loadImage(named: fixture.file)),
                    expectedFoodIdentities: fixture.expectedFoodIdentities,
                    allowedAliases: fixture.allowedAliases,
                    nonFood: fixture.nonFood
                )
            }
            let capabilities = LocalHealthCapabilityProbe.currentProfile()
            let benchmark = LocalFoodVisionBenchmark(
                runID: "local-food-vision-\(UUID().uuidString.lowercased())",
                recordedAt: ISO8601DateFormatter().string(from: Date()),
                dataset: .init(
                    name: LocalFoodVisionBenchmarkConfig.datasetName,
                    version: manifest.datasetVersion,
                    licenseStatus: try license(LocalFoodVisionBenchmarkConfig.datasetLicenseStatus),
                    containsPrivateUserData: manifest.containsPrivateUserData
                ),
                device: .init(
                    hardwareIdentifier: hardwareIdentifier(),
                    deviceClass: "phone",
                    osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
                    isSimulator: capabilities.isSimulator,
                    appBuild: appBuild()
                ),
                capabilities: capabilities,
                modelProfile: .init(
                    engine: "custom_core_ml",
                    identifier: "OFA-Sys/chinese-clip-rn50-image-tower",
                    version: LocalFoodVisionBenchmarkConfig.modelRevision,
                    downloadBytes: LocalFoodVisionBenchmarkConfig.sourceModelBytes
                        + LocalFoodVisionBenchmarkConfig.sourceLabelBankBytes,
                    modelArtifactSha256: LocalFoodVisionBenchmarkConfig.modelArtifactSHA256,
                    labelBankVersion: LocalFoodVisionBenchmarkConfig.labelBankVersion,
                    calibrationVersion: LocalFoodVisionBenchmarkConfig.calibrationVersion,
                    calibrationManifestSha256: calibrationManifestSHA256,
                    minimumScore: LocalFoodVisionBenchmarkConfig.minimumScore,
                    minimumMargin: LocalFoodVisionBenchmarkConfig.minimumMargin,
                    maximumCandidates: LocalFoodVisionBenchmarkConfig.maximumCandidates,
                    installedModelBytes: installedBytes(at: modelURL),
                    installedLabelBankBytes: installedBytes(at: labelBankURL),
                    precisionVariant: LocalFoodVisionBenchmarkConfig.precisionVariant
                ),
                cases: cases,
                warmRunCount: 9,
                engine: engine,
                clock: LocalDietUptimeClock(),
                systemMetrics: LocalDietProcessSystemMetrics(),
                memorySampler: LocalDietPollingPeakMemorySampler()
            )
            let report = try await benchmark.run()
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let data = try encoder.encode(report)
            let json = String(decoding: data, as: UTF8.self)
            print("LOCAL_FOOD_VISION_BENCHMARK=\(json)")
            status = "Completed \(report.caseResults.count) authorized cases."
        } catch {
            let errorType = String(reflecting: type(of: error))
            print("LOCAL_FOOD_VISION_BENCHMARK_ERROR=\(errorType)")
            status = "Benchmark failed: \(errorType)"
        }
    }

    private func loadManifest() throws -> FixtureManifest {
        guard let url = Bundle.main.url(
            forResource: "dataset-manifest",
            withExtension: "json"
        ) else {
            throw HostError.missingManifest
        }
        return try JSONDecoder().decode(FixtureManifest.self, from: Data(contentsOf: url))
    }

    private func bundledModelURL() throws -> URL {
        let name = LocalFoodVisionBenchmarkConfig.modelBaseName
        if let compiled = Bundle.main.url(forResource: name, withExtension: "mlmodelc") {
            return compiled
        }
        if let package = Bundle.main.url(forResource: name, withExtension: "mlpackage") {
            return package
        }
        throw HostError.missingModel
    }

    private func bundledLabelBankURL() throws -> URL {
        guard let url = Bundle.main.url(
            forResource: LocalFoodVisionBenchmarkConfig.labelBankBaseName,
            withExtension: "bin"
        ) else {
            throw HostError.missingLabelBank
        }
        return url
    }

    private func loadImage(named name: String) throws -> LocalFoodRGBAImage {
        let path = name as NSString
        guard let url = Bundle.main.url(
            forResource: path.deletingPathExtension,
            withExtension: path.pathExtension
        ), let image = UIImage(data: try Data(contentsOf: url)),
              let cgImage = image.cgImage else {
            throw HostError.invalidFixture
        }
        var pixels = Data(count: cgImage.width * cgImage.height * 4)
        let rendered = pixels.withUnsafeMutableBytes { bytes -> Bool in
            guard let context = CGContext(
                data: bytes.baseAddress,
                width: cgImage.width,
                height: cgImage.height,
                bitsPerComponent: 8,
                bytesPerRow: cgImage.width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return false }
            context.draw(cgImage, in: CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height))
            return true
        }
        guard rendered else { throw HostError.invalidFixture }
        return LocalFoodRGBAImage(
            width: cgImage.width,
            height: cgImage.height,
            orientation: LocalFoodImageOrientation(uiImageOrientation: image.imageOrientation),
            rgba8: pixels
        )
    }

    private func installedBytes(at url: URL) -> Int {
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .fileSizeKey]
        guard let enumerator = FileManager.default.enumerator(
            at: url,
            includingPropertiesForKeys: Array(keys)
        ) else {
            return (try? url.resourceValues(forKeys: keys).fileSize) ?? 0
        }
        var total = 0
        for case let item as URL in enumerator {
            let values = try? item.resourceValues(forKeys: keys)
            if values?.isRegularFile == true { total += values?.fileSize ?? 0 }
        }
        return total
    }

    private func license(_ rawValue: String) throws -> LocalFoodVisionDatasetLicense {
        guard let value = LocalFoodVisionDatasetLicense(rawValue: rawValue) else {
            throw HostError.invalidManifest
        }
        return value
    }

    private func hardwareIdentifier() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let machineSize = MemoryLayout.size(ofValue: systemInfo.machine)
        return withUnsafePointer(to: &systemInfo.machine) { pointer in
            pointer.withMemoryRebound(
                to: CChar.self,
                capacity: machineSize
            ) {
                String(cString: $0)
            }
        }
    }

    private func appBuild() -> String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "g2-spike"
    }
}

private struct FixtureManifest: Decodable {
    let schemaVersion: Int
    let datasetVersion: String
    let containsPrivateUserData: Bool
    let cases: [FixtureCase]
}

private struct FixtureCase: Decodable {
    let caseId: String
    let fixtureId: String
    let file: String
    let split: String
    let stratum: String
    let licenseStatus: String
    let expectedFoodIdentities: [String]
    let allowedAliases: [String: [String]]
    let nonFood: Bool
}

private enum HostError: Error {
    case missingManifest
    case missingModel
    case missingLabelBank
    case invalidManifest
    case invalidFixture
}

private extension LocalFoodImageOrientation {
    init(uiImageOrientation: UIImage.Orientation) {
        switch uiImageOrientation {
        case .up: self = .up
        case .upMirrored: self = .upMirrored
        case .down: self = .down
        case .downMirrored: self = .downMirrored
        case .left: self = .left
        case .leftMirrored: self = .leftMirrored
        case .right: self = .right
        case .rightMirrored: self = .rightMirrored
        @unknown default: self = .up
        }
    }
}
