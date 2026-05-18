import XCTest

final class PlaniniUITests: XCTestCase {
    private let seededEmail = "planini@schaedler.rocks"
    private let initialListName = "Browser Test Shop"

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testListViewFlow() throws {
        try assertLocalTestBackend()
        let loginApp = XCUIApplication()
        loginApp.launchEnvironment["PLANINI_UI_TEST_MODE"] = "1"
        loginApp.launchEnvironment["PLANINI_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        loginApp.launch()
        XCTAssertTrue(loginApp.buttons["login-passkey-button"].waitForExistence(timeout: 10))
        captureScreenshot(named: "promotion-login-dialogue")
        assertReviewerOnboardingAvailable(in: loginApp)
        loginApp.terminate()

        let session = if let injectedSession {
            injectedSession
        } else {
            try bootstrapSession(email: userEmail)
        }
        let app = XCUIApplication()
        app.launchEnvironment["PLANINI_UI_TEST_MODE"] = "1"
        app.launchEnvironment["PLANINI_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        app.launchEnvironment["PLANINI_UI_TEST_ACCESS_TOKEN"] = session.accessToken
        app.launchEnvironment["PLANINI_UI_TEST_DISPLAY_NAME"] = session.displayName
        app.launchEnvironment["PLANINI_UI_TEST_INITIAL_LIST_NAME"] = initialListName
        app.launchEnvironment["PLANINI_UI_TEST_RESET_APPEARANCE_MODE"] = "1"

        app.launch()

        let listTitle = app.staticTexts["list-detail-title"]
        XCTAssertTrue(
            openInitialListDetail(in: app, listTitle: listTitle),
            "Expected bootstrapped initial list to open."
        )
        XCTAssertTrue(tapTab("Lists", in: app))
        let initialListRow = app.buttons["list-row-\(initialListName)"]
        XCTAssertTrue(initialListRow.waitForExistence(timeout: 10))
        let initialListNameText = app.staticTexts[initialListName]
        XCTAssertTrue(initialListNameText.waitForExistence(timeout: 3))
        captureScreenshot(named: "promotion-list-of-lists")
        initialListNameText.tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-list-detail")

        XCTAssertTrue(app.staticTexts["Uncategorized"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["Konserven"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["Milch & Eier"].waitForExistence(timeout: 3))
        let favoriteButton = app.buttons["favorite-list-button"]
        XCTAssertTrue(favoriteButton.waitForExistence(timeout: 3))
        XCTAssertTrue(favoriteButton.label.contains("Unfavorite"))
        favoriteButton.tap()
        XCTAssertTrue(favoriteButton.waitForExistence(timeout: 3))
        XCTAssertTrue(favoriteButton.label.contains("Favorite"))
        favoriteButton.tap()
        XCTAssertTrue(favoriteButton.waitForExistence(timeout: 3))
        XCTAssertTrue(favoriteButton.label.contains("Unfavorite"))

        XCTAssertTrue(app.tabBars.buttons[initialListName].waitForExistence(timeout: 3))
        XCTAssertTrue(tapTab(initialListName, in: app))
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-favorite-list")

        let uncategorizedCountBadge = firstExistingElement(
            [
                app.staticTexts["section-count-badge-uncategorized"],
                app.staticTexts["Uncategorized count, 1 item"],
                app.otherElements["section-count-badge-uncategorized"],
                app.otherElements["Uncategorized count, 1 item"],
            ],
            timeout: 3
        )
        XCTAssertTrue(uncategorizedCountBadge.waitForExistence(timeout: 3))
        XCTAssertEqual(uncategorizedCountBadge.label, "Uncategorized count, 1 item")

        let quickAddUncategorized = firstExistingElement(
            [
                app.buttons["quick-add-category-uncategorized"],
                app.buttons["Quick add uncategorized item"],
                app.buttons.containing(NSPredicate(format: "label CONTAINS %@", "Quick add uncategorized")).firstMatch,
            ],
            timeout: 3
        )
        XCTAssertTrue(quickAddUncategorized.waitForExistence(timeout: 3))
        quickAddUncategorized.tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["add-item-save-button"].waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-category-quick-add")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(waitForElementToDisappear(app.otherElements["add-item-sheet"], timeout: 3))

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-add-item-sheet")

        let suggestionProbeField = app.textFields["add-item-name-field"]
        XCTAssertTrue(suggestionProbeField.waitForExistence(timeout: 3))
        suggestionProbeField.tap()
        suggestionProbeField.typeText("Loose")
        let activeSuggestion = app.buttons.containing(NSPredicate(format: "label CONTAINS %@", "Jump to Loose item")).firstMatch
        XCTAssertTrue(activeSuggestion.waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-add-item-suggestions")
        app.buttons["Cancel"].tap()
        XCTAssertTrue(waitForElementToDisappear(app.otherElements["add-item-sheet"], timeout: 3))

        let uniqueSuffix = UUID().uuidString.prefix(8)
        let enterSavedItemName = "UI Test Enter \(uniqueSuffix)"
        let itemName = "UI Test Item \(uniqueSuffix)"
        let itemQuantity = "1 bunch"
        let updatedName = "\(itemName) Updated"

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        let nameField = app.textFields["add-item-name-field"]
        XCTAssertTrue(nameField.waitForExistence(timeout: 3))
        nameField.typeText("\(enterSavedItemName)\n")
        XCTAssertTrue(app.staticTexts[enterSavedItemName].waitForExistence(timeout: 5))
        XCTAssertTrue(
            waitForItem(
                named: enterSavedItemName,
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 3))
        XCTAssertTrue(nameField.waitForExistence(timeout: 3))
        nameField.typeText(itemName)

        let quantityField = app.textFields["add-item-quantity-field"]
        quantityField.tap()
        quantityField.typeText(itemQuantity)

        chooseCategory(
            named: "Milch & Eier",
            using: "add-item-category-link",
            in: app,
            searchText: "molkrei",
            sortOption: "A-Z",
            screenshotName: "ios-ui-category-picker"
        )
        XCTAssertTrue(app.buttons["add-item-category-link"].label.contains("Milch & Eier"))

        let noteField = app.textFields["add-item-note-field"]
        noteField.tap()
        noteField.typeText("for pasta")

        tapElement(app.buttons["add-item-save-button"])
        XCTAssertTrue(waitForElementToDisappear(app.otherElements["add-item-sheet"], timeout: 10))
        XCTAssertTrue(
            waitForItem(
                named: itemName,
                inListNamed: initialListName,
                accessToken: session.accessToken,
                timeout: 20
            )
        )
        XCTAssertTrue(app.staticTexts[itemName].waitForExistence(timeout: 15))
        captureScreenshot(named: "ios-ui-added-item")
        XCTAssertTrue(
            waitForItemCategory(
                named: itemName,
                categoryNamed: "Milch & Eier",
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )

        let createdItemLabel = app.staticTexts[itemName]
        scrollToElement(createdItemLabel, in: app)
        tapElement(createdItemLabel)
        XCTAssertTrue(app.otherElements["edit-item-sheet"].waitForExistence(timeout: 3))
        let undoButton = app.buttons["Undo"]
        let redoButton = app.buttons["Redo"]
        let closeButton = app.buttons["edit-item-close-button"]
        XCTAssertTrue(undoButton.waitForExistence(timeout: 3))
        XCTAssertTrue(redoButton.waitForExistence(timeout: 3))
        XCTAssertTrue(closeButton.waitForExistence(timeout: 3))
        XCTAssertLessThan(undoButton.frame.midX, closeButton.frame.midX)
        XCTAssertLessThan(redoButton.frame.midX, closeButton.frame.midX)
        captureScreenshot(named: "promotion-edit-item-dialogue")

        let editNameField = app.textFields["edit-item-name-field"]
        editNameField.tap()
        editNameField.typeText(" Updated")
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(updatedName))

        undoButton.tap()
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(itemName))
        XCTAssertFalse(editNameField.valueText.contains("Updated"))

        redoButton.tap()
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(updatedName))

        chooseCategory(
            named: "Konserven",
            using: "edit-item-category-link",
            in: app,
            searchText: "kon",
            sortOption: "Most used",
            screenshotName: "ios-ui-edit-category-picker"
        )
        XCTAssertTrue(app.buttons["edit-item-category-link"].label.contains("Konserven"))
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        captureScreenshot(named: "ios-ui-live-edit-autosave")
        closeButton.tap()
        XCTAssertTrue(app.staticTexts[updatedName].waitForExistence(timeout: 5))
        XCTAssertTrue(
            waitForItem(
                named: updatedName,
                inListNamed: initialListName,
                accessToken: session.accessToken,
                timeout: 20
            )
        )
        XCTAssertTrue(
            waitForItemCategory(
                named: updatedName,
                categoryNamed: "Konserven",
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )

        let updatedItemID = try itemID(
            named: updatedName,
            inListNamed: initialListName,
            accessToken: session.accessToken
        )
        XCTAssertTrue(
            waitForItemRow(itemID: updatedItemID, named: updatedName, in: app, timeout: 20),
            "Expected updated item row to be visible after closing edit sheet."
        )
        let updatedItemLabel = app.staticTexts[updatedName]
        let updatedCheckButton = app.buttons["toggle-item-\(updatedItemID.uuidString)"]
        scrollToElement(updatedItemLabel, in: app)
        scrollToElement(updatedCheckButton, in: app)
        XCTAssertTrue(updatedCheckButton.waitForExistence(timeout: 3))
        tapElement(updatedCheckButton)
        XCTAssertTrue(
            waitForCheckedItem(
                named: updatedName,
                inListNamed: initialListName,
                accessToken: session.accessToken,
                timeout: 20
            )
        )
        scrollToElement(updatedItemLabel, in: app)
        captureScreenshot(named: "ios-ui-checked-item")
        captureScreenshot(named: "promotion-filled-list")

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        let checkedSuggestionField = app.textFields["add-item-name-field"]
        XCTAssertTrue(checkedSuggestionField.waitForExistence(timeout: 5))
        checkedSuggestionField.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        checkedSuggestionField.typeText(updatedName)
        let checkedSuggestion = firstExistingElement(
            [
                app.buttons["add-item-suggestion-\(updatedItemID.uuidString)"],
                app.buttons.containing(NSPredicate(format: "label CONTAINS %@", "Add \(updatedName) back")).firstMatch,
            ],
            timeout: 10
        )
        XCTAssertTrue(checkedSuggestion.waitForExistence(timeout: 1))
        scrollToHittable(checkedSuggestion, in: app)
        captureScreenshot(named: "ios-ui-checked-item-suggestion")
        let addItemSheet = app.otherElements["add-item-sheet"]
        let cancelButton = app.buttons["Cancel"]
        if cancelButton.waitForExistence(timeout: 3) {
            cancelButton.tap()
        }
        XCTAssertTrue(waitForElementToDisappear(addItemSheet, timeout: 10))

        let moveItemName = "UI Test Move \(uniqueSuffix)"
        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        let moveNameField = app.textFields["add-item-name-field"]
        XCTAssertTrue(moveNameField.waitForExistence(timeout: 3))
        moveNameField.typeText("\(moveItemName)\n")
        XCTAssertTrue(waitForElementToDisappear(app.otherElements["add-item-sheet"], timeout: 8))
        XCTAssertTrue(
            waitForItem(
                named: moveItemName,
                inListNamed: initialListName,
                accessToken: session.accessToken,
                timeout: 20
            )
        )
        let moveItemID = try itemID(
            named: moveItemName,
            inListNamed: initialListName,
            accessToken: session.accessToken
        )
        XCTAssertTrue(
            waitForItemRow(itemID: moveItemID, named: moveItemName, in: app, timeout: 20),
            "Expected move test item row to be visible before opening edit sheet."
        )
        let moveItemLabel = app.staticTexts[moveItemName]
        scrollToElement(moveItemLabel, in: app)
        tapElement(moveItemLabel)
        XCTAssertTrue(app.otherElements["edit-item-sheet"].waitForExistence(timeout: 3))
        let movePicker = firstExistingElement(
            [
                app.buttons["edit-item-list-picker"],
                app.pickers["edit-item-list-picker"],
                app.otherElements["edit-item-list-picker"],
                app.buttons["Move to list"],
            ],
            timeout: 3
        )
        tapElement(movePicker)
        let hostingChoice = firstExistingElement(
            [
                app.buttons["Hosting errands"],
                app.staticTexts["Hosting errands"],
                app.cells["Hosting errands"],
            ],
            timeout: 3
        )
        tapElement(hostingChoice)
        XCTAssertTrue(waitForElementToDisappear(app.otherElements["edit-item-sheet"], timeout: 8))
        XCTAssertTrue(
            waitForItem(
                named: moveItemName,
                inListNamed: "Hosting errands",
                accessToken: session.accessToken
            )
        )
        let moveNotice = app.otherElements["item-move-notice-\(moveItemID.uuidString)"]
        XCTAssertTrue(moveNotice.waitForExistence(timeout: 5))
        let moveNoticeMessage = app.staticTexts["item-move-notice-message-\(moveItemID.uuidString)"]
        XCTAssertTrue(moveNoticeMessage.waitForExistence(timeout: 3))
        XCTAssertTrue(moveNoticeMessage.label.contains(moveItemName))
        XCTAssertTrue(moveNoticeMessage.label.contains("Hosting errands"))
        captureScreenshot(named: "ios-ui-moved-item-notice")
        app.buttons["move-item-undo-button-\(moveItemID.uuidString)"].tap()
        XCTAssertTrue(
            waitForItem(
                named: moveItemName,
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )
        XCTAssertTrue(
            waitForItemAbsent(
                named: moveItemName,
                inListNamed: "Hosting errands",
                accessToken: session.accessToken
            )
        )
        try deleteItem(itemID: moveItemID, accessToken: session.accessToken)

        XCTAssertTrue(tapTab("Lists", in: app))
        returnToListsRootIfNeeded(app)
        let hostingListRow = app.buttons["list-row-Hosting errands"]
        XCTAssertTrue(hostingListRow.waitForExistence(timeout: 10))
        hostingListRow.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.5)).tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, "Hosting errands")
        captureScreenshot(named: "ios-ui-list-switcher")

        XCTAssertTrue(tapTab("Settings", in: app, timeout: 10))
        XCTAssertTrue(app.buttons["settings-sign-out-button"].waitForExistence(timeout: 5))
        assertAppearanceMode("System", in: app)
        selectAppearanceMode("Dark", in: app)
        assertAppearanceMode("Dark", in: app)
        captureScreenshot(named: "ios-ui-settings-dark-mode")

        app.terminate()
        app.launchEnvironment.removeValue(forKey: "PLANINI_UI_TEST_RESET_APPEARANCE_MODE")
        app.launch()
        XCTAssertTrue(tapTab("Settings", in: app, timeout: 15))
        assertAppearanceMode("Dark", in: app)
        selectAppearanceMode("Light", in: app)
        assertAppearanceMode("Light", in: app)
        selectAppearanceMode("System", in: app)
        assertAppearanceMode("System", in: app)
        captureScreenshot(named: "ios-ui-settings")
    }

    func testForceClosedAppRestoresSavedSession() throws {
        try assertLocalTestBackend()
        let session = if let injectedSession {
            injectedSession
        } else {
            try bootstrapSession(email: userEmail)
        }

        let app = XCUIApplication()
        app.launchEnvironment["PLANINI_UI_TEST_MODE"] = "1"
        app.launchEnvironment["PLANINI_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        app.launchEnvironment["PLANINI_UI_TEST_ACCESS_TOKEN"] = session.accessToken
        app.launchEnvironment["PLANINI_UI_TEST_DISPLAY_NAME"] = session.displayName
        app.launchEnvironment["PLANINI_UI_TEST_INITIAL_LIST_NAME"] = initialListName
        app.launch()

        let listTitle = app.staticTexts["list-detail-title"]
        XCTAssertTrue(
            openInitialListDetail(in: app, listTitle: listTitle),
            "Expected bootstrapped list before force-closing the app."
        )
        XCTAssertFalse(app.buttons["login-passkey-button"].exists)
        app.terminate()

        let relaunchedApp = XCUIApplication()
        relaunchedApp.launchEnvironment["PLANINI_UI_TEST_MODE"] = "1"
        relaunchedApp.launchEnvironment["PLANINI_UI_TEST_RESTORE_STORED_SESSION"] = "1"
        relaunchedApp.launchEnvironment["PLANINI_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        relaunchedApp.launch()

        let restoredListTitle = relaunchedApp.staticTexts["list-detail-title"]
        XCTAssertTrue(
            openInitialListDetail(in: relaunchedApp, listTitle: restoredListTitle),
            "Expected saved session to survive force-close and restore the initial list."
        )
        XCTAssertFalse(relaunchedApp.buttons["login-passkey-button"].exists)
        relaunchedApp.terminate()
    }

    func testListReceivesLiveUpdates() throws {
        try assertLocalTestBackend()
        let session = if let injectedSession {
            injectedSession
        } else {
            try bootstrapSession(email: userEmail)
        }

        let app = XCUIApplication()
        app.launchEnvironment["PLANINI_UI_TEST_MODE"] = "1"
        app.launchEnvironment["PLANINI_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        app.launchEnvironment["PLANINI_UI_TEST_ACCESS_TOKEN"] = session.accessToken
        app.launchEnvironment["PLANINI_UI_TEST_DISPLAY_NAME"] = session.displayName
        app.launchEnvironment["PLANINI_UI_TEST_INITIAL_LIST_NAME"] = initialListName
        app.launch()

        let listTitle = app.staticTexts["list-detail-title"]
        XCTAssertTrue(
            openInitialListDetail(in: app, listTitle: listTitle),
            "Expected bootstrapped initial list to open before live-update checks."
        )
        XCTAssertEqual(listTitle.label, initialListName)
        XCTAssertTrue(app.staticTexts["Loose item"].waitForExistence(timeout: 5))
        XCTAssertTrue(
            waitForLiveUpdatesConnection(
                app: app,
                listName: initialListName,
                accessToken: session.accessToken
            ),
            "Expected live updates to connect before checking external mutations."
        )

        let uniqueSuffix = UUID().uuidString.prefix(8)
        let itemName = "A UI Live \(uniqueSuffix)"
        let updatedName = "\(itemName) Updated"
        let itemID = try createItem(
            named: itemName,
            note: "",
            inListNamed: initialListName,
            accessToken: session.accessToken
        )

        XCTAssertTrue(
            waitForItemRow(itemID: itemID, named: itemName, in: app, timeout: 20),
            "Expected live-created item to appear without manual refresh."
        )
        captureScreenshot(named: "ios-ui-live-item-created")

        try updateItem(
            itemID: itemID,
            name: updatedName,
            note: "",
            accessToken: session.accessToken
        )
        XCTAssertTrue(
            waitForItemRow(itemID: itemID, named: updatedName, in: app, timeout: 20),
            "Expected live-updated item to rename without manual refresh."
        )

        try deleteItem(itemID: itemID, accessToken: session.accessToken)
        XCTAssertTrue(
            waitForElementToDisappear(app.staticTexts[updatedName], timeout: 20),
            "Expected live-deleted item to disappear without manual refresh."
        )
    }

    private var baseURL: URL {
        if
            let value = environmentValue("PLANINI_UI_TEST_BASE_URL"),
            let url = URL(string: value)
        {
            return url
        }
        return URL(string: "http://localhost:8018")!
    }

    private var bootstrapBaseURL: URL {
        if
            let value = environmentValue("PLANINI_UI_TEST_BOOTSTRAP_BASE_URL"),
            let url = URL(string: value)
        {
            return url
        }
        return URL(string: "http://localhost:8018")!
    }

    private var userEmail: String {
        guard let configuredEmail = environmentValue("PLANINI_UI_TEST_USER_EMAIL")
        else {
            return seededEmail
        }
        return configuredEmail
    }

    private var injectedSession: UITestSession? {
        guard
            let accessToken = environmentValue("PLANINI_UI_TEST_ACCESS_TOKEN"),
            let displayName = environmentValue("PLANINI_UI_TEST_DISPLAY_NAME")
        else {
            return nil
        }
        return UITestSession(accessToken: accessToken, displayName: displayName)
    }

    private func environmentValue(_ key: String) -> String? {
        guard
            let value = ProcessInfo.processInfo.environment[key]?.trimmingCharacters(
                in: .whitespacesAndNewlines
            ),
            value.isEmpty == false,
            value.hasPrefix("$(") == false
        else {
            return nil
        }
        return value
    }

    private func assertLocalTestBackend() throws {
        try assertLoopbackURL(baseURL, label: "app backend")
        try assertLoopbackURL(bootstrapBaseURL, label: "bootstrap backend")
    }

    private func assertLoopbackURL(_ url: URL, label: String) throws {
        guard let host = url.host?.lowercased(),
            ["localhost", "127.0.0.1", "::1"].contains(host)
        else {
            throw NSError(
                domain: "PlaniniUITests",
                code: 2,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Refusing to run iOS UI tests against a non-local \(label) URL: \(url.absoluteString)"
                ]
            )
        }
    }

    private func bootstrapSession(email: String) throws -> UITestSession {
        let request = jsonRequest(
            path: "/api/v1/auth/ui-test-bootstrap",
            method: "POST",
            token: nil,
            body: ["email": email],
            baseURL: bootstrapBaseURL
        )
        let capturedData = try performRequest(request)
        return try JSONDecoder().decode(UITestSession.self, from: capturedData)
    }

    private func waitForCheckedItem(
        named itemName: String,
        inListNamed listName: String,
        accessToken: String,
        timeout: TimeInterval = 8
    ) -> Bool {
        waitForItemCheckedState(
            named: itemName,
            checked: true,
            inListNamed: listName,
            accessToken: accessToken,
            timeout: timeout
        )
    }

    private func waitForItemCheckedState(
        named itemName: String,
        checked: Bool,
        inListNamed listName: String,
        accessToken: String,
        timeout: TimeInterval = 8
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let items = try? fetchItems(inListNamed: listName, accessToken: accessToken),
                items.contains(where: { $0.name == itemName && $0.checked == checked })
            {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.35))
        }
        return false
    }

    private func waitForItem(
        named itemName: String,
        inListNamed listName: String,
        accessToken: String,
        timeout: TimeInterval = 8
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let items = try? fetchItems(inListNamed: listName, accessToken: accessToken),
                items.contains(where: { $0.name == itemName })
            {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.35))
        }
        return false
    }

    private func waitForItemAbsent(
        named itemName: String,
        inListNamed listName: String,
        accessToken: String,
        timeout: TimeInterval = 8
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let items = try? fetchItems(inListNamed: listName, accessToken: accessToken),
                items.contains(where: { $0.name == itemName }) == false
            {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.35))
        }
        return false
    }

    private func waitForItemCategory(
        named itemName: String,
        categoryNamed categoryName: String,
        inListNamed listName: String,
        accessToken: String,
        timeout: TimeInterval = 8
    ) -> Bool {
        guard
            let categoryID = try? categoryID(
                named: categoryName,
                inListNamed: listName,
                accessToken: accessToken
            )
        else {
            return false
        }

        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let items = try? fetchItems(inListNamed: listName, accessToken: accessToken),
                items.contains(where: { $0.name == itemName && $0.categoryID == categoryID })
            {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.35))
        }
        return false
    }

    private func waitForEditStatus(
        _ status: String,
        app: XCUIApplication,
        timeout: TimeInterval = 20
    ) -> Bool {
        let statusLabel = app.staticTexts["edit-item-save-status"]
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if statusLabel.exists && statusLabel.label.contains(status) {
                return true
            }
            if app.staticTexts[status].exists {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return (statusLabel.exists && statusLabel.label.contains(status)) || app.staticTexts[status].exists
    }

    private func waitForElementToDisappear(_ element: XCUIElement, timeout: TimeInterval = 8) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if element.exists == false {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return element.exists == false
    }

    private func waitForLiveUpdatesConnection(
        app: XCUIApplication,
        listName: String,
        accessToken: String,
        timeout: TimeInterval = 45
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let probeName = "A UI Live Ready \(UUID().uuidString.prefix(8))"
            if let probeID = try? createItem(
                named: probeName,
                note: "",
                inListNamed: listName,
                accessToken: accessToken
            ) {
                let appeared = waitForItemRow(itemID: probeID, named: probeName, in: app, timeout: 8)
                try? deleteItem(itemID: probeID, accessToken: accessToken)
                let disappeared = waitForElementToDisappear(
                    itemRow(itemID: probeID, in: app),
                    timeout: 8
                )
                if appeared && disappeared {
                    return true
                }
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }
        return false
    }

    private func openInitialListDetail(
        in app: XCUIApplication,
        listTitle: XCUIElement,
        timeout: TimeInterval = 45
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        let listsTab = app.tabBars.buttons["Lists"]
        let initialListRow = app.buttons["list-row-\(initialListName)"]

        while Date() < deadline {
            if listTitle.exists && listTitle.label == initialListName {
                return true
            }

            if listsTab.exists {
                guard tapTab("Lists", in: app) else {
                    RunLoop.current.run(until: Date().addingTimeInterval(0.5))
                    continue
                }
                returnToListsRootIfNeeded(app)
                if initialListRow.waitForExistence(timeout: 2) {
                    initialListRow.tap()
                    if listTitle.waitForExistence(timeout: 5), listTitle.label == initialListName {
                        return true
                    }
                }
            }

            RunLoop.current.run(until: Date().addingTimeInterval(0.5))
        }

        return listTitle.exists && listTitle.label == initialListName
    }

    private func tapTab(_ label: String, in app: XCUIApplication, timeout: TimeInterval = 5) -> Bool {
        let tabButton = app.tabBars.buttons[label]
        guard tabButton.waitForExistence(timeout: timeout) else {
            return false
        }
        tapElement(tabButton)
        return true
    }

    private func chooseCategory(
        named categoryName: String,
        using linkIdentifier: String,
        in app: XCUIApplication,
        searchText: String?,
        sortOption: String?,
        screenshotName: String?
    ) {
        let link = app.buttons[linkIdentifier]
        scrollToHittable(link, in: app)
        XCTAssertTrue(link.waitForExistence(timeout: 3))
        tapElement(link)

        let categoryScreen = app.descendants(matching: .any)["category-selection-screen"]
        XCTAssertTrue(categoryScreen.waitForExistence(timeout: 3))
        XCTAssertTrue(app.textFields["category-search-field"].waitForExistence(timeout: 3))

        if let sortOption {
            let option = firstExistingElement(
                [
                    app.buttons[sortOption],
                    app.segmentedControls.buttons[sortOption],
                    app.staticTexts[sortOption],
                ],
                timeout: 3
            )
            XCTAssertTrue(option.waitForExistence(timeout: 3))
            tapElement(option)
        }

        if let searchText {
            let searchField = app.textFields["category-search-field"]
            searchField.tap()
            searchField.typeText(searchText)
        }

        let categoryOption = app.buttons["category-option-\(categoryName)"]
        XCTAssertTrue(categoryOption.waitForExistence(timeout: 3))
        if let screenshotName {
            captureScreenshot(named: screenshotName)
        }
        tapElement(categoryOption)
        XCTAssertTrue(waitForElementToDisappear(categoryScreen, timeout: 3))
    }

    private func selectAppearanceMode(_ label: String, in app: XCUIApplication) {
        let picker = app.segmentedControls["settings-appearance-picker"]
        XCTAssertTrue(picker.waitForExistence(timeout: 5))
        let option = picker.buttons[label]
        XCTAssertTrue(option.waitForExistence(timeout: 3))
        tapElement(option)
    }

    private func assertAppearanceMode(
        _ label: String,
        in app: XCUIApplication,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        let picker = app.segmentedControls["settings-appearance-picker"]
        XCTAssertTrue(picker.waitForExistence(timeout: 5), file: file, line: line)
        let option = picker.buttons[label]
        XCTAssertTrue(option.waitForExistence(timeout: 3), file: file, line: line)
        XCTAssertTrue(
            option.isSelected || picker.valueText == label,
            "Expected \(label) appearance mode to be selected.",
            file: file,
            line: line
        )
    }

    private func tapElement(_ element: XCUIElement) {
        if element.isHittable {
            element.tap()
        } else {
            element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        }
    }

    private func waitForItemRow(
        itemID: UUID,
        named itemName: String,
        in app: XCUIApplication,
        timeout: TimeInterval
    ) -> Bool {
        let row = itemRow(itemID: itemID, in: app)
        let label = app.staticTexts[itemName]
        let deadline = Date().addingTimeInterval(timeout)

        while Date() < deadline {
            if row.exists && label.exists {
                return true
            }
            app.swipeDown()
            if row.exists && label.exists {
                return true
            }
            app.swipeUp()
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return row.exists && label.exists
    }

    private func itemRow(itemID: UUID, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)["item-row-\(itemID.uuidString)"]
    }

    private func scrollToElement(_ element: XCUIElement, in app: XCUIApplication, maxSwipes: Int = 10) {
        for _ in 0..<maxSwipes {
            if element.exists {
                return
            }
            app.swipeUp()
        }
    }

    private func scrollToHittable(_ element: XCUIElement, in app: XCUIApplication, maxSwipes: Int = 6) {
        for _ in 0..<maxSwipes {
            if element.exists && element.isHittable {
                return
            }
            app.swipeUp()
        }
    }

    private func assertReviewerOnboardingAvailable(in app: XCUIApplication) {
        let helpMenu = app.buttons["login-help-menu"]
        XCTAssertTrue(helpMenu.waitForExistence(timeout: 3))
        helpMenu.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()

        let helpButton = firstExistingElement(
            [
                app.buttons["login-help-trouble-button"],
                app.buttons["Having trouble signing in?"],
                app.menuItems["Having trouble signing in?"],
                app.buttons.containing(NSPredicate(format: "label CONTAINS %@", "trouble signing in")).firstMatch,
            ],
            timeout: 3
        )
        XCTAssertTrue(helpButton.waitForExistence(timeout: 3))
        helpButton.tap()

        XCTAssertTrue(app.otherElements["reviewer-onboarding-sheet"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.textFields["passkey-add-link-field"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.textFields["registration-display-name-field"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.textFields["registration-email-field"].waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-reviewer-onboarding")

        let passkeyField = app.textFields["passkey-add-link-field"]
        passkeyField.tap()
        passkeyField.typeText("\(baseURL.absoluteString)/passkey-add/missing-reviewer-token")
        XCTAssertTrue(app.buttons["passkey-add-submit-button"].isEnabled)

        let nameField = app.textFields["registration-display-name-field"]
        nameField.tap()
        nameField.typeText("App Reviewer")
        let emailField = app.textFields["registration-email-field"]
        emailField.tap()
        emailField.typeText("reviewer@example.com")
        XCTAssertTrue(app.buttons["registration-submit-button"].isEnabled)

        app.buttons["Cancel"].tap()
        XCTAssertFalse(app.otherElements["reviewer-onboarding-sheet"].exists)
    }

    private func firstExistingElement(_ elements: [XCUIElement], timeout: TimeInterval) -> XCUIElement {
        for element in elements {
            if element.waitForExistence(timeout: timeout) {
                return element
            }
        }
        return elements.first ?? XCUIApplication().buttons.firstMatch
    }

    private func fetchItems(inListNamed listName: String, accessToken: String) throws -> [UITestItem] {
        let householdRequest = jsonRequest(
            path: "/api/v1/households",
            method: "GET",
            token: accessToken
        )
        let householdData = try performRequest(householdRequest)
        let households = try JSONDecoder().decode([UITestHousehold].self, from: householdData)

        for household in households {
            let listsRequest = jsonRequest(
                path: "/api/v1/households/\(household.id.uuidString)/lists",
                method: "GET",
                token: accessToken
            )
            let listData = try performRequest(listsRequest)
            let lists = try JSONDecoder().decode([UITestList].self, from: listData)
            guard let matchingList = lists.first(where: { $0.name == listName }) else {
                continue
            }

            let itemsRequest = jsonRequest(
                path: "/api/v1/lists/\(matchingList.id.uuidString)/items",
                method: "GET",
                token: accessToken
            )
            let itemData = try performRequest(itemsRequest)
            return try JSONDecoder().decode([UITestItem].self, from: itemData)
        }

        return []
    }

    private func itemID(named itemName: String, inListNamed listName: String, accessToken: String) throws -> UUID {
        if let item = try fetchItems(inListNamed: listName, accessToken: accessToken)
            .first(where: { $0.name == itemName })
        {
            return item.id
        }
        throw NSError(
            domain: "PlaniniUITests",
            code: 1,
            userInfo: [NSLocalizedDescriptionKey: "Could not find item named \(itemName)."]
        )
    }

    private func categoryID(named categoryName: String, inListNamed listName: String, accessToken: String) throws -> UUID {
        let listID = try listID(named: listName, accessToken: accessToken)
        if let category = try fetchCategories(listID: listID, accessToken: accessToken)
            .first(where: { $0.name == categoryName })
        {
            return category.id
        }
        throw NSError(
            domain: "PlaniniUITests",
            code: 5,
            userInfo: [NSLocalizedDescriptionKey: "Could not find category named \(categoryName)."]
        )
    }

    private func fetchCategories(listID: UUID, accessToken: String) throws -> [UITestCategory] {
        let request = jsonRequest(
            path: "/api/v1/lists/\(listID.uuidString)/categories",
            method: "GET",
            token: accessToken
        )
        let data = try performRequest(request)
        return try JSONDecoder().decode([UITestCategory].self, from: data)
    }

    private func createItem(
        named name: String,
        note: String,
        inListNamed listName: String,
        accessToken: String
    ) throws -> UUID {
        let listID = try listID(named: listName, accessToken: accessToken)
        let request = jsonRequest(
            path: "/api/v1/lists/\(listID.uuidString)/items",
            method: "POST",
            token: accessToken,
            body: [
                "name": name,
                "quantity_text": NSNull(),
                "note": note,
                "category_id": NSNull(),
                "sort_order": -1_000,
            ]
        )
        let data = try performRequest(request)
        let item = try JSONDecoder().decode(UITestIdentifiedItem.self, from: data)
        return item.id
    }

    private func updateItem(
        itemID: UUID,
        name: String,
        note: String,
        accessToken: String
    ) throws {
        let request = jsonRequest(
            path: "/api/v1/items/\(itemID.uuidString)",
            method: "PATCH",
            token: accessToken,
            body: [
                "name": name,
                "note": note,
            ]
        )
        _ = try performRequest(request)
    }

    private func deleteItem(itemID: UUID, accessToken: String) throws {
        let request = jsonRequest(
            path: "/api/v1/items/\(itemID.uuidString)",
            method: "DELETE",
            token: accessToken
        )
        _ = try performRequest(request)
    }

    private func listID(named listName: String, accessToken: String) throws -> UUID {
        let householdRequest = jsonRequest(
            path: "/api/v1/households",
            method: "GET",
            token: accessToken
        )
        let householdData = try performRequest(householdRequest)
        let households = try JSONDecoder().decode([UITestHousehold].self, from: householdData)

        for household in households {
            let listsRequest = jsonRequest(
                path: "/api/v1/households/\(household.id.uuidString)/lists",
                method: "GET",
                token: accessToken
            )
            let listData = try performRequest(listsRequest)
            let lists = try JSONDecoder().decode([UITestList].self, from: listData)
            if let matchingList = lists.first(where: { $0.name == listName }) {
                return matchingList.id
            }
        }

        throw NSError(
            domain: "PlaniniUITests",
            code: 4,
            userInfo: [NSLocalizedDescriptionKey: "Could not find seeded list named \(listName)."]
        )
    }

    private func jsonRequest(
        path: String,
        method: String,
        token: String?,
        body: [String: Any]? = nil,
        baseURL overrideBaseURL: URL? = nil
    ) -> URLRequest {
        let targetBaseURL = overrideBaseURL ?? baseURL
        var request = URLRequest(url: targetBaseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpMethod = method
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        return request
    }

    private func performRequest(_ request: URLRequest) throws -> Data {
        var lastError: Error?
        for attempt in 1...3 {
            do {
                return try performSingleRequest(request)
            } catch {
                lastError = error
                guard isTransientNetworkError(error), attempt < 3 else {
                    throw error
                }
                RunLoop.current.run(until: Date().addingTimeInterval(0.4 * Double(attempt)))
            }
        }

        throw lastError ?? NSError(domain: "PlaniniUITests", code: 1, userInfo: [NSLocalizedDescriptionKey: "Missing response"])
    }

    private func performSingleRequest(_ request: URLRequest) throws -> Data {
        let semaphore = DispatchSemaphore(value: 0)
        var capturedData: Data?
        var capturedError: Error?
        URLSession.shared.dataTask(with: request) { data, _, error in
            capturedData = data
            capturedError = error
            semaphore.signal()
        }.resume()
        let waitResult = semaphore.wait(timeout: .now() + 10)

        if let capturedError {
            throw capturedError
        }
        if waitResult == .timedOut {
            throw NSError(
                domain: "PlaniniUITests",
                code: 3,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Timed out waiting for response from \(request.url?.absoluteString ?? "unknown request")"
                ]
            )
        }
        guard let capturedData else {
            throw NSError(domain: "PlaniniUITests", code: 1, userInfo: [NSLocalizedDescriptionKey: "Missing bootstrap response"])
        }
        return capturedData
    }

    private func isTransientNetworkError(_ error: Error) -> Bool {
        let nsError = error as NSError
        guard nsError.domain == NSURLErrorDomain else {
            return false
        }
        return [
            NSURLErrorNetworkConnectionLost,
            NSURLErrorTimedOut,
            NSURLErrorCannotConnectToHost,
        ].contains(nsError.code)
    }

    private func returnToListsRootIfNeeded(_ app: XCUIApplication) {
        if app.buttons["list-row-\(initialListName)"].waitForExistence(timeout: 1) {
            return
        }

        let backButton = app.navigationBars.buttons.firstMatch
        if backButton.exists {
            backButton.tap()
        }
    }

    private func captureScreenshot(named name: String) {
        let screenshot = XCUIScreen.main.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)

        let directoryURL = screenshotArtifactDirectory()
        try? FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let fileURL = directoryURL.appending(path: "\(name).png")
        try? screenshot.pngRepresentation.write(to: fileURL)
    }

    private func screenshotArtifactDirectory() -> URL {
        if let artifactDirectory = ProcessInfo.processInfo.environment["PLANINI_UI_TEST_ARTIFACT_DIR"],
            artifactDirectory.isEmpty == false
        {
            return URL(fileURLWithPath: artifactDirectory, isDirectory: true)
        }

        return URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appending(path: "e2e-artifacts/ios-ui-e2e", directoryHint: .isDirectory)
    }

}

private struct UITestSession: Decodable {
    let accessToken: String
    let displayName: String

    private enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case displayName = "display_name"
    }
}

private struct UITestHousehold: Decodable {
    let id: UUID
}

private struct UITestList: Decodable {
    let id: UUID
    let name: String
}

private struct UITestCategory: Decodable {
    let id: UUID
    let name: String
}

private struct UITestItem: Decodable {
    let id: UUID
    let name: String
    let checked: Bool
    let categoryID: UUID?

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case checked
        case categoryID = "category_id"
    }
}

private struct UITestIdentifiedItem: Decodable {
    let id: UUID
}

private extension XCUIElement {
    var valueText: String {
        value as? String ?? ""
    }
}
