import Foundation

public enum AppearanceMode: String, CaseIterable, Identifiable, Sendable {
    case system
    case light
    case dark

    public var id: String { rawValue }

    public var settingsLabel: String {
        switch self {
        case .system:
            return "System"
        case .light:
            return "Light"
        case .dark:
            return "Dark"
        }
    }
}

public protocol AppearanceModeStoring: Sendable {
    func load() -> AppearanceMode
    func save(_ mode: AppearanceMode)
    func clear()
}

public final class AppearanceModeStore: AppearanceModeStoring, @unchecked Sendable {
    public static let storageKey = "planini.appearance-mode"

    private let userDefaults: UserDefaults
    private let appearanceModeKey: String

    public init(
        userDefaults: UserDefaults = .standard,
        appearanceModeKey: String = AppearanceModeStore.storageKey
    ) {
        self.userDefaults = userDefaults
        self.appearanceModeKey = appearanceModeKey
    }

    public func load() -> AppearanceMode {
        guard
            let storedMode = userDefaults.string(forKey: appearanceModeKey),
            let mode = AppearanceMode(rawValue: storedMode)
        else {
            return .system
        }
        return mode
    }

    public func save(_ mode: AppearanceMode) {
        userDefaults.set(mode.rawValue, forKey: appearanceModeKey)
    }

    public func clear() {
        userDefaults.removeObject(forKey: appearanceModeKey)
    }
}
