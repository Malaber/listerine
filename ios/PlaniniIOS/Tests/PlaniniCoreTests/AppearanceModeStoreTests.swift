import Foundation
import Testing
@testable import PlaniniCore

struct AppearanceModeStoreTests {
    @Test func loadDefaultsToSystemWhenEmpty() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = AppearanceModeStore(userDefaults: defaults, appearanceModeKey: "appearance")

        #expect(store.load() == .system)
    }

    @Test func loadDefaultsToSystemWhenStoredValueIsInvalid() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        defaults.set("sepia", forKey: "appearance")
        let store = AppearanceModeStore(userDefaults: defaults, appearanceModeKey: "appearance")

        #expect(store.load() == .system)
    }

    @Test(arguments: AppearanceMode.allCases)
    func savePersistsSelectedAppearanceMode(mode: AppearanceMode) {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = AppearanceModeStore(userDefaults: defaults, appearanceModeKey: "appearance")

        store.save(mode)

        #expect(store.load() == mode)
    }

    @Test func clearRemovesStoredAppearanceMode() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = AppearanceModeStore(userDefaults: defaults, appearanceModeKey: "appearance")

        store.save(.dark)
        store.clear()

        #expect(store.load() == .system)
    }

    @Test func settingsLabelsMatchPickerChoices() {
        #expect(AppearanceMode.system.settingsLabel == "System")
        #expect(AppearanceMode.light.settingsLabel == "Light")
        #expect(AppearanceMode.dark.settingsLabel == "Dark")
    }
}
