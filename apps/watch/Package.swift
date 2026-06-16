// swift-tools-version: 6.0
// Apple Watch Companion 核心逻辑包(纯 Foundation,与 watchOS UI 解耦)。
// 不限平台 → `swift test` 在 Mac host 直接跑(逻辑全可单测);watchOS app target
// (W3 由 Expo config-plugin 注入)编译同一批源文件。
import PackageDescription

let package = Package(
    name: "WatchCompanion",
    products: [
        .library(name: "WatchCompanionCore", targets: ["WatchCompanionCore"]),
    ],
    targets: [
        .target(name: "WatchCompanionCore"),
        .testTarget(name: "WatchCompanionCoreTests", dependencies: ["WatchCompanionCore"]),
    ]
)
