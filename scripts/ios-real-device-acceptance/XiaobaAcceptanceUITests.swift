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

    func test00AuthenticatedSessionPersistsAcrossTwoColdLaunches() throws {
        app.launch()
        try requireAuthenticatedChat()
        attachScreenshot("pre-authenticated-session")

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

    func testConversationOpensAtLatestSeededMessage() throws {
        app.launch()
        try requireAuthenticatedChat()

        let seededMessageText = "今天优先完成两件事"
        let assistantSurface = app.descendants(matching: .any)
            .matching(
                NSPredicate(
                    format: "identifier == %@ AND label CONTAINS %@",
                    "assistant-message-surface",
                    seededMessageText
                )
            )
            .firstMatch
        XCTAssertTrue(
            assistantSurface.waitForExistence(timeout: 20),
            "The seeded assistant message was not rendered"
        )
        XCTAssertTrue(
            assistantSurface.isHittable,
            "The conversation did not open at the latest assistant message"
        )
        XCTAssertTrue(
            assistantSurface.label.contains("今天优先完成两件事"),
            "The visible latest assistant message was not the deterministic review fixture"
        )
        attachScreenshot("conversation-opened-at-latest-seeded-markdown")
    }

    func testTodayContextCanOpenAndDismiss() throws {
        app.launch()
        try requireAuthenticatedChat()

        let openToday = app.buttons["打开今日计划"]
        guard openToday.waitForExistence(timeout: 15) else {
            throw XCTSkip("No qualified today context is visible for this account")
        }

        openToday.tap()
        let backToChat = app.buttons["返回小巴"]
        XCTAssertTrue(
            backToChat.waitForExistence(timeout: 20),
            "Today context did not open the Today plan"
        )
        attachScreenshot("today-context-opened")

        backToChat.tap()
        XCTAssertTrue(
            chatSurfaceExists(timeout: 20),
            "Returning from Today did not restore the Agent chat"
        )

        let dismiss = app.buttons["关闭当前提示"]
        XCTAssertTrue(
            dismiss.waitForExistence(timeout: 10),
            "Today context dismiss action was not exposed after returning to chat"
        )
        dismiss.tap()
        XCTAssertFalse(
            dismiss.waitForExistence(timeout: 3),
            "Today context remained visible after dismissal"
        )
        attachScreenshot("today-context-dismissed")
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
