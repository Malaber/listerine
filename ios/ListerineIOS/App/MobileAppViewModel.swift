import Foundation
import ListerineCore
import os.log

private let netLog = Logger(subsystem: "com.example.ListerineIOS", category: "network")

private enum AppBuildConfiguration {
    private static let backendURLKey = "ListerineBackendBaseURL"
    private static let backendURLOverrideKey = "LISTERINE_BACKEND_BASE_URL_OVERRIDE"

    static var backendURL: URL? {
        if let overriddenURL = validatedURL(from: ProcessInfo.processInfo.environment[backendURLOverrideKey]) {
            return overriddenURL
        }
        if let generatedURL = validatedURL(from: GeneratedBuildConfiguration.backendURL) {
            return generatedURL
        }
        return validatedURL(
            from: Bundle.main.object(forInfoDictionaryKey: backendURLKey) as? String
        )
    }

    private static func validatedURL(from rawValue: String?) -> URL? {
        guard
            let rawValue,
            let url = URL(string: rawValue),
            let scheme = url.scheme?.lowercased(),
            ["http", "https"].contains(scheme),
            url.host != nil
        else {
            return nil
        }
        return url
    }
}

@MainActor
final class MobileAppViewModel: ObservableObject {
    private static let favoriteListKey = "listerine.favoriteListID"
    private static let authTokenKey = "listerine.authToken"
    private static let displayNameKey = "listerine.displayName"
    private static let quickAddItemKey = "listerine.quickAddItemName"

    @Published private(set) var backendURL: URL?
    @Published private(set) var isAuthenticating = false
    @Published private(set) var authToken: String?
    @Published private(set) var displayName: String?
    @Published private(set) var lists: [GroceryListSummary] = []
    @Published private(set) var items: [GroceryItemRecord] = []
    @Published private(set) var categories: [GroceryCategorySummary] = []
    @Published private(set) var categoryOrder: [ListCategoryOrderEntry] = []
    @Published var selectedListID: UUID?
    @Published private(set) var favoriteListID: UUID?
    @Published var quickAddItemName: String
    @Published var errorMessage: String?

    private let passkeyClient: ApplePasskeyClient
    private let userDefaults: UserDefaults
    private let processInfo: ProcessInfo
    private let watchSyncCoordinator: WatchSyncCoordinator
    private let isSimulatorBuild: Bool
    private var didAttemptLaunchBootstrap = false

    init(
        passkeyClient: ApplePasskeyClient = ApplePasskeyClient(),
        userDefaults: UserDefaults = .standard,
        processInfo: ProcessInfo = .processInfo,
        watchSyncCoordinator: WatchSyncCoordinator = .shared
    ) {
        self.passkeyClient = passkeyClient
        self.userDefaults = userDefaults
        self.processInfo = processInfo
        self.watchSyncCoordinator = watchSyncCoordinator
        #if targetEnvironment(simulator)
            isSimulatorBuild = true
        #else
            isSimulatorBuild = false
        #endif
        backendURL = AppBuildConfiguration.backendURL
        if processInfo.environment["LISTERINE_UI_TEST_MODE"] == "1" {
            favoriteListID = nil
            authToken = nil
            displayName = nil
            quickAddItemName = SharedAppState.defaultQuickAddItemName
        } else {
            favoriteListID = userDefaults.string(forKey: Self.favoriteListKey).flatMap(UUID.init(uuidString:))
            authToken = userDefaults.string(forKey: Self.authTokenKey)
            displayName = userDefaults.string(forKey: Self.displayNameKey)
            quickAddItemName = userDefaults.string(forKey: Self.quickAddItemKey) ?? SharedAppState.defaultQuickAddItemName
        }
        watchSyncCoordinator.setStateProvider { [weak self] in
            self?.makeSharedAppState() ?? SharedAppState()
        }
        watchSyncCoordinator.publishCurrentState()
    }

    var backendDisplayName: String {
        backendURL?.host ?? backendURL?.absoluteString ?? "Not configured"
    }

    var selectedList: GroceryListSummary? {
        lists.first { $0.id == selectedListID }
    }

    var favoriteList: GroceryListSummary? {
        lists.first { $0.id == favoriteListID }
    }

    var availableCategories: [GroceryCategorySummary] {
        categories.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var sections: [GroceryItemSection] {
        GroceryItemSectionBuilder.build(
            items: items,
            categories: categories,
            categoryOrder: categoryOrder
        )
    }

    var isRunningUITests: Bool {
        processInfo.environment["LISTERINE_UI_TEST_MODE"] == "1"
    }

    func loginWithPasskey() async {
        guard let backendURL else {
            errorMessage = "This build is missing a backend URL configuration."
            return
        }

        netLog.debug("Starting passkey login flow for backend: \(backendURL.absoluteString, privacy: .public)")
        isAuthenticating = true
        defer { isAuthenticating = false }

        do {
            try await ensureBackendReady(backendURL: backendURL)
            let options = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/login/options",
                method: "POST",
                body: [:],
                token: nil
            )
            let relyingPartyIdentifier = rpID(from: options) ?? backendURL.host ?? ""
            let credential = try await passkeyClient.authenticate(
                optionsPayload: options,
                relyingPartyIdentifier: relyingPartyIdentifier
            )
            let tokenJson = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/login/verify",
                method: "POST",
                body: ["credential": credential],
                token: nil
            )

            guard let accessToken = tokenJson["access_token"] as? String else {
                throw AppError.invalidResponse
            }

            authToken = accessToken
            userDefaults.set(accessToken, forKey: Self.authTokenKey)

            let me = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/me",
                method: "GET",
                body: nil,
                token: accessToken
            )
            displayName = me["display_name"] as? String
            userDefaults.set(displayName, forKey: Self.displayNameKey)
            try await reloadAllData()
            errorMessage = nil
            watchSyncCoordinator.publishCurrentState()
        } catch {
            let nsErr = error as NSError
            netLog.error("Passkey login failed. Type=\(String(describing: type(of: error)), privacy: .public) Domain=\(nsErr.domain, privacy: .public) Code=\(nsErr.code) Desc=\(nsErr.localizedDescription, privacy: .public)")
            errorMessage = nsErr.localizedDescription
        }
    }

    func bootstrapLaunchSessionIfNeeded() async {
        guard didAttemptLaunchBootstrap == false else { return }
        didAttemptLaunchBootstrap = true

        let environment = processInfo.environment
        do {
            if
                environment["LISTERINE_UI_TEST_MODE"] == "1",
                let accessToken = environment["LISTERINE_UI_TEST_ACCESS_TOKEN"],
                accessToken.isEmpty == false
            {
                try await applyBootstrappedSession(
                    accessToken: accessToken,
                    displayNameOverride: environment["LISTERINE_UI_TEST_DISPLAY_NAME"],
                    preferredListName: environment["LISTERINE_UI_TEST_INITIAL_LIST_NAME"]
                )
                return
            }

            if
                isSimulatorBuild,
                let bootstrapEmail = environment["LISTERINE_SIMULATOR_BOOTSTRAP_EMAIL"]?.trimmingCharacters(in: .whitespacesAndNewlines),
                bootstrapEmail.isEmpty == false
            {
                try await bootstrapSimulatorSession(
                    email: bootstrapEmail,
                    preferredListName: environment["LISTERINE_SIMULATOR_INITIAL_LIST_NAME"]
                )
            }
        } catch {
            authToken = nil
            userDefaults.removeObject(forKey: Self.authTokenKey)
            errorMessage = error.localizedDescription
        }
    }

    private func bootstrapSimulatorSession(email: String, preferredListName: String?) async throws {
        guard let backendURL else {
            throw AppError.invalidResponse
        }

        let payload = try await requestJSON(
            backendURL: backendURL,
            path: "/api/v1/auth/ui-test-bootstrap",
            method: "POST",
            body: ["email": email],
            token: nil
        )

        guard let accessToken = payload["access_token"] as? String else {
            throw AppError.invalidResponse
        }

        try await applyBootstrappedSession(
            accessToken: accessToken,
            displayNameOverride: payload["display_name"] as? String,
            preferredListName: preferredListName
        )
    }

    private func applyBootstrappedSession(
        accessToken: String,
        displayNameOverride: String?,
        preferredListName: String?
    ) async throws {
        authToken = accessToken
        userDefaults.set(accessToken, forKey: Self.authTokenKey)

        if let backendURL {
            let me = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/me",
                method: "GET",
                body: nil,
                token: accessToken
            )
            displayName = me["display_name"] as? String
        } else if let displayNameOverride, displayNameOverride.isEmpty == false {
            displayName = displayNameOverride
        }

        userDefaults.set(displayName, forKey: Self.displayNameKey)

        try await reloadAllData()

        if
            let preferredListName = preferredListName?.trimmingCharacters(in: .whitespacesAndNewlines),
            preferredListName.isEmpty == false,
            let matchingList = lists.first(where: { $0.name == preferredListName })
        {
            selectedListID = matchingList.id
            setFavoriteList(id: matchingList.id)
            try await reloadItems()
        }

        errorMessage = nil
        watchSyncCoordinator.publishCurrentState()
    }

    func signOut() {
        authToken = nil
        displayName = nil
        lists = []
        items = []
        categories = []
        categoryOrder = []
        selectedListID = nil
        errorMessage = nil
        userDefaults.removeObject(forKey: Self.authTokenKey)
        userDefaults.removeObject(forKey: Self.displayNameKey)
        watchSyncCoordinator.publishCurrentState()
    }

    func showFavoriteList() async {
        let targetID = favoriteListID ?? lists.first?.id
        guard let targetID else { return }
        await selectList(id: targetID)
    }

    func setFavoriteList(id: UUID) {
        favoriteListID = id
        userDefaults.set(id.uuidString, forKey: Self.favoriteListKey)
        watchSyncCoordinator.publishCurrentState()
    }

    func updateQuickAddItemName(_ rawValue: String) {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        quickAddItemName = trimmed.isEmpty ? SharedAppState.defaultQuickAddItemName : trimmed
        userDefaults.set(quickAddItemName, forKey: Self.quickAddItemKey)
        watchSyncCoordinator.publishCurrentState()
    }

    func reloadAllData() async throws {
        guard let backendURL, let authToken else { return }

        let households = try await requestArray(
            backendURL: backendURL,
            path: "/api/v1/households",
            token: authToken
        )

        var loadedLists: [GroceryListSummary] = []
        for household in households {
            guard
                let householdIDText = household["id"] as? String,
                let householdID = UUID(uuidString: householdIDText),
                let householdName = household["name"] as? String
            else {
                continue
            }

            let householdLists = try await requestArray(
                backendURL: backendURL,
                path: "/api/v1/households/\(householdID.uuidString)/lists",
                token: authToken
            )

            loadedLists.append(
                contentsOf: householdLists.compactMap { listJSON in
                    guard
                        let idText = listJSON["id"] as? String,
                        let id = UUID(uuidString: idText),
                        let name = listJSON["name"] as? String
                    else {
                        return nil
                    }

                    return GroceryListSummary(
                        id: id,
                        householdID: householdID,
                        householdName: householdName,
                        name: name,
                        archived: (listJSON["archived"] as? Bool) ?? false
                    )
                }
            )
        }

        lists = loadedLists.sorted {
            if $0.householdName != $1.householdName {
                return $0.householdName.localizedCaseInsensitiveCompare($1.householdName) == .orderedAscending
            }
            return $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
        }

        if let favoriteListID, lists.contains(where: { $0.id == favoriteListID }) == false {
            self.favoriteListID = nil
            userDefaults.removeObject(forKey: Self.favoriteListKey)
        }

        if favoriteListID == nil, let firstListID = lists.first?.id {
            setFavoriteList(id: firstListID)
        }

        if let selectedListID, lists.contains(where: { $0.id == selectedListID }) == false {
            self.selectedListID = nil
        }

        if selectedListID == nil {
            selectedListID = favoriteListID ?? lists.first?.id
        }

        try await reloadItems()
        watchSyncCoordinator.publishCurrentState()
    }

    func selectList(id: UUID) async {
        guard selectedListID != id else { return }
        selectedListID = id
        try? await reloadItems()
    }

    func reloadItems() async throws {
        guard let backendURL, let authToken, let selectedListID else {
            items = []
            categories = []
            categoryOrder = []
            return
        }

        async let itemPayload = requestArray(
            backendURL: backendURL,
            path: "/api/v1/lists/\(selectedListID.uuidString)/items",
            token: authToken
        )
        async let categoryPayload = requestArray(
            backendURL: backendURL,
            path: "/api/v1/lists/\(selectedListID.uuidString)/categories",
            token: authToken
        )
        async let categoryOrderPayload = requestArray(
            backendURL: backendURL,
            path: "/api/v1/lists/\(selectedListID.uuidString)/category-order",
            token: authToken
        )

        items = try await itemPayload.compactMap(GroceryItemRecord.init)
        categories = try await categoryPayload.compactMap(GroceryCategorySummary.init)
        categoryOrder = try await categoryOrderPayload.compactMap(ListCategoryOrderEntry.init)
        watchSyncCoordinator.publishCurrentState()
    }

    @discardableResult
    func addItem(name: String, quantity: String, note: String, categoryID: UUID?) async -> Bool {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let backendURL, let authToken, let selectedListID, trimmed.isEmpty == false else {
            return false
        }

        var body: [String: Any] = ["name": trimmed]
        body["quantity_text"] = quantity.isEmpty ? NSNull() : quantity
        body["note"] = note.isEmpty ? NSNull() : note
        body["category_id"] = categoryID?.uuidString ?? NSNull()

        do {
            _ = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/lists/\(selectedListID.uuidString)/items",
                method: "POST",
                body: body,
                token: authToken
            )
            try await reloadItems()
            watchSyncCoordinator.publishCurrentState()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func toggle(_ item: GroceryItemRecord) async -> Bool {
        guard let backendURL, let authToken else { return false }
        let suffix = item.checked ? "uncheck" : "check"
        do {
            _ = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/items/\(item.id.uuidString)/\(suffix)",
                method: "POST",
                body: [:],
                token: authToken
            )
            try await reloadItems()
            watchSyncCoordinator.publishCurrentState()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func saveEdit(
        item: GroceryItemRecord,
        name: String,
        quantity: String,
        note: String,
        categoryID: UUID?
    ) async -> Bool {
        guard let backendURL, let authToken else { return false }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else { return false }

        do {
            _ = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/items/\(item.id.uuidString)",
                method: "PATCH",
                body: [
                    "name": trimmed,
                    "quantity_text": quantity.isEmpty ? NSNull() : quantity,
                    "note": note.isEmpty ? NSNull() : note,
                    "category_id": categoryID?.uuidString ?? NSNull()
                ],
                token: authToken
            )
            try await reloadItems()
            watchSyncCoordinator.publishCurrentState()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func delete(item: GroceryItemRecord) async -> Bool {
        guard let backendURL, let authToken else { return false }

        do {
            _ = try await requestData(
                backendURL: backendURL,
                path: "/api/v1/items/\(item.id.uuidString)",
                method: "DELETE",
                body: nil,
                token: authToken
            )
            try await reloadItems()
            watchSyncCoordinator.publishCurrentState()
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    private func makeSharedAppState() -> SharedAppState {
        let syncedItems = selectedListID == favoriteListID ? items : []
        return SharedAppState(
            backendURL: backendURL,
            authToken: authToken,
            displayName: displayName,
            favoriteListID: favoriteListID,
            quickAddItemName: quickAddItemName,
            lists: lists,
            items: syncedItems
        )
    }

    private func rpID(from optionsPayload: [String: Any]) -> String? {
        let publicKey = (optionsPayload["publicKey"] as? [String: Any]) ?? optionsPayload
        return publicKey["rpId"] as? String
    }

    private func ensureBackendReady(backendURL: URL) async throws {
        let data = try await requestData(
            backendURL: backendURL,
            path: "/health",
            method: "GET",
            body: nil,
            token: nil
        )
        guard
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let status = payload["status"] as? String,
            status == "ok"
        else {
            throw AppError.backendUnavailable(
                "The backend is not ready yet. It may still be starting or redeploying."
            )
        }
    }

    private func requestArray(backendURL: URL, path: String, token: String) async throws -> [[String: Any]] {
        let data = try await requestData(
            backendURL: backendURL,
            path: path,
            method: "GET",
            body: nil,
            token: token
        )
        do {
            let obj = try JSONSerialization.jsonObject(with: data)
            guard let array = obj as? [[String: Any]] else {
                throw AppError.invalidResponse
            }
            return array
        } catch {
            netLog.error("JSON decode error: \(String(describing: error), privacy: .public). Raw: \(String(data: data, encoding: .utf8) ?? "<non-utf8>", privacy: .public)")
            throw error
        }
    }

    private func requestJSON(backendURL: URL, path: String, method: String, body: [String: Any]?, token: String?) async throws -> [String: Any] {
        let data = try await requestData(
            backendURL: backendURL,
            path: path,
            method: method,
            body: body,
            token: token
        )
        do {
            let obj = try JSONSerialization.jsonObject(with: data)
            guard let payload = obj as? [String: Any] else {
                throw AppError.invalidResponse
            }
            return payload
        } catch {
            netLog.error("JSON decode error: \(String(describing: error), privacy: .public). Raw: \(String(data: data, encoding: .utf8) ?? "<non-utf8>", privacy: .public)")
            throw error
        }
    }

    private func requestData(backendURL: URL, path: String, method: String, body: [String: Any]?, token: String?) async throws -> Data {
        var request = URLRequest(url: backendURL.appending(path: path))
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw AppError.invalidResponse
        }
        guard (200 ... 299).contains(http.statusCode) else {
            if let temporaryBackendError = backendAvailabilityError(response: http, data: data) {
                throw temporaryBackendError
            }
            if
                let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let detail = payload["detail"] as? String
            {
                throw AppError.server(detail)
            }
            throw AppError.server("Request failed (\(http.statusCode)).")
        }
        return data
    }

    private func backendAvailabilityError(response: HTTPURLResponse, data: Data) -> AppError? {
        let serverHeader = response.value(forHTTPHeaderField: "Server") ?? ""
        let contentType = response.value(forHTTPHeaderField: "Content-Type") ?? ""
        let bodyString = String(data: data, encoding: .utf8) ?? ""

        if response.statusCode == 501 && serverHeader.contains("BaseHTTP") {
            return .backendUnavailable(
                "The backend is not ready yet. This URL is currently serving a temporary placeholder while the deployment is rebuilding."
            )
        }
        if contentType.contains("text/html") && bodyString.contains("Unsupported method") {
            return .backendUnavailable(
                "The backend is not ready yet. This URL is currently serving a temporary placeholder while the deployment is rebuilding."
            )
        }
        return nil
    }
}

enum AppError: LocalizedError {
    case invalidResponse
    case backendUnavailable(String)
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The server returned an invalid response."
        case let .backendUnavailable(message):
            return message
        case let .server(message):
            return message
        }
    }
}
