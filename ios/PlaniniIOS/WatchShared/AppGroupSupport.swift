import Foundation
import PlaniniCore

enum WatchSharedContainer {
    static let groupID = PlaniniSharedConstants.watchAppGroupID

    static var userDefaults: UserDefaults {
        UserDefaults(suiteName: groupID) ?? .standard
    }

    static var stateStore: SharedAppStateStore {
        SharedAppStateStore(userDefaults: userDefaults)
    }
}
