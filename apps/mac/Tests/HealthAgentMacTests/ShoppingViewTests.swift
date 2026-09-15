import AppKit
import HealthAgentMacCore
import SnapshotTesting
import SwiftUI
import WebKit
import XCTest
@testable import HealthAgentMac

final class ShoppingViewTests: XCTestCase {
    @MainActor func testBrowserResetDiscardsCookiesAndUsesNonpersistentStore() async throws {
        let browser = ShoppingBrowserSession()
        browser.open(loadLoginPage: false)
        let oldView = try XCTUnwrap(browser.webView)
        XCTAssertFalse(oldView.configuration.websiteDataStore.isPersistent)
        let cookie = try XCTUnwrap(HTTPCookie(properties: [.name: "token", .value: "fake-test", .domain: ".kuaishou.com", .path: "/"]))
        await oldView.configuration.websiteDataStore.httpCookieStore.setCookie(cookie)
        let before = await browser.cookies()
        XCTAssertEqual(before.map(\.name), ["token"])
        XCTAssertTrue(browser.responds(to: NSSelectorFromString("webView:decidePolicyForNavigationAction:decisionHandler:")))
        browser.reset()
        XCTAssertNil(browser.webView)
        XCTAssertNil(oldView.navigationDelegate)
        browser.open(loadLoginPage: false)
        XCTAssertFalse(browser.webView === oldView)
        let after = await browser.cookies()
        XCTAssertTrue(after.isEmpty)
        browser.reset()
    }

    @MainActor func testShoppingWelcome() {
        let browser = ShoppingBrowserSession()
        let vm = ShoppingChatViewModel(credentials: browser)
        vm.bindOwner("synthetic-preview-owner")
        snapshot(vm, browser: browser)
    }

    @MainActor func testShoppingDemoConversation() async {
        let browser = ShoppingBrowserSession()
        let vm = ShoppingChatViewModel(credentials: browser)
        vm.bindOwner("synthetic-preview-owner")
        vm.setDemoMode(true)
        vm.draft = "找一个通勤用的保温杯"
        await vm.send()
        snapshot(vm, browser: browser, height: 1080)
    }

    @MainActor private func snapshot(_ vm: ShoppingChatViewModel, browser: ShoppingBrowserSession, height: CGFloat = 760,
                                     file: StaticString = #filePath, testName: String = #function, line: UInt = #line) {
        let view = ShoppingChatView(viewModel: vm, browser: browser)
            .frame(width: 900, height: height)
            .environment(\.colorScheme, .light)
            .dynamicTypeSize(.medium)
        let host = ShoppingSnapshotHost(rootView: view)
        host.frame = CGRect(x: 0, y: 0, width: 900, height: height)
        assertSnapshot(of: host, as: .image(precision: 0.99), file: file, testName: testName, line: line)
    }
}

/// Keep pixel dimensions independent of the currently attached display. The
/// reference is rendered at one pixel per point, including on Retina machines.
@MainActor private final class ShoppingSnapshotHost<Content: View>: NSHostingView<Content> {
    override func bitmapImageRepForCachingDisplay(in rect: NSRect) -> NSBitmapImageRep? {
        NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(rect.width), pixelsHigh: Int(rect.height),
                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                         colorSpaceName: .calibratedRGB, bytesPerRow: 0, bitsPerPixel: 0)
    }
}
