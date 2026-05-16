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

        app.launch()

        let listTitle = app.staticTexts["list-detail-title"]
        XCTAssertTrue(
            openInitialListDetail(in: app, listTitle: listTitle),
            "Expected bootstrapped initial list to open."
        )
        app.tabBars.buttons["Lists"].tap()
        let initialListRow = app.buttons["list-row-\(initialListName)"]
        XCTAssertTrue(initialListRow.waitForExistence(timeout: 10))
        captureScreenshot(named: "promotion-list-of-lists")
        initialListRow.tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-list-detail")

        XCTAssertTrue(app.staticTexts["Uncategorized"].waitForExistence(timeout: 3))
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
        app.tabBars.buttons[initialListName].tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-favorite-list")

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-add-item-sheet")

        let uniqueSuffix = UUID().uuidString.prefix(8)
        let itemName = "UI Test Herbs \(uniqueSuffix)"
        let itemQuantity = "1 bunch"
        let updatedName = "\(itemName) Updated"

        let nameField = app.textFields["add-item-name-field"]
        XCTAssertTrue(nameField.waitForExistence(timeout: 3))
        nameField.tap()
        nameField.typeText(itemName)

        let quantityField = app.textFields["add-item-quantity-field"]
        quantityField.tap()
        quantityField.typeText(itemQuantity)

        let noteField = app.textFields["add-item-note-field"]
        noteField.tap()
        noteField.typeText("for pasta")

        app.buttons["add-item-save-button"].tap()
        XCTAssertTrue(app.staticTexts[itemName].waitForExistence(timeout: 5))
        captureScreenshot(named: "ios-ui-added-item")

        app.staticTexts[itemName].tap()
        XCTAssertTrue(app.otherElements["edit-item-sheet"].waitForExistence(timeout: 3))
        captureScreenshot(named: "promotion-edit-item-dialogue")

        let editNameField = app.textFields["edit-item-name-field"]
        editNameField.tap()
        editNameField.typeText(" Updated")
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(updatedName))

        app.buttons["edit-item-undo-button"].tap()
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(itemName))
        XCTAssertFalse(editNameField.valueText.contains("Updated"))

        app.buttons["edit-item-redo-button"].tap()
        XCTAssertTrue(waitForEditStatus("Saved", app: app))
        XCTAssertTrue(editNameField.valueText.contains(updatedName))
        captureScreenshot(named: "ios-ui-live-edit-autosave")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.staticTexts[updatedName].waitForExistence(timeout: 5))
        XCTAssertTrue(
            waitForItem(
                named: updatedName,
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )

        app.buttons["Check \(updatedName)"].tap()
        XCTAssertTrue(
            waitForCheckedItem(
                named: updatedName,
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )
        scrollToElement(app.staticTexts[updatedName], in: app)
        captureScreenshot(named: "ios-ui-checked-item")
        captureScreenshot(named: "promotion-filled-list")

        app.tabBars.buttons["Lists"].tap()
        returnToListsRootIfNeeded(app)
        let hostingListRow = app.buttons["list-row-Hosting errands"]
        XCTAssertTrue(hostingListRow.waitForExistence(timeout: 10))
        hostingListRow.tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, "Hosting errands")
        captureScreenshot(named: "ios-ui-list-switcher")

        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.buttons["settings-sign-out-button"].waitForExistence(timeout: 5))
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
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let items = try? fetchItems(inListNamed: listName, accessToken: accessToken),
                items.contains(where: { $0.name == itemName && $0.checked })
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

    private func waitForEditStatus(
        _ status: String,
        app: XCUIApplication,
        timeout: TimeInterval = 8
    ) -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if app.staticTexts[status].exists {
                return true
            }
            RunLoop.current.run(until: Date().addingTimeInterval(0.25))
        }
        return app.staticTexts[status].exists
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
        timeout: TimeInterval = 20
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
                let appeared = waitForItemRow(itemID: probeID, named: probeName, in: app, timeout: 3)
                try? deleteItem(itemID: probeID, accessToken: accessToken)
                let disappeared = waitForElementToDisappear(
                    itemRow(itemID: probeID, in: app),
                    timeout: 5
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
                listsTab.tap()
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

private struct UITestItem: Decodable {
    let name: String
    let checked: Bool
}

private struct UITestIdentifiedItem: Decodable {
    let id: UUID
}

private extension XCUIElement {
    var valueText: String {
        value as? String ?? ""
    }
}
