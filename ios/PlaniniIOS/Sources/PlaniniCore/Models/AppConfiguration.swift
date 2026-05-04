import Foundation

public struct AppConfiguration: Equatable, Sendable {
    public var backendURL: URL?

    public init(backendURL: URL?) {
        self.backendURL = backendURL
    }

    public var hasBackendURL: Bool {
        backendURL != nil
    }
}
