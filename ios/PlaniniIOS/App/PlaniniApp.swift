import SwiftUI

@main
struct PlaniniApp: App {
    @StateObject private var viewModel = MobileAppViewModel()
    @StateObject private var appearanceSettings = AppearanceSettings()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
                .environmentObject(appearanceSettings)
                .preferredColorScheme(appearanceSettings.mode.preferredColorScheme)
        }
    }
}
