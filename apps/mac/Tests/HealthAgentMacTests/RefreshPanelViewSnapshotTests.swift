import XCTest
import SwiftUI
import SnapshotTesting
@testable import HealthAgentMac
import HealthAgentMacCore

@MainActor
final class RefreshPanelViewSnapshotTests: XCTestCase {
    override func setUp() {
        super.setUp()
        // isRecording = true
    }

    @MainActor
    func testRefreshPanel_Ready() {
        assertCardSnapshot(isLoading: false, named: "ready")
    }

    @MainActor
    func testRefreshPanel_Loading() {
        assertCardSnapshot(isLoading: true, named: "loading")
    }

    @MainActor
    private func assertCardSnapshot(
        isLoading: Bool,
        named name: String,
        filePath: StaticString = #filePath,
        testName: String = #function,
        line: UInt = #line
    ) {
        let view = RefreshPanelView(
            isLoading: isLoading,
            appLanguageRaw: "en",
            onRefresh: {}
        )
        .frame(width: 360)
        .padding(20)
        .background(Color.white)
        .environment(\.colorScheme, .light)
        .dynamicTypeSize(.medium)

        let host = NSHostingView(rootView: view)
        host.frame = CGRect(origin: .zero, size: host.fittingSize)

        assertSnapshot(
            of: host,
            as: .image(precision: 0.99),
            named: name,
            file: filePath,
            testName: testName,
            line: line
        )
    }
}
