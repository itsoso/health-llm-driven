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
        app.descendants(matching: .any)
            .matching(
                NSPredicate(
                    format: "label == %@ OR label == %@ OR label == %@",
                    "按住说话",
                    "消息输入框",
                    "消息输入框容器"
                )
            )
            .firstMatch
            .waitForExistence(timeout: timeout)
    }

    private func loginSurfaceExists(timeout: TimeInterval = 2) -> Bool {
        app.textFields["手机号输入框"].waitForExistence(timeout: timeout) &&
            app.buttons["获取验证码"].exists
    }

    private func reviewCredentials() -> (account: String, password: String)? {
        let environment = ProcessInfo.processInfo.environment
        let account = environment["APP_STORE_REVIEW_DEMO_ACCOUNT"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let password = environment["APP_STORE_REVIEW_DEMO_PASSWORD"] ?? ""
        guard !account.isEmpty, !password.isEmpty else { return nil }
        return (account, password)
    }

    private func loginWithReviewAccountIfNeeded() throws {
        if chatSurfaceExists(timeout: 3) {
            return
        }
        XCTAssertTrue(loginSurfaceExists(timeout: 10), "Login surface was not exposed")
        guard let credentials = reviewCredentials() else {
            throw XCTSkip(
                "Set APP_STORE_REVIEW_DEMO_ACCOUNT and APP_STORE_REVIEW_DEMO_PASSWORD " +
                    "to exercise login persistence"
            )
        }

        let passwordMode = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "账号密码登录"))
            .firstMatch
        XCTAssertTrue(passwordMode.waitForExistence(timeout: 5), "Password login entry was not exposed")
        passwordMode.tap()

        let accountField = app.textFields["用户名输入框"]
        let passwordField = app.secureTextFields["密码输入框"]
        XCTAssertTrue(accountField.waitForExistence(timeout: 5), "Account field was not exposed")
        XCTAssertTrue(passwordField.waitForExistence(timeout: 5), "Password field was not exposed")
        accountField.tap()
        accountField.typeText(credentials.account)
        passwordField.tap()
        passwordField.typeText(credentials.password)

        let loginButton = app.buttons["登录"]
        XCTAssertTrue(loginButton.waitForExistence(timeout: 3), "Login button was not exposed")
        loginButton.tap()
        XCTAssertTrue(
            chatSurfaceExists(timeout: 45),
            "Review account did not reach the authenticated Agent chat"
        )
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

    private func composerTextInput() -> XCUIElement {
        let inputLabel = NSPredicate(format: "label BEGINSWITH %@", "消息输入框")
        let textView = app.textViews.matching(inputLabel).firstMatch
        if textView.exists {
            return textView
        }
        return app.textFields.matching(inputLabel).firstMatch
    }

    private func draftValue(_ field: XCUIElement) -> String {
        let current = (field.value as? String) ?? ""
        return current == "问小巴，或点麦克风说话" ? "" : current
    }

    private func selectAllText(_ field: XCUIElement) {
        field.tap()
        field.press(forDuration: 0.8)

        let selectAll = app.descendants(matching: .any)
            .matching(
                NSPredicate(
                    format: "label == %@ OR label == %@",
                    "Select All",
                    "全选"
                )
            )
            .firstMatch
        if selectAll.waitForExistence(timeout: 2) {
            selectAll.tap()
            return
        }

        field.tap(withNumberOfTaps: 3, numberOfTouches: 1)
    }

    private func replaceDraft(_ field: XCUIElement, with replacement: String) {
        let current = draftValue(field)
        if !current.isEmpty {
            selectAllText(field)
        } else {
            field.tap()
        }

        field.typeText(
            replacement.isEmpty
                ? XCUIKeyboardKey.delete.rawValue
                : replacement
        )
    }

    private func scrollToElement(
        _ element: XCUIElement,
        maxSwipes: Int = 8
    ) -> Bool {
        for _ in 0..<maxSwipes {
            if element.exists && element.isHittable {
                return true
            }
            app.swipeUp()
        }
        return element.exists && element.isHittable
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

    func test00ReviewAccountLoginPersistsAcrossTwoColdLaunches() throws {
        app.launch()
        try loginWithReviewAccountIfNeeded()
        attachScreenshot("review-account-authenticated")

        for coldLaunch in 1...2 {
            app.terminate()
            app.launch()
            XCTAssertTrue(
                app.wait(for: .runningForeground, timeout: 15),
                "App did not foreground on cold launch \(coldLaunch)"
            )
            XCTAssertFalse(
                loginSurfaceExists(timeout: 3),
                "Login surface returned on cold launch \(coldLaunch)"
            )
            XCTAssertTrue(
                chatSurfaceExists(timeout: 30),
                "Authenticated Agent was unavailable on cold launch \(coldLaunch)"
            )
            attachScreenshot("authenticated-cold-launch-\(coldLaunch)")
        }
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

        let field = composerTextInput()
        XCTAssertTrue(field.waitForExistence(timeout: 5), "Keyboard text field was not exposed")
        let originalDraft = draftValue(field)
        replaceDraft(field, with: draftFixture)
        XCTAssertEqual(
            draftValue(field),
            draftFixture,
            "Acceptance fixture could not replace the existing draft"
        )

        XCUIDevice.shared.press(.home)
        app.activate()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 10),
            "App did not return from background"
        )

        switchToKeyboardModeIfNeeded()
        let restoredField = composerTextInput()
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
        replaceDraft(restoredField, with: originalDraft)
    }

    func testPrivacyAndAccountDeletionEntriesAreReachable() throws {
        app.launch()
        try requireAuthenticatedChat()

        let more = app.buttons["更多会诊操作"]
        XCTAssertTrue(more.waitForExistence(timeout: 10), "More actions button was not exposed")
        more.tap()

        let personalCenter = app.buttons["我 · 个人中心与设置"]
        XCTAssertTrue(
            personalCenter.waitForExistence(timeout: 5),
            "Personal center entry was not exposed"
        )
        personalCenter.tap()

        let privacyPolicy = app.buttons["隐私政策"]
        XCTAssertTrue(
            scrollToElement(privacyPolicy),
            "Privacy policy entry was not exposed"
        )
        let accountDeletion = app.buttons["删除账号与数据"]
        XCTAssertTrue(
            scrollToElement(accountDeletion),
            "Account deletion entry was not exposed"
        )
        attachScreenshot("privacy-and-account-deletion-entries")

        XCTAssertTrue(
            scrollToElement(privacyPolicy),
            "Privacy policy entry could not be restored after checking account deletion"
        )
        privacyPolicy.tap()
        XCTAssertTrue(
            app.staticTexts["隐私政策"].waitForExistence(timeout: 5),
            "Privacy policy page did not open"
        )
        attachScreenshot("privacy-policy-page")
    }
}
