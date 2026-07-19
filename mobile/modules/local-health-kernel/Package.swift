// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "LocalHealthCapabilityProbe",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(
            name: "LocalHealthCapabilityProbe",
            targets: ["LocalHealthCapabilityProbe"]
        ),
    ],
    targets: [
        .target(
            name: "LocalHealthCapabilityProbe",
            path: "ios",
            exclude: ["LocalHealthKernel.podspec", "Resources"]
        ),
        .testTarget(
            name: "LocalHealthCapabilityProbeTests",
            dependencies: ["LocalHealthCapabilityProbe"],
            path: "Tests"
        ),
    ]
)
