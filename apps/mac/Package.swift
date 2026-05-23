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
    targets: [
        .target(name: "HealthAgentMacCore"),
        .executableTarget(
            name: "HealthAgentMac",
            dependencies: ["HealthAgentMacCore"]
        ),
        .testTarget(
            name: "HealthAgentMacCoreTests",
            dependencies: ["HealthAgentMacCore"]
        )
    ]
)
