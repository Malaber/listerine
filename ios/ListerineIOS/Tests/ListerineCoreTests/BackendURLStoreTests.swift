import Foundation
import Testing
@testable import ListerineCore

struct BackendURLStoreTests {
    @Test func appConfigurationHasBackendURLReflectsPresence() {
        #expect(AppConfiguration(backendURL: nil).hasBackendURL == false)
        #expect(AppConfiguration(backendURL: URL(string: "https://api.example.com")).hasBackendURL == true)
    }
    @Test func loadReturnsNilWhenEmpty() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = BackendURLStore(userDefaults: defaults, backendURLKey: "backend")

        #expect(store.load().backendURL == nil)
    }

    @Test func saveTrimsAndPersistsValidURL() throws {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = BackendURLStore(userDefaults: defaults, backendURLKey: "backend")

        let configuration = try store.save(backendURLString: "  https://api.example.com  ")

        #expect(configuration.backendURL == URL(string: "https://api.example.com"))
        #expect(store.load().backendURL == URL(string: "https://api.example.com"))
    }

    @Test(arguments: ["", "ftp://api.example.com", "https:///missing-host"])
    func saveRejectsInvalidURLs(input: String) {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = BackendURLStore(userDefaults: defaults, backendURLKey: "backend")

        #expect(throws: BackendURLStoreError.invalidURL) {
            try store.save(backendURLString: input)
        }
    }

    @Test func clearRemovesStoredURL() throws {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = BackendURLStore(userDefaults: defaults, backendURLKey: "backend")

        _ = try store.save(backendURLString: "https://api.example.com")
        store.clear()

        #expect(store.load().backendURL == nil)
    }
}
