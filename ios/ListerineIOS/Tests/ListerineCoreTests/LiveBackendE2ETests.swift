#if canImport(CryptoKit)
import CryptoKit
import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Testing

struct LiveBackendE2ETests {
    @Test("Seeded passkey login and list CRUD against a live backend")
    func seededPasskeyLoginAndListCrud() async throws {
        guard let config = LiveBackendE2EConfiguration.fromEnvironment() else {
            return
        }

        let fixture = try SeedFixture.load(from: config.seedPath, userEmail: config.userEmail)
        let client = LiveBackendClient(baseURL: config.baseURL)

        let loginOptions = try await client.jsonObject(
            path: "/api/v1/auth/login/options",
            method: "POST",
            body: [:],
            token: nil
        )
        let credential = try SeededAssertionFactory.makeCredential(
            options: loginOptions,
            origin: config.origin,
            fallbackRelyingPartyIdentifier: config.rpID,
            passkey: fixture.passkey
        )
        let tokenPayload = try await client.jsonObject(
            path: "/api/v1/auth/login/verify",
            method: "POST",
            body: ["credential": credential],
            token: nil
        )
        let accessToken = try #require(tokenPayload["access_token"] as? String)

        let me = try await client.jsonObject(
            path: "/api/v1/auth/me",
            method: "GET",
            body: nil,
            token: accessToken
        )
        #expect(me["email"] as? String == fixture.email)
        #expect(me["display_name"] as? String == fixture.displayName)

        let households = try await client.jsonArray(
            path: "/api/v1/households",
            token: accessToken
        )
        let household = try #require(households.first { $0["name"] as? String == fixture.primaryHouseholdName })
        let householdID = try #require(household["id"] as? String)

        let lists = try await client.jsonArray(
            path: "/api/v1/households/\(householdID)/lists",
            token: accessToken
        )
        let list = try #require(lists.first { $0["name"] as? String == fixture.primaryListName })
        let listID = try #require(list["id"] as? String)

        let uniqueSuffix = UUID().uuidString.prefix(8)
        let originalName = "iOS E2E \(uniqueSuffix)"
        let updatedName = "\(originalName) Updated"

        let created = try await client.jsonObject(
            path: "/api/v1/lists/\(listID)/items",
            method: "POST",
            body: [
                "name": originalName,
                "quantity_text": "2 jars",
                "note": "Created by iOS backend e2e"
            ],
            token: accessToken
        )
        let itemID = try #require(created["id"] as? String)
        #expect(created["name"] as? String == originalName)
        #expect(created["checked"] as? Bool == false)

        let itemsAfterCreate = try await client.jsonArray(
            path: "/api/v1/lists/\(listID)/items",
            token: accessToken
        )
        #expect(itemsAfterCreate.contains(where: { ($0["id"] as? String) == itemID }))

        let updated = try await client.jsonObject(
            path: "/api/v1/items/\(itemID)",
            method: "PATCH",
            body: [
                "name": updatedName,
                "quantity_text": "3 jars",
                "note": "Updated by iOS backend e2e"
            ],
            token: accessToken
        )
        #expect(updated["name"] as? String == updatedName)
        #expect(updated["quantity_text"] as? String == "3 jars")
        #expect(updated["note"] as? String == "Updated by iOS backend e2e")

        let checked = try await client.jsonObject(
            path: "/api/v1/items/\(itemID)/check",
            method: "POST",
            body: [:],
            token: accessToken
        )
        #expect(checked["checked"] as? Bool == true)

        let unchecked = try await client.jsonObject(
            path: "/api/v1/items/\(itemID)/uncheck",
            method: "POST",
            body: [:],
            token: accessToken
        )
        #expect(unchecked["checked"] as? Bool == false)

        _ = try await client.data(
            path: "/api/v1/items/\(itemID)",
            method: "DELETE",
            body: nil,
            token: accessToken
        )

        let itemsAfterDelete = try await client.jsonArray(
            path: "/api/v1/lists/\(listID)/items",
            token: accessToken
        )
        #expect(itemsAfterDelete.contains(where: { ($0["id"] as? String) == itemID }) == false)
    }
}

private struct LiveBackendE2EConfiguration {
    let baseURL: URL
    let seedPath: URL
    let userEmail: String
    let rpID: String?

    var origin: String {
        baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    static func fromEnvironment() -> Self? {
        let environment = ProcessInfo.processInfo.environment
        guard
            let baseURLText = environment["LISTERINE_E2E_BASE_URL"],
            let baseURL = URL(string: baseURLText),
            let seedPathText = environment["LISTERINE_E2E_SEED_PATH"],
            seedPathText.isEmpty == false
        else {
            return nil
        }

        let seedPath = URL(fileURLWithPath: seedPathText)
        let userEmail = environment["LISTERINE_E2E_USER_EMAIL"] ?? "listerine@schaedler.rocks"
        let rpID = environment["LISTERINE_E2E_RP_ID"]
        return Self(baseURL: baseURL, seedPath: seedPath, userEmail: userEmail, rpID: rpID)
    }
}

private struct SeedFixture: Decodable {
    struct E2EMetadata: Decodable {
        let primaryHousehold: String
        let primaryList: String

        private enum CodingKeys: String, CodingKey {
            case primaryHousehold = "primary_household"
            case primaryList = "primary_list"
        }
    }

    struct User: Decodable {
        let email: String
        let displayName: String
        let passkey: Passkey?

        private enum CodingKeys: String, CodingKey {
            case email
            case displayName = "display_name"
            case passkey
        }
    }

    struct Passkey: Decodable {
        let credentialID: String
        let signCount: Int
        let privateKeyPKCS8Base64: String
        let userHandleBase64: String

        private enum CodingKeys: String, CodingKey {
            case credentialID = "credential_id"
            case signCount = "sign_count"
            case privateKeyPKCS8Base64 = "private_key_pkcs8_b64"
            case userHandleBase64 = "user_handle_b64"
        }
    }

    let e2e: E2EMetadata
    let users: [User]

    var email: String
    var displayName: String
    var passkey: Passkey
    var primaryHouseholdName: String
    var primaryListName: String

    private enum CodingKeys: String, CodingKey {
        case e2e
        case users
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        e2e = try container.decode(E2EMetadata.self, forKey: .e2e)
        users = try container.decode([User].self, forKey: .users)
        email = ""
        displayName = ""
        passkey = Passkey(
            credentialID: "",
            signCount: 0,
            privateKeyPKCS8Base64: "",
            userHandleBase64: ""
        )
        primaryHouseholdName = e2e.primaryHousehold
        primaryListName = e2e.primaryList
    }

    static func load(from url: URL, userEmail: String) throws -> SeedFixture {
        let data = try Data(contentsOf: url)
        let decoded = try JSONDecoder().decode(SeedFixture.self, from: data)
        guard let user = decoded.users.first(where: { $0.email == userEmail }), let passkey = user.passkey else {
            throw LiveBackendE2EError("Seed fixture does not contain a passkey for \(userEmail).")
        }

        var resolved = decoded
        resolved.email = user.email
        resolved.displayName = user.displayName
        resolved.passkey = passkey
        return resolved
    }
}

private final class LiveBackendClient {
    let baseURL: URL
    let session: URLSession
    private var sessionCookie: String?

    init(baseURL: URL) {
        self.baseURL = baseURL
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpCookieStorage = HTTPCookieStorage()
        configuration.httpShouldSetCookies = true
        configuration.httpCookieAcceptPolicy = .always
        session = URLSession(configuration: configuration)
    }

    func jsonObject(
        path: String,
        method: String,
        body: [String: Any]?,
        token: String?
    ) async throws -> [String: Any] {
        let data = try await data(path: path, method: method, body: body, token: token)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw LiveBackendE2EError("Expected JSON object for \(path).")
        }
        return payload
    }

    func jsonArray(path: String, token: String) async throws -> [[String: Any]] {
        let data = try await data(path: path, method: "GET", body: nil, token: token)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw LiveBackendE2EError("Expected JSON array for \(path).")
        }
        return payload
    }

    func data(
        path: String,
        method: String,
        body: [String: Any]?,
        token: String?
    ) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw LiveBackendE2EError("Invalid URL path \(path).")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let sessionCookie {
            request.setValue(sessionCookie, forHTTPHeaderField: "Cookie")
        }
        if let body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw LiveBackendE2EError("Expected HTTP response for \(path).")
        }
        if let setCookie = httpResponse.value(forHTTPHeaderField: "Set-Cookie") {
            let sessionCookies: [String] = setCookie
                .split(separator: ",")
                .map(String.init)
                .compactMap { cookie -> String? in
                    let trimmed = cookie.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard trimmed.hasPrefix("session=") else { return nil }
                    return trimmed.split(separator: ";", maxSplits: 1).first.map(String.init)
                }
            sessionCookie = sessionCookies.first ?? sessionCookie
        }
        guard (200 ... 299).contains(httpResponse.statusCode) else {
            let bodyText = String(data: data, encoding: .utf8) ?? "<non-utf8>"
            throw LiveBackendE2EError("Request \(method) \(path) failed with status \(httpResponse.statusCode): \(bodyText)")
        }
        return data
    }
}

private enum SeededAssertionFactory {
    static func makeCredential(
        options: [String: Any],
        origin: String,
        fallbackRelyingPartyIdentifier: String?,
        passkey: SeedFixture.Passkey
    ) throws -> [String: Any] {
        let publicKey = (options["publicKey"] as? [String: Any]) ?? options
        guard let challenge = publicKey["challenge"] as? String else {
            throw LiveBackendE2EError("Login options are missing a challenge.")
        }

        let rpID = (publicKey["rpId"] as? String) ?? fallbackRelyingPartyIdentifier
        guard let rpID, rpID.isEmpty == false else {
            throw LiveBackendE2EError("Login options are missing an rpId.")
        }

        let clientDataJSON = try JSONSerialization.data(
            withJSONObject: [
                "type": "webauthn.get",
                "challenge": challenge,
                "origin": origin,
                "crossOrigin": false
            ]
        )
        let clientDataHash = Data(SHA256.hash(data: clientDataJSON))
        let authenticatorData = makeAuthenticatorData(
            rpID: rpID,
            nextSignCount: UInt32(passkey.signCount + 1)
        )

        var signaturePayload = Data()
        signaturePayload.append(authenticatorData)
        signaturePayload.append(clientDataHash)

        guard let privateKeyData = Data(base64Encoded: passkey.privateKeyPKCS8Base64) else {
            throw LiveBackendE2EError("Passkey fixture has an invalid private key.")
        }
        let privateKey = try P256.Signing.PrivateKey(derRepresentation: privateKeyData)
        let signature = try privateKey.signature(for: signaturePayload).derRepresentation
        guard let userHandle = Data(base64Encoded: passkey.userHandleBase64) else {
            throw LiveBackendE2EError("Passkey fixture has an invalid user handle.")
        }

        return [
            "id": passkey.credentialID,
            "rawId": passkey.credentialID,
            "type": "public-key",
            "response": [
                "authenticatorData": authenticatorData.base64URLEncodedString(),
                "clientDataJSON": clientDataJSON.base64URLEncodedString(),
                "signature": signature.base64URLEncodedString(),
                "userHandle": userHandle.base64URLEncodedString()
            ],
            "clientExtensionResults": [:]
        ]
    }

    private static func makeAuthenticatorData(rpID: String, nextSignCount: UInt32) -> Data {
        var data = Data(SHA256.hash(data: Data(rpID.utf8)))
        data.append(0x05)
        var counter = nextSignCount.bigEndian
        withUnsafeBytes(of: &counter) { rawBuffer in
            data.append(contentsOf: rawBuffer)
        }
        return data
    }
}

private struct LiveBackendE2EError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? {
        message
    }
}

private extension Data {
    func base64URLEncodedString() -> String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
#endif
