import Foundation
import ListerineCore
#if canImport(WatchConnectivity)
import WatchConnectivity

final class WatchSyncCoordinator: NSObject {
    static let shared = WatchSyncCoordinator()

    private let session: WCSession?
    private var stateProvider: (() -> SharedAppState)?
    private let encoder = JSONEncoder()

    init(session: WCSession? = WCSession.isSupported() ? WCSession.default : nil) {
        self.session = session
        super.init()
        self.session?.delegate = self
        self.session?.activate()
    }

    func setStateProvider(_ provider: @escaping () -> SharedAppState) {
        stateProvider = provider
    }

    func publishCurrentState() {
        guard
            let session,
            let stateProvider,
            let data = try? encoder.encode(stateProvider())
        else {
            return
        }

        try? session.updateApplicationContext([ListerineSharedConstants.watchContextPayloadKey: data])
    }
}

extension WatchSyncCoordinator: WCSessionDelegate {
    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: (any Error)?
    ) {
        if activationState == .activated {
            publishCurrentState()
        }
    }

    #if os(iOS)
        func sessionDidBecomeInactive(_ session: WCSession) {}

        func sessionDidDeactivate(_ session: WCSession) {
            session.activate()
        }
    #endif

    func session(
        _ session: WCSession,
        didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        guard
            message["command"] as? String == "syncState",
            let stateProvider,
            let data = try? encoder.encode(stateProvider())
        else {
            replyHandler([:])
            return
        }

        replyHandler([ListerineSharedConstants.watchContextPayloadKey: data])
    }
}
#else
final class WatchSyncCoordinator {
    static let shared = WatchSyncCoordinator()

    func setStateProvider(_ provider: @escaping () -> SharedAppState) {
        _ = provider
    }

    func publishCurrentState() {}
}
#endif
