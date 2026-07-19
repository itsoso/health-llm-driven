import Foundation

#if canImport(CoreGraphics) && canImport(ImageIO)
import CoreGraphics
import ImageIO

public struct LocalFoodPhotoLoader: Sendable {
    private let maximumPixelDimension = 1_600

    public init() {}

    public func load(fileURL: URL) throws -> LocalFoodRGBAImage {
        guard fileURL.isFileURL else { throw LocalFoodVisionError.invalidFileURL }
        guard let source = CGImageSourceCreateWithURL(fileURL as CFURL, nil) else {
            throw LocalFoodVisionError.invalidImage
        }
        let options = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: maximumPixelDimension,
            kCGImageSourceShouldCacheImmediately: true,
        ] as CFDictionary
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options) else {
            throw LocalFoodVisionError.invalidImage
        }
        let width = image.width
        let height = image.height
        guard width > 0, height > 0, width <= Int.max / height / 4 else {
            throw LocalFoodVisionError.invalidImage
        }
        var pixels = Data(count: width * height * 4)
        let rendered = pixels.withUnsafeMutableBytes { bytes -> Bool in
            guard let address = bytes.baseAddress,
                  let context = CGContext(
                    data: address,
                    width: width,
                    height: height,
                    bitsPerComponent: 8,
                    bytesPerRow: width * 4,
                    space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGBitmapInfo.byteOrder32Big
                        .union(CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue))
                  ) else { return false }
            context.translateBy(x: 0, y: CGFloat(height))
            context.scaleBy(x: 1, y: -1)
            context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
            return true
        }
        guard rendered else { throw LocalFoodVisionError.invalidImage }
        return LocalFoodRGBAImage(width: width, height: height, orientation: .up, rgba8: pixels)
    }

    public func deleteTemporaryCopyIfOwned(fileURL: URL) throws {
        guard fileURL.isFileURL else { return }
        let candidate = fileURL.standardizedFileURL.resolvingSymlinksInPath()
        var ownedRoots = [FileManager.default.temporaryDirectory]
        if let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first {
            ownedRoots.append(caches)
        }
        let isOwned = ownedRoots.contains { root in
            let rootPath = root.standardizedFileURL.resolvingSymlinksInPath().path
            return candidate.path == rootPath || candidate.path.hasPrefix(rootPath + "/")
        }
        guard isOwned, FileManager.default.fileExists(atPath: candidate.path) else { return }
        try FileManager.default.removeItem(at: candidate)
    }
}
#endif

public struct LocalFoodVisionResourceURLs: Equatable, Sendable {
    public let model: URL
    public let labelBank: URL
}

public enum LocalFoodVisionResourceLocator {
    public static func locate(in bundle: Bundle = .main) throws -> LocalFoodVisionResourceURLs {
        guard let model = bundle.url(
            forResource: "ChineseClipRN50Image",
            withExtension: "mlmodelc"
        ) else {
            throw LocalFoodVisionError.modelMissing
        }
        guard let labelBank = bundle.url(
            forResource: "chinese-clip-label-bank-v2",
            withExtension: "bin"
        ) else {
            throw LocalFoodVisionError.labelBankMissing
        }
        return LocalFoodVisionResourceURLs(model: model, labelBank: labelBank)
    }
}
