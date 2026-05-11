import SwiftUI

@main
struct PlaniniApp: App {
    @StateObject private var viewModel = MobileAppViewModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(viewModel)
        }
    }
}
