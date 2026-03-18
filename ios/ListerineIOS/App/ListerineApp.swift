import ListerineCore
import SwiftUI

@main
struct ListerineApp: App {
    @StateObject private var authViewModel = AuthViewModel(
        urlStore: BackendURLStore(),
        passkeyService: PasskeyAuthService(client: ApplePasskeyClient())
    )

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(authViewModel)
        }
    }
}
