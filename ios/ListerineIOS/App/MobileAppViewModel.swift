import Foundation
import ListerineCore

@MainActor
final class MobileAppViewModel: ObservableObject {
    @Published var backendURLInput: String
    @Published private(set) var backendURL: URL?
    @Published private(set) var isAuthenticating = false
    @Published private(set) var authToken: String?
    @Published private(set) var displayName: String?
    @Published private(set) var lists: [AppGroceryList] = []
    @Published private(set) var items: [AppGroceryItem] = []
    @Published var selectedListID: UUID?
    @Published var newItemName = ""
    @Published var errorMessage: String?

    private let urlStore = BackendURLStore()
    private let passkeyClient: ApplePasskeyClient

    init(passkeyClient: ApplePasskeyClient = ApplePasskeyClient()) {
        self.passkeyClient = passkeyClient
        let config = urlStore.load()
        backendURL = config.backendURL
        backendURLInput = config.backendURL?.absoluteString ?? "https://listerine.malaber.de"
    }

    func saveBackendURL() {
        do {
            let config = try urlStore.save(backendURLString: backendURLInput)
            backendURL = config.backendURL
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loginWithPasskey() async {
        guard let backendURL else {
            errorMessage = "Please save a backend URL first."
            return
        }

        isAuthenticating = true
        defer { isAuthenticating = false }

        do {
            let options = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/login/options",
                method: "POST",
                body: [:],
                token: nil
            )
            let credential = try await passkeyClient.authenticate(optionsPayload: options, relyingPartyIdentifier: backendURL.host ?? "")
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

            let me = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/me",
                method: "GET",
                body: nil,
                token: accessToken
            )
            displayName = me["display_name"] as? String
            try await reloadAllData()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func reloadAllData() async throws {
        guard let backendURL, let authToken else { return }

        let households = try await requestArray(
            backendURL: backendURL,
            path: "/api/v1/households",
            token: authToken
        )
        var allLists: [AppGroceryList] = []
        for household in households {
            guard let householdIDText = household["id"] as? String, let householdID = UUID(uuidString: householdIDText) else { continue }
            let householdLists = try await requestArray(
                backendURL: backendURL,
                path: "/api/v1/households/\(householdID.uuidString)/lists",
                token: authToken
            )
            let mapped = householdLists.compactMap(AppGroceryList.init)
            allLists.append(contentsOf: mapped)
        }

        lists = allLists.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        if selectedListID == nil {
            selectedListID = lists.first?.id
        }
        try await reloadItems()
    }

    func reloadItems() async throws {
        guard let backendURL, let authToken, let selectedListID else {
            items = []
            return
        }

        let payload = try await requestArray(
            backendURL: backendURL,
            path: "/api/v1/lists/\(selectedListID.uuidString)/items",
            token: authToken
        )
        items = payload.compactMap(AppGroceryItem.init).sorted { lhs, rhs in
            if lhs.checked != rhs.checked { return lhs.checked == false }
            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
    }

    func addItem() async {
        let trimmed = newItemName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let backendURL, let authToken, let selectedListID, trimmed.isEmpty == false else { return }

        do {
            _ = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/lists/\(selectedListID.uuidString)/items",
                method: "POST",
                body: ["name": trimmed],
                token: authToken
            )
            newItemName = ""
            try await reloadItems()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggle(_ item: AppGroceryItem) async {
        guard let backendURL, let authToken else { return }
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
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveEdit(item: AppGroceryItem, name: String, quantity: String, note: String) async {
        guard let backendURL, let authToken else { return }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else { return }

        do {
            _ = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/items/\(item.id.uuidString)",
                method: "PATCH",
                body: ["name": trimmed, "quantity_text": quantity.isEmpty ? NSNull() : quantity, "note": note.isEmpty ? NSNull() : note],
                token: authToken
            )
            try await reloadItems()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func delete(item: AppGroceryItem) async {
        guard let backendURL, let authToken else { return }

        do {
            _ = try await requestData(
                backendURL: backendURL,
                path: "/api/v1/items/\(item.id.uuidString)",
                method: "DELETE",
                body: nil,
                token: authToken
            )
            try await reloadItems()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func requestArray(backendURL: URL, path: String, token: String) async throws -> [[String: Any]] {
        let data = try await requestData(backendURL: backendURL, path: path, method: "GET", body: nil, token: token)
        guard let array = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw AppError.invalidResponse
        }
        return array
    }

    private func requestJSON(backendURL: URL, path: String, method: String, body: [String: Any]?, token: String?) async throws -> [String: Any] {
        let data = try await requestData(backendURL: backendURL, path: path, method: method, body: body, token: token)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AppError.invalidResponse
        }
        return payload
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
        guard let http = response as? HTTPURLResponse else { throw AppError.invalidResponse }
        guard (200 ... 299).contains(http.statusCode) else {
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let detail = payload["detail"] as? String {
                throw AppError.server(detail)
            }
            throw AppError.server("Request failed (\(http.statusCode)).")
        }
        return data
    }
}

struct AppGroceryList: Identifiable {
    let id: UUID
    let name: String

    init?(json: [String: Any]) {
        guard let idText = json["id"] as? String, let id = UUID(uuidString: idText), let name = json["name"] as? String else { return nil }
        self.id = id
        self.name = name
    }
}

struct AppGroceryItem: Identifiable {
    let id: UUID
    let name: String
    let checked: Bool
    let quantityText: String?
    let note: String?

    init?(json: [String: Any]) {
        guard let idText = json["id"] as? String, let id = UUID(uuidString: idText), let name = json["name"] as? String else { return nil }
        self.id = id
        self.name = name
        self.checked = (json["checked"] as? Bool) ?? false
        self.quantityText = json["quantity_text"] as? String
        self.note = json["note"] as? String
    }
}

enum AppError: LocalizedError {
    case invalidResponse
    case server(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "The server returned an invalid response."
        case let .server(message):
            return message
        }
    }
}
