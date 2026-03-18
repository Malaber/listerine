import Foundation
import Testing
@testable import ListerineCore

@MainActor
struct AuthViewModelTests {
    @Test func initializesFromStoredConfiguration() {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: URL(string: "https://stored.example.com")))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )

        #expect(viewModel.backendURLInput == "https://stored.example.com")
        #expect(viewModel.backendURLDescription == "https://stored.example.com")
    }

    @Test func backendDescriptionFallsBackWhenUnset() {
        let viewModel = AuthViewModel(
            urlStore: InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: nil)),
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )

        #expect(viewModel.backendURLDescription == "Not configured")
    }

    @Test func saveBackendURLUpdatesStatus() {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: nil))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )
        viewModel.backendURLInput = "https://api.example.com"

        viewModel.saveBackendURL()

        #expect(viewModel.configuration.backendURL == URL(string: "https://api.example.com"))
        #expect(viewModel.latestStatusMessage == "Backend URL saved.")
        #expect(viewModel.errorMessage == nil)
    }

    @Test func saveBackendURLPublishesValidationError() {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: nil))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )
        viewModel.backendURLInput = "notaurl"

        viewModel.saveBackendURL()

        #expect(viewModel.errorMessage == "Enter a valid http or https backend URL.")
    }

    @Test func resetBackendURLClearsState() {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: URL(string: "https://api.example.com")))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )

        viewModel.resetBackendURL()

        #expect(viewModel.configuration.backendURL == nil)
        #expect(viewModel.backendURLInput.isEmpty)
        #expect(viewModel.latestStatusMessage == "Backend URL cleared.")
    }

    @Test func performPasskeyRequiresBackendURL() async {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: nil))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient())
        )

        await viewModel.performPasskey(.logIn)

        #expect(viewModel.errorMessage == "Set your backend URL before using passkeys.")
        #expect(viewModel.isPerformingPasskeyRequest == false)
    }

    @Test func performPasskeyPublishesSuccessMessage() async {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: URL(string: "https://api.example.com")))
        let client = SpyPasskeyClient()
        let service = PasskeyAuthService(client: client, challengeGenerator: { Data([0xAA]) })
        let viewModel = AuthViewModel(urlStore: store, passkeyService: service, username: "alex@example.com")

        await viewModel.performPasskey(.signUp)

        #expect(viewModel.latestStatusMessage.contains("Created a sign up passkey request"))
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.isPerformingPasskeyRequest == false)
        let requests = await client.requests
        #expect(requests.count == 1)
        #expect(requests.first?.operation == .signUp)
    }

    @Test func performPasskeyPublishesServiceErrors() async {
        let store = InMemoryBackendURLStore(configuration: AppConfiguration(backendURL: URL(string: "https://api.example.com")))
        let viewModel = AuthViewModel(
            urlStore: store,
            passkeyService: PasskeyAuthService(client: SpyPasskeyClient()),
            username: "  "
        )

        await viewModel.performPasskey(.logIn)

        #expect(viewModel.errorMessage == "Enter an email or username before continuing.")
        #expect(viewModel.isPerformingPasskeyRequest == false)
    }
}

private final class InMemoryBackendURLStore: BackendURLStoring, @unchecked Sendable {
    private var storedConfiguration: AppConfiguration

    init(configuration: AppConfiguration) {
        storedConfiguration = configuration
    }

    func load() -> AppConfiguration {
        storedConfiguration
    }

    func save(backendURLString: String) throws -> AppConfiguration {
        let url = try BackendURLStore(
            userDefaults: UserDefaults(suiteName: #function)!,
            backendURLKey: UUID().uuidString
        ).save(backendURLString: backendURLString)
        storedConfiguration = url
        return url
    }

    func clear() {
        storedConfiguration = AppConfiguration(backendURL: nil)
    }
}

actor SpyPasskeyClient: PasskeyClient {
    private(set) var requests: [PasskeyRequest] = []

    func prepareRequest(_ request: PasskeyRequest) async throws {
        requests.append(request)
    }
}
