import PlaniniCore
import SwiftUI

@MainActor
final class AppearanceSettings: ObservableObject {
    private static let uiTestResetKey = "PLANINI_UI_TEST_RESET_APPEARANCE_MODE"

    private let store: AppearanceModeStoring

    @Published var mode: AppearanceMode {
        didSet {
            store.save(mode)
        }
    }

    init(
        store: AppearanceModeStoring = AppearanceModeStore(),
        processInfo: ProcessInfo = .processInfo
    ) {
        self.store = store
        if processInfo.environment[Self.uiTestResetKey] == "1" {
            store.clear()
        }
        mode = store.load()
    }
}

extension AppearanceMode {
    var preferredColorScheme: ColorScheme? {
        switch self {
        case .system:
            return nil
        case .light:
            return .light
        case .dark:
            return .dark
        }
    }
}
