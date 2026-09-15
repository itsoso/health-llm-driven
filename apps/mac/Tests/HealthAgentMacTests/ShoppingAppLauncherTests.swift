import Foundation
import HealthAgentMacCore
import XCTest
@testable import HealthAgentMac

final class ShoppingAppLauncherTests: XCTestCase {
    @MainActor func testBridgeLaunchUsesFixedRouteAndNoQuestion() async throws {
        let bridge = ShoppingBridgeTransport()
        let pairing = try await bridge.start()
        defer { bridge.disconnect() }
        var opened: URL?
        let launcher = ShoppingAppLauncher(findApplication: { URL(fileURLWithPath: "/Applications/Kuaishou.app") }, open: { url, _ in opened = url; return true })
        let result = await launcher.openLocalBridge(pairing)
        XCTAssertTrue(result)
        let parts = try XCTUnwrap(URLComponents(url: XCTUnwrap(opened), resolvingAgainstBaseURL: false))
        let items = try XCTUnwrap(parts.queryItems)
        XCTAssertEqual(items.map(\.name), ["bundleId", "componentName", "entrySrc", "desktopBridgePort", "desktopBridgeToken", "desktopBridgeCode"])
        XCTAssertEqual(items.first { $0.name == "desktopBridgePort" }?.value, String(pairing.port))
        XCTAssertEqual(items.first { $0.name == "desktopBridgeToken" }?.value, pairing.token)
        XCTAssertFalse(launcher.notice?.contains(pairing.token) ?? true)
        XCTAssertFalse(bridge.isReady, "Opening app is not pairing")
    }

    @MainActor func testQuestionHandoffPreservesTextAndEncodesOnlyExplicitInput() async throws {
        let question = "找个杯子 & sourceId=unexpected\n中文 + 100% #测试"
        var openedURLs: [URL] = []
        let launcher = ShoppingAppLauncher(findApplication: { URL(fileURLWithPath: "/Applications/Kuaishou.app") }, open: { url, _ in
            openedURLs.append(url)
            return true
        })
        await launcher.openShoppingAssistant(question: question)
        let parts = try XCTUnwrap(URLComponents(url: XCTUnwrap(openedURLs.first), resolvingAgainstBaseURL: false))
        let items = try XCTUnwrap(parts.queryItems)
        XCTAssertEqual(items.map(\.name), ["bundleId", "componentName", "entrySrc", "sugText", "sugExtData"])
        XCTAssertEqual(items.first(where: { $0.name == "sugText" })?.value, question)
        let data = try XCTUnwrap(items.first(where: { $0.name == "sugExtData" })?.value?.data(using: .utf8))
        XCTAssertEqual(try JSONSerialization.jsonObject(with: data) as? [String: String], ["inputContent": question])
        XCTAssertNil(parts.fragment)
        XCTAssertEqual(launcher.notice, "已将问题交给快手，请在快手窗口查看提问和回复；未出现时请勿反复提交。")
    }

    @MainActor func testInvalidQuestionsNeverLaunch() async {
        var opened = false
        let launcher = ShoppingAppLauncher(findApplication: { URL(fileURLWithPath: "/Applications/Kuaishou.app") }, open: { _, _ in opened = true; return true })
        for question in ["   ", String(repeating: "a", count: 2001), "hello\u{0}world"] {
            await launcher.openShoppingAssistant(question: question)
            XCTAssertNotNil(launcher.notice)
        }
        XCTAssertFalse(opened)
    }

    @MainActor func testMissingAppDoesNotOpenScheme() async {
        var opened = false
        let launcher = ShoppingAppLauncher(findApplication: { nil }, open: { _, _ in
            opened = true
            return true
        })
        await launcher.openShoppingAssistant()
        XCTAssertFalse(opened)
        XCTAssertEqual(launcher.notice, "请先从 App Store 安装快手，再打开购物助手。")
        XCTAssertFalse(launcher.isOpening)
    }

    @MainActor func testHandoffTargetsOfficialAppWithOnlyFixedRouteParameters() async throws {
        let application = URL(fileURLWithPath: "/Applications/Kuaishou.app")
        var openedURLs: [URL] = []
        let launcher = ShoppingAppLauncher(findApplication: { application }, open: { url, app in
            XCTAssertEqual(app, application)
            openedURLs.append(url)
            return true
        })
        await launcher.openShoppingAssistant()
        let url = try XCTUnwrap(openedURLs.first)
        let parts = try XCTUnwrap(URLComponents(url: url, resolvingAgainstBaseURL: false))
        XCTAssertEqual(openedURLs.count, 1)
        XCTAssertEqual(parts.scheme, "kwai")
        XCTAssertEqual(parts.host, "krn")
        XCTAssertEqual(parts.queryItems, [
            URLQueryItem(name: "bundleId", value: "KwaishopCAIChatPageV2"),
            URLQueryItem(name: "componentName", value: "KwaishopCAIChatPageV2"),
            URLQueryItem(name: "entrySrc", value: "HOME_SHORTCUT")
        ])
        XCTAssertEqual(launcher.notice, "已请求打开，请在快手窗口继续。是否登录和能否聊天，以快手页面为准。")
    }

    @MainActor func testLaunchFailureIsVisible() async {
        let launcher = ShoppingAppLauncher(findApplication: { URL(fileURLWithPath: "/Applications/Kuaishou.app") }, open: { _, _ in false })
        await launcher.openShoppingAssistant()
        XCTAssertEqual(launcher.notice, "未能打开快手，请确认官方客户端已安装并可正常启动。")
        XCTAssertFalse(launcher.isOpening)
    }
}
