import Foundation
import os.log
import ListerineCore

private let netLog = Logger(subsystem: "com.example.ListerineIOS", category: "network")

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

        netLog.debug("Starting passkey login flow for backend: \(backendURL.absoluteString, privacy: .public)")

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
            netLog.debug("Received login options keys: \(String(describing: Array(options.keys)), privacy: .public)")
            netLog.debug("Invoking platform authenticator with RP ID: \(backendURL.host ?? "<nil>", privacy: .public)")
            
            netLog.debug("About to call passkeyClient.authenticate", privacy: .public)
            let credential = try await passkeyClient.authenticate(optionsPayload: options, relyingPartyIdentifier: backendURL.host ?? "")
            netLog.debug("Authenticate returned successfully", privacy: .public)
            netLog.debug("Credential top-level type: \(String(describing: type(of: credential)), privacy: .public)")

            #if DEBUG
            if let credDict = credential as? [String: Any] {
                let topKeys = Array(credDict.keys)
                netLog.debug("Credential top-level keys: \(String(describing: topKeys), privacy: .public)")
                if let resp = credDict["response"] as? [String: Any] {
                    netLog.debug("Credential.response keys: \(String(describing: Array(resp.keys)), privacy: .public)")
                    // Helpful hint: binary fields must be base64url strings, not Data
                    let suspectedBinaryKeys = ["clientDataJSON", "authenticatorData", "signature", "userHandle"]
                    for key in suspectedBinaryKeys {
                        if let value = resp[key] {
                            netLog.debug("response[\(key)] type: \(String(describing: type(of: value)), privacy: .public)")
                        }
                    }
                }
            }
            #endif

            // Normalize credential to be JSON-safe (convert Data to base64url strings)
            var normalizedAny: Any = normalizeCredentialJSON(credential)

            // If the credential isn't a dictionary/array after normalization, fall back to a stringified wrapper
            if (normalizedAny as? [String: Any]) == nil && (normalizedAny as? [Any]) == nil {
                netLog.error("Credential is not a dictionary/array after normalization. Applying fallback wrapper.")
                normalizedAny = ["raw": String(describing: credential)]
            }

            var normalized = normalizedAny
            if let problem = findFirstNonJSONValue(in: normalized) {
                netLog.error("Credential contains non-JSON value at path: \(problem.path.joined(separator: "."), privacy: .public); type=\(String(describing: type(of: problem.value)), privacy: .public)")
                // Apply broader normalization to coerce remaining values
                normalized = deepNormalizeToJSON(normalized)
            }

            let verifyEnvelope: [String: Any] = ["credential": normalized]

            // Pre-encode to catch JSONSerialization errors early and log raw issues
            let verifyBodyData: Data
            do {
                verifyBodyData = try JSONSerialization.data(withJSONObject: verifyEnvelope)
                #if DEBUG
                if let jsonString = String(data: verifyBodyData, encoding: .utf8) {
                    netLog.debug("Verify request body JSON: \(jsonString, privacy: .public)")
                }
                #endif
            } catch {
                netLog.error("Failed to encode verify body. Ensure binary fields are base64url strings. Error: \(String(describing: error), privacy: .public)")
                throw error
            }

            // Send verify request using the normalized envelope
            let tokenJson = try await requestJSON(
                backendURL: backendURL,
                path: "/api/v1/auth/login/verify",
                method: "POST",
                body: verifyEnvelope,
                token: nil
            )

            netLog.debug("Verify response keys: \(String(describing: Array(tokenJson.keys)), privacy: .public)")

            guard let accessToken = tokenJson["access_token"] as? String else {
                throw AppError.invalidResponse
            }
            netLog.info("Passkey login succeeded; received access token (length=\(accessToken.count))")
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
            let nsErr = error as NSError
            netLog.error("Passkey login failed. Type=\(String(describing: type(of: error)), privacy: .public) Domain=\(nsErr.domain, privacy: .public) Code=\(nsErr.code) Desc=\(nsErr.localizedDescription, privacy: .public)")
            errorMessage = nsErr.localizedDescription
        }
    }

    // MARK: - Passkey credential normalization
    private func base64url(_ data: Data) -> String {
        let base64 = data.base64EncodedString()
        // Convert to base64url by replacing characters and trimming padding
        return base64
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .trimmingCharacters(in: CharacterSet(charactersIn: "="))
    }

    private func normalizeCredentialJSON(_ credential: Any) -> Any {
        // Recursively walk the structure and convert Data to base64url strings.
        if let data = credential as? Data {
            return base64url(data)
        } else if let dict = credential as? [String: Any] {
            var out: [String: Any] = [:]
            for (k, v) in dict {
                out[k] = normalizeCredentialJSON(v)
            }
            return out
        } else if let array = credential as? [Any] {
            return array.map { normalizeCredentialJSON($0) }
        } else {
            return credential
        }
    }

    // Validate JSON-encodability and provide diagnostics
    private func findFirstNonJSONValue(in value: Any, path: [String] = []) -> (path: [String], value: Any)? {
        // JSONSerialization allows: NSDictionary/Array, String, Number, Bool, NSNull
        if value is String || value is NSNumber || value is NSNull || value is Bool { return nil }
        if let dict = value as? [String: Any] {
            for (k, v) in dict {
                if let problem = findFirstNonJSONValue(in: v, path: path + [k]) {
                    return problem
                }
            }
            return nil
        }
        if let array = value as? [Any] {
            for (idx, v) in array.enumerated() {
                if let problem = findFirstNonJSONValue(in: v, path: path + ["[\(idx)]"]) {
                    return problem
                }
            }
            return nil
        }
        // Anything else is non-JSON-encodable
        return (path, value)
    }

    // Broader normalization to coerce common Foundation types to strings and keys to String
    private func deepNormalizeToJSON(_ value: Any) -> Any {
        if let data = value as? Data { return base64url(data) }
        if let date = value as? Date {
            let iso = ISO8601DateFormatter().string(from: date)
            return iso
        }
        if let url = value as? URL { return url.absoluteString }
        if let str = value as? String { return str }
        if let num = value as? NSNumber { return num }
        if value is NSNull { return NSNull() }
        if let b = value as? Bool { return b }
        if let dict = value as? [String: Any] {
            var out: [String: Any] = [:]
            for (k, v) in dict {
                out[String(describing: k)] = deepNormalizeToJSON(v)
            }
            return out
        }
        if let array = value as? [Any] {
            return array.map { deepNormalizeToJSON($0) }
        }
        // Fallback: stringify unknown types for debug robustness
        return String(describing: value)
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
        do {
            let obj = try JSONSerialization.jsonObject(with: data)
            guard let array = obj as? [[String: Any]] else {
                netLog.error("Invalid JSON object type (expected array). Raw: \(String(data: data, encoding: .utf8) ?? "<non-utf8>", privacy: .public)")
                throw AppError.invalidResponse
            }
            return array
        } catch {
            netLog.error("JSON decode error: \(String(describing: error), privacy: .public). Raw: \(String(data: data, encoding: .utf8) ?? "<non-utf8>", privacy: .public)")
            throw error
        }
    }

    private func requestJSON(backendURL: URL, path: String, method: String, body: [String: Any]?, token: String?) async throws -> [String: Any] {
        let data = try await requestData(backendURL: backendURL, path: path, method: method, body: body, token: token)
        do {
            let obj = try JSONSerialization.jsonObject(with: data)
            guard let payload = obj as? [String: Any] else {
                netLog.error("Invalid JSON object type (expected dictionary). Raw: \(String(data: data, encoding: .utf8) ?? "<non-utf8>", privacy: .public)")
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

        #if DEBUG
        let debugBody: String? = {
            guard let body = request.httpBody else { return nil }
            return String(data: body, encoding: .utf8)
        }()
        netLog.debug("→ \(request.httpMethod ?? "<NO_METHOD>", privacy: .public) \(request.url?.absoluteString ?? "<NO_URL>", privacy: .public)")
        if let headers = request.allHTTPHeaderFields, !headers.isEmpty {
            netLog.debug("Headers: \(String(describing: headers), privacy: .public)")
        }
        if let debugBody {
            netLog.debug("Body: \(debugBody, privacy: .public)")
        }
        #endif

        let (data, response) = try await URLSession.shared.data(for: request)

        #if DEBUG
        if let http = response as? HTTPURLResponse {
            netLog.debug("← status \(http.statusCode) for \(request.url?.absoluteString ?? "<NO_URL>", privacy: .public)")
            netLog.debug("Response headers: \(String(describing: http.allHeaderFields), privacy: .public)")
        }
        if let bodyString = String(data: data, encoding: .utf8) {
            netLog.debug("Response body: \(bodyString, privacy: .public)")
        }
        #endif

        guard let http = response as? HTTPURLResponse else {
            netLog.error("Non-HTTP response for \(request.url?.absoluteString ?? "<NO_URL>", privacy: .public)")
            throw AppError.invalidResponse
        }
        guard (200 ... 299).contains(http.statusCode) else {
            netLog.error("Request failed with status \(http.statusCode); detail=\(String(describing: (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["detail"]), privacy: .public)")
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
