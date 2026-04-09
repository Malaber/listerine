import XCTest

final class ListerineUITests: XCTestCase {
    private let seededEmail = "listerine@schaedler.rocks"
    private let initialListName = "Browser Test Shop"

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testListViewFlow() throws {
        try assertLocalTestBackend()
        let session = try bootstrapSession(email: userEmail)
        let app = XCUIApplication()
        app.launchEnvironment["LISTERINE_UI_TEST_MODE"] = "1"
        app.launchEnvironment["LISTERINE_BACKEND_BASE_URL_OVERRIDE"] = baseURL.absoluteString
        app.launchEnvironment["LISTERINE_UI_TEST_ACCESS_TOKEN"] = session.accessToken
        app.launchEnvironment["LISTERINE_UI_TEST_DISPLAY_NAME"] = session.displayName
        app.launchEnvironment["LISTERINE_UI_TEST_INITIAL_LIST_NAME"] = initialListName

        app.launch()

        let listTitle = app.staticTexts["list-detail-title"]
        XCTAssertTrue(listTitle.waitForExistence(timeout: 10))
        app.tabBars.buttons["Lists"].tap()
        XCTAssertTrue(app.navigationBars["Lists"].waitForExistence(timeout: 5))
        app.buttons["list-row-\(initialListName)"].tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-list-detail")

        XCTAssertTrue(app.staticTexts["Uncategorized"].waitForExistence(timeout: 3))
        if app.buttons["favorite-list-button"].exists {
            app.buttons["favorite-list-button"].tap()
        }

        app.tabBars.buttons["Favorite"].tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, initialListName)
        captureScreenshot(named: "ios-ui-favorite-list")

        app.buttons["add-item-button"].tap()
        XCTAssertTrue(app.otherElements["add-item-sheet"].waitForExistence(timeout: 3))
        captureScreenshot(named: "ios-ui-add-item-sheet")

        let itemName = "UI Test Fresh Herbs"
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

        let editNameField = app.textFields["edit-item-name-field"]
        editNameField.tap()
        editNameField.typeText(" Updated")
        app.buttons["edit-item-save-button"].tap()
        XCTAssertTrue(app.staticTexts[updatedName].waitForExistence(timeout: 5))

        app.buttons["Check \(updatedName)"].tap()
        XCTAssertTrue(
            waitForCheckedItem(
                named: updatedName,
                inListNamed: initialListName,
                accessToken: session.accessToken
            )
        )
        captureScreenshot(named: "ios-ui-checked-item")

        app.tabBars.buttons["Lists"].tap()
        returnToListsRootIfNeeded(app)
        XCTAssertTrue(app.navigationBars["Lists"].waitForExistence(timeout: 5))
        app.buttons["list-row-Hosting errands"].tap()
        XCTAssertTrue(listTitle.waitForExistence(timeout: 5))
        XCTAssertEqual(listTitle.label, "Hosting errands")
        captureScreenshot(named: "ios-ui-list-switcher")

        app.tabBars.buttons["Settings"].tap()
        XCTAssertTrue(app.buttons["settings-sign-out-button"].waitForExistence(timeout: 5))
        captureScreenshot(named: "ios-ui-settings")
    }

    private var baseURL: URL {
        if
            let value = ProcessInfo.processInfo.environment["LISTERINE_UI_TEST_BASE_URL"],
            let url = URL(string: value)
        {
            return url
        }
        return URL(string: "http://127.0.0.1:8018")!
    }

    private var userEmail: String {
        guard let configuredEmail = ProcessInfo.processInfo.environment["LISTERINE_UI_TEST_USER_EMAIL"],
            configuredEmail.isEmpty == false
        else {
            return seededEmail
        }
        return configuredEmail
    }

    private func assertLocalTestBackend() throws {
        guard let host = baseURL.host?.lowercased(),
            ["localhost", "127.0.0.1", "::1"].contains(host)
        else {
            throw NSError(
                domain: "ListerineUITests",
                code: 2,
                userInfo: [
                    NSLocalizedDescriptionKey:
                        "Refusing to run iOS UI tests against a non-local backend URL: \(baseURL.absoluteString)"
                ]
            )
        }
    }

    private func bootstrapSession(email: String) throws -> UITestSession {
        let request = jsonRequest(
            path: "/api/v1/auth/ui-test-bootstrap",
            method: "POST",
            token: nil,
            body: ["email": email]
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

    private func jsonRequest(
        path: String,
        method: String,
        token: String?,
        body: [String: Any]? = nil
    ) -> URLRequest {
        var request = URLRequest(url: baseURL.appending(path: path))
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
        _ = semaphore.wait(timeout: .now() + 10)

        if let capturedError {
            throw capturedError
        }
        guard let capturedData else {
            throw NSError(domain: "ListerineUITests", code: 1, userInfo: [NSLocalizedDescriptionKey: "Missing bootstrap response"])
        }
        return capturedData
    }

    private func returnToListsRootIfNeeded(_ app: XCUIApplication) {
        if app.navigationBars["Lists"].waitForExistence(timeout: 1) {
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

        guard let artifactDirectory = ProcessInfo.processInfo.environment["LISTERINE_UI_TEST_ARTIFACT_DIR"] else {
            return
        }
        let directoryURL = URL(fileURLWithPath: artifactDirectory, isDirectory: true)
        try? FileManager.default.createDirectory(at: directoryURL, withIntermediateDirectories: true)
        let fileURL = directoryURL.appending(path: "\(name).png")
        try? screenshot.pngRepresentation.write(to: fileURL)
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
