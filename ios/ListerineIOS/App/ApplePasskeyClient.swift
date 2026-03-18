import Foundation
import ListerineCore

#if canImport(AuthenticationServices)
import AuthenticationServices

struct ApplePasskeyClient: PasskeyClient {
    func prepareRequest(_ request: PasskeyRequest) async throws {
        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(
            relyingPartyIdentifier: request.relyingPartyIdentifier
        )

        switch request.operation {
        case .signUp:
            _ = provider.createCredentialRegistrationRequest(
                challenge: request.challenge,
                name: request.username,
                userID: request.userID
            )
        case .logIn:
            _ = provider.createCredentialAssertionRequest(challenge: request.challenge)
        }
    }
}
#else
struct ApplePasskeyClient: PasskeyClient {
    func prepareRequest(_ request: PasskeyRequest) async throws {
        _ = request
    }
}
#endif
