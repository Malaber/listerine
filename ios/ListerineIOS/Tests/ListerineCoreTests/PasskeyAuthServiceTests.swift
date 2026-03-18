import Foundation
import Testing
@testable import ListerineCore

struct PasskeyAuthServiceTests {
    @Test func rejectsBlankUsernames() async {
        let service = PasskeyAuthService()

        await #expect(throws: PasskeyAuthError.invalidUsername) {
            try await service.perform(
                operation: .signUp,
                username: "   ",
                backendURL: try #require(URL(string: "https://api.example.com"))
            )
        }
    }

    @Test func rejectsBackendURLWithoutHost() async {
        let service = PasskeyAuthService()

        await #expect(throws: PasskeyAuthError.invalidBackendURL) {
            try await service.perform(
                operation: .logIn,
                username: "alex@example.com",
                backendURL: try #require(URL(string: "file:///tmp/backend"))
            )
        }

        #expect(PasskeyAuthError.invalidBackendURL.errorDescription == "The configured backend URL is missing a valid host.")
    }

    @Test func defaultClientAndChallengeGeneratorWork() async throws {
        let service = PasskeyAuthService()

        let result = try await service.perform(
            operation: .logIn,
            username: "alex@example.com",
            backendURL: try #require(URL(string: "https://api.example.com"))
        )

        #expect(result.request.challenge == Data("listerine-placeholder-challenge".utf8))
        #expect(result.request.operation == .logIn)
    }

    @Test func preparesRequestAndReturnsSummary() async throws {
        let recorder = PasskeyClientRecorder()
        let service = PasskeyAuthService(
            client: recorder,
            challengeGenerator: { Data([0x01, 0x02, 0x03]) }
        )

        let result = try await service.perform(
            operation: .signUp,
            username: "  alex@example.com ",
            backendURL: try #require(URL(string: "https://api.example.com"))
        )

        #expect(result.request.username == "alex@example.com")
        #expect(result.request.operation == .signUp)
        #expect(result.request.relyingPartyIdentifier == "api.example.com")
        #expect(result.request.challenge == Data([0x01, 0x02, 0x03]))
        #expect(result.request.userID == Data("alex@example.com".utf8))
        #expect(result.summary.contains("Wire this request to https://api.example.com"))
        let captured = await recorder.capturedRequests
        #expect(captured == [result.request])
    }
}

actor PasskeyClientRecorder: PasskeyClient {
    private(set) var capturedRequests: [PasskeyRequest] = []

    func prepareRequest(_ request: PasskeyRequest) async throws {
        capturedRequests.append(request)
    }
}
