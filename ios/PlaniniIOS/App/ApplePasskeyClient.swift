import Foundation

#if canImport(AuthenticationServices)
import AuthenticationServices
import os.log
import UIKit

private let passkeyLog = Logger(subsystem: "de.malaber.planini.ios", category: "passkey")

struct ApplePasskeyClient {
    func register(optionsPayload: [String: Any], relyingPartyIdentifier: String) async throws -> [String: Any] {
        let publicKey = (optionsPayload["publicKey"] as? [String: Any]) ?? optionsPayload
        guard
            let challengeText = publicKey["challenge"] as? String,
            let challenge = Data(base64URLEncoded: challengeText),
            let user = publicKey["user"] as? [String: Any],
            let userIDText = user["id"] as? String,
            let userID = Data(base64URLEncoded: userIDText)
        else {
            throw AppError.invalidResponse
        }

        let userName = (user["name"] as? String) ?? (user["displayName"] as? String) ?? "Planini"
        logPasskeyRequest(
            operation: "registration",
            relyingPartyIdentifier: relyingPartyIdentifier,
            publicKey: publicKey,
            allowedCredentialCount: 0
        )
        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(relyingPartyIdentifier: relyingPartyIdentifier)
        let request = provider.createCredentialRegistrationRequest(
            challenge: challenge,
            name: userName,
            userID: userID
        )

        let authorization = try await PasskeyCoordinator().perform(request: request)
        guard
            let credential = authorization.credential as? ASAuthorizationPlatformPublicKeyCredentialRegistration,
            let attestationObject = credential.rawAttestationObject
        else {
            throw AppError.server("Passkey registration failed.")
        }

        return [
            "id": credential.credentialID.base64URLEncodedString(),
            "rawId": credential.credentialID.base64URLEncodedString(),
            "type": "public-key",
            "response": [
                "clientDataJSON": credential.rawClientDataJSON.base64URLEncodedString(),
                "attestationObject": attestationObject.base64URLEncodedString(),
            ],
            "clientExtensionResults": [:],
        ]
    }

    func authenticate(optionsPayload: [String: Any], relyingPartyIdentifier: String) async throws -> [String: Any] {
        let publicKey = (optionsPayload["publicKey"] as? [String: Any]) ?? optionsPayload
        guard
            let challengeText = publicKey["challenge"] as? String,
            let challenge = Data(base64URLEncoded: challengeText)
        else {
            throw AppError.invalidResponse
        }

        let allowCredentials = publicKey["allowCredentials"] as? [[String: Any]]
        logPasskeyRequest(
            operation: "assertion",
            relyingPartyIdentifier: relyingPartyIdentifier,
            publicKey: publicKey,
            allowedCredentialCount: allowCredentials?.count ?? 0
        )
        let provider = ASAuthorizationPlatformPublicKeyCredentialProvider(relyingPartyIdentifier: relyingPartyIdentifier)
        let request = provider.createCredentialAssertionRequest(challenge: challenge)

        if let allowCredentials, allowCredentials.isEmpty == false {
            var descriptors: [ASAuthorizationPlatformPublicKeyCredentialDescriptor] = []
            for item in allowCredentials {
                guard let id = item["id"] as? String,
                      let credentialID = Data(base64URLEncoded: id) else { continue }
                let descriptor = ASAuthorizationPlatformPublicKeyCredentialDescriptor(credentialID: credentialID)
                descriptors.append(descriptor)
            }
            request.allowedCredentials = descriptors
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

private func logPasskeyRequest(
    operation: String,
    relyingPartyIdentifier: String,
    publicKey: [String: Any],
    allowedCredentialCount: Int
) {
    let challengeText = publicKey["challenge"] as? String ?? "<missing>"
    let userVerification = publicKey["userVerification"] as? String ?? "<missing>"
    let bundleID = Bundle.main.bundleIdentifier ?? "<missing>"
    passkeyLog.notice(
        "Starting passkey \(operation, privacy: .public). rpID=\(relyingPartyIdentifier, privacy: .public) bundleID=\(bundleID, privacy: .public) challengeLength=\(challengeText.count) allowCredentials=\(allowedCredentialCount) userVerification=\(userVerification, privacy: .public)"
    )
}

private final class PasskeyCoordinator: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private var continuation: CheckedContinuation<ASAuthorization, Error>?

    func perform(request: ASAuthorizationRequest) async throws -> ASAuthorization {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            passkeyLog.debug(
                "Performing ASAuthorizationController request type=\(String(describing: type(of: request)), privacy: .public)"
            )
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self
            controller.presentationContextProvider = self
            controller.performRequests()
        }
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        passkeyLog.notice(
            "ASAuthorizationController completed. credentialType=\(String(describing: type(of: authorization.credential)), privacy: .public)"
        )
        continuation?.resume(returning: authorization)
        continuation = nil
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let nsError = error as NSError
        passkeyLog.error(
            "ASAuthorizationController failed. type=\(String(describing: type(of: error)), privacy: .public) domain=\(nsError.domain, privacy: .public) code=\(nsError.code) description=\(nsError.localizedDescription, privacy: .public) userInfo=\(String(describing: nsError.userInfo), privacy: .public)"
        )
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
    func register(optionsPayload: [String: Any], relyingPartyIdentifier: String) async throws -> [String: Any] {
        _ = optionsPayload
        _ = relyingPartyIdentifier
        throw AppError.server("Passkeys are unavailable on this platform.")
    }

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
