import SwiftUI

@main
struct ListerineApp: App {
    @StateObject private var viewModel = MobileAppViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
        }
    }
}
