import XCTest

final class XiaobaAcceptanceUITests: XCTestCase {
    private let app = XCUIApplication(bundleIdentifier: "life.executor.health")
    private let draftFixture = "UI自动验收草稿不发送"

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    private func attachScreenshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func chatSurfaceExists(timeout: TimeInterval = 2) -> Bool {
        app.buttons["按住说话"].waitForExistence(timeout: timeout) ||
            app.textFields["消息输入框"].waitForExistence(timeout: timeout) ||
            app.buttons["消息输入框容器"].waitForExistence(timeout: timeout)
    }

    private func loginSurfaceExists(timeout: TimeInterval = 2) -> Bool {
        app.textFields["手机号输入框"].waitForExistence(timeout: timeout) &&
            app.buttons["获取验证码"].exists
    }

    private func requireAuthenticatedChat() throws {
        if loginSurfaceExists(timeout: 2) {
            throw XCTSkip("Owner login is required before authenticated acceptance checks")
        }
        XCTAssertTrue(
            chatSurfaceExists(timeout: 30),
            "Authenticated Agent chat surface was not exposed"
        )
    }

    private func switchToKeyboardModeIfNeeded() {
        let keyboardToggle = app.buttons["切换到键盘输入"]
        if keyboardToggle.waitForExistence(timeout: 2) {
            keyboardToggle.tap()
        }
    }

    private func clearDraft(_ field: XCUIElement) {
        field.tap()
        let current = (field.value as? String) ?? ""
        guard !current.isEmpty && current != "问小巴，或点麦克风说话" else { return }

        let deleteKey = app.keys["delete"].exists ? app.keys["delete"] : app.keys["删除"]
        if deleteKey.exists {
            for _ in current {
                deleteKey.tap()
            }
        }
    }

    func testInstalledBuildLaunchesExpectedEntrySurface() throws {
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 15),
            "Installed app did not reach the foreground"
        )

        let reachedChat = chatSurfaceExists(timeout: 20)
        let reachedLogin = reachedChat ? false : loginSurfaceExists(timeout: 5)
        attachScreenshot(reachedChat ? "authenticated-launch" : "login-launch")

        XCTAssertTrue(reachedChat || reachedLogin, "App exposed neither login nor Agent chat")
    }

    func testBriefingCanExpandAndCollapse() throws {
        app.launch()
        try requireAuthenticatedChat()

        let briefing = app.buttons.matching(
            NSPredicate(format: "label BEGINSWITH %@", "今日简报：")
        ).firstMatch
        guard briefing.waitForExistence(timeout: 15) else {
            throw XCTSkip("Today's briefing is not visible for this account")
        }

        briefing.tap()
        attachScreenshot("today-briefing-expanded")
        XCTAssertTrue(
            briefing.waitForExistence(timeout: 5),
            "Briefing control disappeared after expansion"
        )
        briefing.tap()
        attachScreenshot("today-briefing-collapsed")
    }

    func testDraftSurvivesBackgroundWithoutSending() throws {
        app.launch()
        try requireAuthenticatedChat()
        switchToKeyboardModeIfNeeded()

        let container = app.buttons["消息输入框容器"]
        if container.waitForExistence(timeout: 5) {
            container.tap()
        }
        let field = app.textFields["消息输入框"]
        XCTAssertTrue(field.waitForExistence(timeout: 5), "Keyboard text field was not exposed")
        clearDraft(field)
        field.typeText(draftFixture)

        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 10),
            "App did not return from background"
        )

        switchToKeyboardModeIfNeeded()
        let restoredField = app.textFields["消息输入框"]
        XCTAssertTrue(
            restoredField.waitForExistence(timeout: 5),
            "Composer disappeared after foregrounding"
        )
        XCTAssertEqual(
            restoredField.value as? String,
            draftFixture,
            "Unsent draft was not preserved"
        )
        attachScreenshot("draft-restored-after-background")
        clearDraft(restoredField)
    }

    func testPrivacyAndAccountDeletionEntriesAreReachable() throws {
        app.launch()
        try requireAuthenticatedChat()

        let more = app.buttons["更多会诊操作"]
        XCTAssertTrue(more.waitForExistence(timeout: 10), "More actions button was not exposed")
        more.tap()

        let personalCenter = app.staticTexts["我 · 个人中心与设置"]
        XCTAssertTrue(
            personalCenter.waitForExistence(timeout: 5),
            "Personal center entry was not exposed"
        )
        personalCenter.tap()

        let privacyPolicy = app.staticTexts["隐私政策"]
        XCTAssertTrue(
            privacyPolicy.waitForExistence(timeout: 10),
            "Privacy policy entry was not exposed"
        )
        XCTAssertTrue(
            app.staticTexts["删除账号与数据"].exists,
            "Account deletion entry was not exposed"
        )
        attachScreenshot("privacy-and-account-deletion-entries")

        privacyPolicy.tap()
        XCTAssertTrue(
            app.staticTexts["隐私政策"].waitForExistence(timeout: 5),
            "Privacy policy page did not open"
        )
        attachScreenshot("privacy-policy-page")
    }
}
