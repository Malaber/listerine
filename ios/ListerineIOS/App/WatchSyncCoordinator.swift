import Foundation
import ListerineCore
import os.log
#if canImport(WatchConnectivity)
import WatchConnectivity

private let watchSyncLog = Logger(
    subsystem: "de.malaber.listerine.ios",
    category: "watch-sync"
)

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
            watchSyncLog.error("Skipping watch state publish because session/provider/encoding was unavailable.")
            return
        }

        if let state = try? JSONDecoder().decode(SharedAppState.self, from: data) {
            watchSyncLog.debug(
                "Publishing state to watch. lists=\(state.lists.count) auth=\(state.authToken?.isEmpty == false) favorite=\(state.favoriteListID?.uuidString ?? "nil", privacy: .public)"
            )
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
        watchSyncLog.debug(
            "WCSession activation completed on phone. state=\(activationState.rawValue) error=\(error?.localizedDescription ?? "none", privacy: .public)"
        )
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
            watchSyncLog.error("Received unsupported watch message or failed to encode state.")
            replyHandler([:])
            return
        }

        if let state = try? JSONDecoder().decode(SharedAppState.self, from: data) {
            watchSyncLog.debug(
                "Replying to syncState request. lists=\(state.lists.count) auth=\(state.authToken?.isEmpty == false) favorite=\(state.favoriteListID?.uuidString ?? "nil", privacy: .public)"
            )
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
