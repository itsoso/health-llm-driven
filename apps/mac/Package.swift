// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "HealthAgentMac",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "HealthAgentMac", targets: ["HealthAgentMac"]),
        .library(name: "HealthAgentMacCore", targets: ["HealthAgentMacCore"])
    ],
    dependencies: [
        .package(url: "https://github.com/pointfreeco/swift-snapshot-testing", from: "1.17.0")
    ],
    targets: [
        .target(name: "HealthAgentMacCore"),
        .executableTarget(
            name: "HealthAgentMac",
            dependencies: ["HealthAgentMacCore"],
            resources: [
                .process("Resources")
            ]
        ),
        .testTarget(
            name: "HealthAgentMacCoreTests",
            dependencies: ["HealthAgentMacCore"]
        ),
        .testTarget(
            name: "HealthAgentMacTests",
            dependencies: [
                "HealthAgentMac",
                .product(name: "SnapshotTesting", package: "swift-snapshot-testing")
            ],
            exclude: ["__Snapshots__"]
        )
    ]
)
