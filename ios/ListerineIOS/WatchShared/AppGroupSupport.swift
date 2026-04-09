import Foundation
import ListerineCore

enum WatchSharedContainer {
    static let groupID = ListerineSharedConstants.watchAppGroupID

    static var userDefaults: UserDefaults {
        UserDefaults(suiteName: groupID) ?? .standard
    }

    static var stateStore: SharedAppStateStore {
        SharedAppStateStore(userDefaults: userDefaults)
    }
}
