import Foundation

#if canImport(AuthenticationServices)
import AuthenticationServices
import UIKit

struct ApplePasskeyClient {
    func authenticate(optionsPayload: [String: Any], relyingPartyIdentifier: String) async throws -> [String: Any] {
        guard
            let publicKey = optionsPayload["publicKey"] as? [String: Any],
            let challengeText = publicKey["challenge"] as? String,
            let challenge = Data(base64URLEncoded: challengeText)
        else {
            throw AppError.invalidResponse
        }

        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(relyingPartyIdentifier: relyingPartyIdentifier)
        let request = provider.createCredentialAssertionRequest(challenge: challenge)

        if let allowCredentials = publicKey["allowCredentials"] as? [[String: Any]], allowCredentials.isEmpty == false {
            request.allowedCredentials = allowCredentials.compactMap { item in
                guard let id = item["id"] as? String else { return nil }
                return Data(base64URLEncoded: id)
            }
        }

        let authorization = try await PasskeyCoordinator().perform(request: request)
        guard let credential = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialAssertion else {
            throw AppError.server("Passkey sign-in failed.")
        }

        return [
            "id": credential.credentialID.base64URLEncodedString(),
            "rawId": credential.credentialID.base64URLEncodedString(),
            "type": "public-key",
            "response": [
                "authenticatorData": credential.rawAuthenticatorData.base64URLEncodedString(),
                "clientDataJSON": credential.rawClientDataJSON.base64URLEncodedString(),
                "signature": credential.signature.base64URLEncodedString(),
                "userHandle": (credential.userID ?? Data()).base64URLEncodedString(),
            ],
            "clientExtensionResults": [:],
        ]
    }
}

private final class PasskeyCoordinator: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var continuation: CheckedContinuation<ASAuthorization, Error>?

    func perform(request: ASAuthorizationRequest) async throws -> ASAuthorization {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.presentationContextProvider = self
            controller.performRequests()
        }
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        continuation?.resume(returning: authorization)
        continuation = nil
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.keyWindow }
            .first ?? ASPresentationAnchor()
    }
}
#else
struct ApplePasskeyClient {
    func authenticate(optionsPayload: [String: Any], relyingPartyIdentifier: String) async throws -> [String: Any] {
        _ = optionsPayload
        _ = relyingPartyIdentifier
        throw AppError.server("Passkeys are unavailable on this platform.")
    }
}
#endif

private extension Data {
    init?(base64URLEncoded value: String) {
        let normalized = value.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        let padded = normalized + String(repeating: "=", count: (4 - normalized.count % 4) % 4)
        self.init(base64Encoded: padded)
    }

    func base64URLEncodedString() -> String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}
