import SwiftUI

@main
struct PlaniniApp: App {
    @StateObject private var viewModel = MobileAppViewModel()
    @StateObject private var localization = AppLocalization()
    @StateObject private var appearanceSettings = AppearanceSettings()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
                .environmentObject(localization)
                .environmentObject(appearanceSettings)
                .environment(\.locale, Locale(identifier: localization.effectiveLocale))
                .preferredColorScheme(appearanceSettings.mode.preferredColorScheme)
        }
    }
}
