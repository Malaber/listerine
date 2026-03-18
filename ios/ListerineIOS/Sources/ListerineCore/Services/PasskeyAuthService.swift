import Foundation

public struct PasskeyRequest: Equatable, Sendable {
    public let operation: PasskeyOperation
    public let username: String
    public let backendURL: URL
    public let relyingPartyIdentifier: String
    public let challenge: Data
    public let userID: Data

    public init(
        operation: PasskeyOperation,
        username: String,
        backendURL: URL,
        relyingPartyIdentifier: String,
        challenge: Data,
        userID: Data
    ) {
        self.operation = operation
        self.username = username
        self.backendURL = backendURL
        self.relyingPartyIdentifier = relyingPartyIdentifier
        self.challenge = challenge
        self.userID = userID
    }
}

public struct PasskeyResult: Equatable, Sendable {
    public let request: PasskeyRequest
    public let summary: String

    public init(request: PasskeyRequest, summary: String) {
        self.request = request
        self.summary = summary
    }
}

public enum PasskeyOperation: String, Equatable, Sendable {
    case signUp = "Sign Up"
    case logIn = "Log In"
}

public enum PasskeyAuthError: LocalizedError, Equatable {
    case invalidUsername
    case invalidBackendURL

    public var errorDescription: String? {
        switch self {
        case .invalidUsername:
            return "Enter an email or username before continuing."
        case .invalidBackendURL:
            return "The configured backend URL is missing a valid host."
        }
    }
}

public protocol PasskeyClient: Sendable {
    func prepareRequest(_ request: PasskeyRequest) async throws
}

public struct NoopPasskeyClient: PasskeyClient {
    public init() {}

    public func prepareRequest(_ request: PasskeyRequest) async throws {
        _ = request
    }
}

public struct PasskeyAuthService: Sendable {
    private let client: PasskeyClient
    private let challengeGenerator: @Sendable () -> Data

    public init(
        client: PasskeyClient = NoopPasskeyClient(),
        challengeGenerator: @escaping @Sendable () -> Data = { Data("listerine-placeholder-challenge".utf8) }
    ) {
        self.client = client
        self.challengeGenerator = challengeGenerator
    }

    public func perform(
        operation: PasskeyOperation,
        username: String,
        backendURL: URL
    ) async throws -> PasskeyResult {
        let trimmedUsername = username.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedUsername.isEmpty == false else {
            throw PasskeyAuthError.invalidUsername
        }

        guard let relyingPartyIdentifier = backendURL.host else {
            throw PasskeyAuthError.invalidBackendURL
        }

        let request = PasskeyRequest(
            operation: operation,
            username: trimmedUsername,
            backendURL: backendURL,
            relyingPartyIdentifier: relyingPartyIdentifier,
            challenge: challengeGenerator(),
            userID: Data(trimmedUsername.utf8)
        )

        try await client.prepareRequest(request)

        return PasskeyResult(
            request: request,
            summary: "Created a \(operation.rawValue.lowercased()) passkey request for \(trimmedUsername). Wire this request to \(backendURL.absoluteString) when backend passkey endpoints are ready."
        )
    }
}
