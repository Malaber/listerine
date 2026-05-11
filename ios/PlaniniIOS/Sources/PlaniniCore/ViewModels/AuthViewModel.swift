#if canImport(Combine)
import Combine
#else
public protocol ObservableObject: AnyObject {}

@propertyWrapper
public struct Published<Value> {
    public var wrappedValue: Value

    public init(wrappedValue: Value) {
        self.wrappedValue = wrappedValue
    }
}
#endif

import Foundation

@MainActor
public final class AuthViewModel: ObservableObject {
    @Published public var backendURLInput: String
    @Published public var username: String
    @Published public private(set) var configuration: AppConfiguration
    @Published public private(set) var isPerformingPasskeyRequest = false
    @Published public private(set) var latestStatusMessage = ""
    @Published public var errorMessage: String?

    private let urlStore: BackendURLStoring
    private let passkeyService: PasskeyAuthService

    public init(
        urlStore: BackendURLStoring,
        passkeyService: PasskeyAuthService,
        username: String = ""
    ) {
        self.urlStore = urlStore
        self.passkeyService = passkeyService

        let loadedConfiguration = urlStore.load()
        configuration = loadedConfiguration
        backendURLInput = loadedConfiguration.backendURL?.absoluteString ?? ""
        self.username = username
    }

    public var backendURLDescription: String {
        configuration.backendURL?.absoluteString ?? "Not configured"
    }

    public func saveBackendURL() {
        do {
            configuration = try urlStore.save(backendURLString: backendURLInput)
            backendURLInput = configuration.backendURL?.absoluteString ?? backendURLInput
            latestStatusMessage = "Backend URL saved."
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func resetBackendURL() {
        urlStore.clear()
        configuration = AppConfiguration(backendURL: nil)
        backendURLInput = ""
        latestStatusMessage = "Backend URL cleared."
        errorMessage = nil
    }

    public func performPasskey(_ operation: PasskeyOperation) async {
        guard let backendURL = configuration.backendURL else {
            errorMessage = "Set your backend URL before using passkeys."
            return
        }

        isPerformingPasskeyRequest = true
        errorMessage = nil
        defer { isPerformingPasskeyRequest = false }

        do {
            let result = try await passkeyService.perform(
                operation: operation,
                username: username,
                backendURL: backendURL
            )
            latestStatusMessage = result.summary
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
