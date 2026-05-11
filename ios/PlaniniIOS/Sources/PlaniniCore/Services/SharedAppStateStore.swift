import Foundation

public final class SharedAppStateStore: @unchecked Sendable {
    private let userDefaults: UserDefaults
    private let storageKey: String
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()

    public init(
        userDefaults: UserDefaults = .standard,
        storageKey: String = PlaniniSharedConstants.sharedAppStateKey
    ) {
        self.userDefaults = userDefaults
        self.storageKey = storageKey
    }

    public func load() -> SharedAppState {
        guard
            let data = userDefaults.data(forKey: storageKey),
            let state = try? decoder.decode(SharedAppState.self, from: data)
        else {
            return SharedAppState()
        }

        return state
    }

    public func save(_ state: SharedAppState) {
        guard let data = try? encoder.encode(state) else { return }
        userDefaults.set(data, forKey: storageKey)
    }

    public func clear() {
        userDefaults.removeObject(forKey: storageKey)
    }
}
