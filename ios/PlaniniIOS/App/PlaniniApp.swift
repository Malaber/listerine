import SwiftUI

@main
struct PlaniniApp: App {
    @StateObject private var viewModel = MobileAppViewModel()
    @StateObject private var localization = AppLocalization()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
                .environmentObject(localization)
                .environment(\.locale, Locale(identifier: localization.effectiveLocale))
        }
    }
}
