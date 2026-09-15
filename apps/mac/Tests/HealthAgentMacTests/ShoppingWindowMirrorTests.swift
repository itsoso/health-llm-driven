import AppKit
import HealthAgentMacCore
import XCTest
@testable import HealthAgentMac

final class ShoppingWindowMirrorTests: XCTestCase {
    func testHeadingRequiresOneExactHighConfidenceTitle() {
        XCTAssertTrue(ShoppingWindowCapture.isShoppingHeading("AI 购物助手", confidence: 0.95))
        XCTAssertTrue(ShoppingWindowCapture.isShoppingHeading("AI 购物助手", confidence: 0.5))
        for text in ["搜索购物助手", "AI购物助手相关视频", "购物助手", "AI购物", "助手", ""] {
            XCTAssertFalse(ShoppingWindowCapture.isShoppingHeading(text, confidence: 1))
        }
        XCTAssertFalse(ShoppingWindowCapture.isShoppingHeading("AI购物助手", confidence: 0.3))
    }

    @MainActor func testSharedSessionClearInvalidatesBothWindowsBeforeLateCaptureReturns() async throws {
        let vm = ShoppingChatViewModel(credentials: ShoppingBrowserSession())
        vm.bindOwner("synthetic-mirror-owner")
        for clear in [vm.clearConversation, vm.logout, vm.prepareForLogin] {
            let session = vm.sessionGeneration
            var continuations: [CheckedContinuation<CGImage, any Error>] = []
            let entered = expectation(description: "both windows capturing")
            entered.expectedFulfillmentCount = 2
            let capture: () async throws -> CGImage = {
                try await withCheckedThrowingContinuation {
                    continuations.append($0)
                    entered.fulfill()
                }
            }
            let first = ShoppingWindowMirror(permission: { true }, capture: capture)
            let second = ShoppingWindowMirror(permission: { true }, capture: capture)
            first.start { vm.sessionGeneration == session }
            second.start { vm.sessionGeneration == session }
            await fulfillment(of: [entered], timeout: 2)
            clear()
            XCTAssertNotEqual(vm.sessionGeneration, session)
            let bitmap = try XCTUnwrap(NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 2, pixelsHigh: 2, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0))
            let image = try XCTUnwrap(bitmap.cgImage)
            continuations.forEach { $0.resume(returning: image) }
            await Task.yield()
            await Task.yield()
            XCTAssertNil(first.image)
            XCTAssertNil(second.image)
            XCTAssertFalse(first.isActive)
            XCTAssertFalse(second.isActive)
        }
    }

    @MainActor func testDeniedPermissionNeverCaptures() async {
        var captured = false
        let mirror = ShoppingWindowMirror(permission: { false }, capture: {
            captured = true
            throw ShoppingWindowMirrorError.windowUnavailable
        })
        mirror.start()
        await Task.yield()
        XCTAssertFalse(captured)
        XCTAssertFalse(mirror.isActive)
        XCTAssertNil(mirror.image)
        XCTAssertNotNil(mirror.notice)
    }

    @MainActor func testStoppedSessionCannotPublishLateImage() async throws {
        var continuation: CheckedContinuation<CGImage, any Error>?
        let entered = expectation(description: "capture entered")
        let mirror = ShoppingWindowMirror(permission: { true }, capture: {
            try await withCheckedThrowingContinuation {
                continuation = $0
                entered.fulfill()
            }
        })
        mirror.start()
        await fulfillment(of: [entered], timeout: 2)
        mirror.stop()
        let bitmap = try XCTUnwrap(NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 2, pixelsHigh: 2, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0))
        continuation?.resume(returning: try XCTUnwrap(bitmap.cgImage))
        await Task.yield()
        await Task.yield()
        XCTAssertNil(mirror.image)
        XCTAssertFalse(mirror.isActive)
    }

    @MainActor func testCaptureFailureClearsFrameAndStops() async {
        let entered = expectation(description: "capture failed")
        let mirror = ShoppingWindowMirror(permission: { true }, capture: {
            entered.fulfill()
            throw ShoppingWindowMirrorError.notShoppingPage
        })
        mirror.start()
        await fulfillment(of: [entered], timeout: 2)
        await Task.yield()
        XCTAssertFalse(mirror.isActive)
        XCTAssertNil(mirror.image)
        XCTAssertEqual(mirror.notice, ShoppingWindowMirrorError.notShoppingPage.localizedDescription)
    }

    func testOnlyOfficialVisibleMainWindowIsEligible() {
        XCTAssertTrue(ShoppingWindowCapture.eligible(bundleID: "com.jiangjia.gif", layer: 0, onScreen: true, width: 788, height: 1079))
        XCTAssertFalse(ShoppingWindowCapture.eligible(bundleID: "life.executor.health.mac", layer: 0, onScreen: true, width: 788, height: 1079))
        XCTAssertFalse(ShoppingWindowCapture.eligible(bundleID: "com.jiangjia.gif", layer: 0, onScreen: false, width: 500, height: 500))
        XCTAssertFalse(ShoppingWindowCapture.eligible(bundleID: "com.jiangjia.gif", layer: 3, onScreen: true, width: 788, height: 1079))
    }
}
