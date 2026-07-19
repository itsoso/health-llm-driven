import Foundation

public enum LocalFoodImageOrientation: Int, Codable, Equatable, Sendable {
    case up = 1
    case upMirrored = 2
    case down = 3
    case downMirrored = 4
    case leftMirrored = 5
    case right = 6
    case rightMirrored = 7
    case left = 8
}

public struct LocalFoodRGBAImage: Equatable, Sendable {
    public let width: Int
    public let height: Int
    public let orientation: LocalFoodImageOrientation
    public let rgba8: Data

    public init(
        width: Int,
        height: Int,
        orientation: LocalFoodImageOrientation,
        rgba8: Data
    ) {
        self.width = width
        self.height = height
        self.orientation = orientation
        self.rgba8 = rgba8
    }
}

public struct LocalFoodRegionProposal: Codable, Equatable, Sendable {
    public let x: Double
    public let y: Double
    public let width: Double
    public let height: Double
    public let confidence: Double

    public init(x: Double, y: Double, width: Double, height: Double, confidence: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.confidence = confidence
    }
}

public struct LocalFoodPreparedRegion: Equatable, Sendable {
    public let evidence: LocalFoodEvidence
    public let regionIndex: Int?
    public let tensor: [Float]

    public init(evidence: LocalFoodEvidence, regionIndex: Int?, tensor: [Float]) {
        self.evidence = evidence
        self.regionIndex = regionIndex
        self.tensor = tensor
    }
}

public protocol LocalFoodVisionPreprocessing: Sendable {
    func prepare(
        image: LocalFoodRGBAImage,
        proposals: [LocalFoodRegionProposal]
    ) throws -> [LocalFoodPreparedRegion]
}

public struct LocalFoodVisionPreprocessor: LocalFoodVisionPreprocessing, Sendable {
    public static let imageSize = 224

    private static let mean: [Float] = [0.48145466, 0.4578275, 0.40821073]
    private static let standardDeviation: [Float] = [0.26862954, 0.26130258, 0.27577711]

    public init() {}

    public func prepare(
        image: LocalFoodRGBAImage,
        proposals: [LocalFoodRegionProposal]
    ) throws -> [LocalFoodPreparedRegion] {
        try validate(image)
        let selected = selectValidRegions(proposals)
        var regions = [
            LocalFoodPreparedRegion(
                evidence: .wholeImage,
                regionIndex: nil,
                tensor: makeTensor(image: image, box: .fullImage)
            )
        ]
        regions.append(contentsOf: selected.enumerated().map { index, box in
            LocalFoodPreparedRegion(
                evidence: .salientRegion,
                regionIndex: index,
                tensor: makeTensor(image: image, box: box)
            )
        })
        return regions
    }

    private func validate(_ image: LocalFoodRGBAImage) throws {
        guard image.width > 0, image.height > 0,
              image.width <= Int.max / image.height / 4,
              image.rgba8.count == image.width * image.height * 4 else {
            throw LocalFoodVisionError.invalidImage
        }
    }

    private func selectValidRegions(_ proposals: [LocalFoodRegionProposal]) -> [Box] {
        let sorted = proposals.enumerated().sorted { lhs, rhs in
            if lhs.element.confidence != rhs.element.confidence {
                return lhs.element.confidence > rhs.element.confidence
            }
            return lhs.offset < rhs.offset
        }
        var accepted: [Box] = []
        for item in sorted {
            guard accepted.count < 3,
                  let box = Box(clamping: item.element),
                  box.area >= 0.01,
                  accepted.allSatisfy({ $0.intersectionOverUnion(with: box) < 0.8 }) else {
                continue
            }
            accepted.append(box)
        }
        return accepted
    }

    private func makeTensor(image: LocalFoodRGBAImage, box: Box) -> [Float] {
        let size = Self.imageSize
        let planeSize = size * size
        var tensor = [Float](repeating: 0, count: 3 * planeSize)
        let oriented = orientedSize(image)

        image.rgba8.withUnsafeBytes { rawBytes in
            let pixels = rawBytes.bindMemory(to: UInt8.self)
            for outputY in 0..<size {
                let unitY = (Double(outputY) + 0.5) / Double(size)
                let orientedY = min(
                    oriented.height - 1,
                    Int((box.y + unitY * box.height) * Double(oriented.height))
                )
                for outputX in 0..<size {
                    let unitX = (Double(outputX) + 0.5) / Double(size)
                    let orientedX = min(
                        oriented.width - 1,
                        Int((box.x + unitX * box.width) * Double(oriented.width))
                    )
                    let source = sourceCoordinate(
                        orientedX: orientedX,
                        orientedY: orientedY,
                        image: image
                    )
                    let sourceOffset = (source.y * image.width + source.x) * 4
                    let outputOffset = outputY * size + outputX
                    for channel in 0..<3 {
                        let unitValue = Float(pixels[sourceOffset + channel]) / 255
                        tensor[channel * planeSize + outputOffset] =
                            (unitValue - Self.mean[channel]) / Self.standardDeviation[channel]
                    }
                }
            }
        }
        return tensor
    }

    private func orientedSize(_ image: LocalFoodRGBAImage) -> (width: Int, height: Int) {
        switch image.orientation {
        case .leftMirrored, .right, .rightMirrored, .left:
            return (image.height, image.width)
        default:
            return (image.width, image.height)
        }
    }

    private func sourceCoordinate(
        orientedX x: Int,
        orientedY y: Int,
        image: LocalFoodRGBAImage
    ) -> (x: Int, y: Int) {
        switch image.orientation {
        case .up:
            return (x, y)
        case .upMirrored:
            return (image.width - 1 - x, y)
        case .down:
            return (image.width - 1 - x, image.height - 1 - y)
        case .downMirrored:
            return (x, image.height - 1 - y)
        case .leftMirrored:
            return (y, x)
        case .right:
            return (y, image.height - 1 - x)
        case .rightMirrored:
            return (image.width - 1 - y, image.height - 1 - x)
        case .left:
            return (image.width - 1 - y, x)
        }
    }
}

private struct Box: Equatable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double

    static let fullImage = Box(x: 0, y: 0, width: 1, height: 1)

    init(x: Double, y: Double, width: Double, height: Double) {
        self.x = x
        self.y = y
        self.width = width
        self.height = height
    }

    init?(clamping proposal: LocalFoodRegionProposal) {
        guard proposal.x.isFinite, proposal.y.isFinite,
              proposal.width.isFinite, proposal.height.isFinite,
              proposal.confidence.isFinite, proposal.confidence >= 0,
              proposal.width > 0, proposal.height > 0 else {
            return nil
        }
        let left = min(1, max(0, proposal.x))
        let top = min(1, max(0, proposal.y))
        let right = min(1, max(0, proposal.x + proposal.width))
        let bottom = min(1, max(0, proposal.y + proposal.height))
        guard right > left, bottom > top else { return nil }
        self.init(x: left, y: top, width: right - left, height: bottom - top)
    }

    var area: Double { width * height }

    func intersectionOverUnion(with other: Box) -> Double {
        let intersectionWidth = max(0, min(x + width, other.x + other.width) - max(x, other.x))
        let intersectionHeight = max(0, min(y + height, other.y + other.height) - max(y, other.y))
        let intersection = intersectionWidth * intersectionHeight
        let union = area + other.area - intersection
        return union > 0 ? intersection / union : 0
    }
}
