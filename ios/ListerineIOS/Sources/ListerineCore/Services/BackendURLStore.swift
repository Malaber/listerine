import Foundation

public protocol BackendURLStoring: Sendable {
    func load() -> AppConfiguration
    func save(backendURLString: String) throws -> AppConfiguration
    func clear()
}

public enum BackendURLStoreError: LocalizedError, Equatable {
    case invalidURL

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Enter a valid http or https backend URL."
        }
    }
}

public final class BackendURLStore: BackendURLStoring, @unchecked Sendable {
    private let userDefaults: UserDefaults
    private let backendURLKey: String

    public init(
        userDefaults: UserDefaults = .standard,
        backendURLKey: String = "listerine.backend-url"
    ) {
        self.userDefaults = userDefaults
        self.backendURLKey = backendURLKey
    }

    public func load() -> AppConfiguration {
        guard
            let storedURL = userDefaults.string(forKey: backendURLKey),
            let url = URL(string: storedURL)
        else {
            return AppConfiguration(backendURL: nil)
        }

        return AppConfiguration(backendURL: url)
    }

    public func save(backendURLString: String) throws -> AppConfiguration {
        let trimmedURL = backendURLString.trimmingCharacters(in: .whitespacesAndNewlines)

        guard
            let url = URL(string: trimmedURL),
            let scheme = url.scheme?.lowercased(),
            ["http", "https"].contains(scheme),
            url.host != nil
        else {
            throw BackendURLStoreError.invalidURL
        }

        userDefaults.set(url.absoluteString, forKey: backendURLKey)
        return AppConfiguration(backendURL: url)
    }

    public func clear() {
        userDefaults.removeObject(forKey: backendURLKey)
    }
}
