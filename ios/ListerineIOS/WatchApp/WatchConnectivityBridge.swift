import Foundation
import ListerineCore
import os.log
#if canImport(WatchConnectivity)
import WatchConnectivity

private let watchConnectivityLog = Logger(
    subsystem: "de.malaber.listerine.watch",
    category: "connectivity"
)

final class WatchConnectivityBridge: NSObject {
    var onStateUpdate: ((SharedAppState) -> Void)?
    var onReachabilityChange: (() -> Void)?

    private let session: WCSession?
    private let store: SharedAppStateStore
    private let decoder = JSONDecoder()

    init(
        session: WCSession? = WCSession.isSupported() ? WCSession.default : nil,
        store: SharedAppStateStore = WatchSharedContainer.stateStore
    ) {
        self.session = session
        self.store = store
        super.init()
        self.session?.delegate = self
        self.session?.activate()
    }

    var isCompanionAppInstalled: Bool {
        session?.isCompanionAppInstalled ?? false
    }

    var isReachable: Bool {
        session?.isReachable ?? false
    }

    func requestLatestState() {
        Task {
            _ = await requestLatestStateAsync()
        }
    }

    func requestLatestStateAsync() async -> SharedAppState? {
        if
            let session,
            let state = decodedState(from: session.receivedApplicationContext)
        {
            watchConnectivityLog.debug(
                "Using cached application context. lists=\(state.lists.count) auth=\(state.authToken?.isEmpty == false) favorite=\(state.favoriteListID?.uuidString ?? "nil", privacy: .public)"
            )
            apply(state)
            return state
        }

        guard let session else {
            watchConnectivityLog.error("WCSession unavailable on watch.")
            return nil
        }
        guard session.isReachable else {
            watchConnectivityLog.error(
                "WCSession not reachable. companionInstalled=\(session.isCompanionAppInstalled)"
            )
            return nil
        }
        watchConnectivityLog.debug("Requesting latest state from iPhone via sendMessage.")
        return await withCheckedContinuation { continuation in
            session.sendMessage(
                ["command": "syncState"],
                replyHandler: { [weak self] payload in
                    watchConnectivityLog.debug("Received syncState reply from iPhone.")
                    let state = self?.handle(payload)
                    continuation.resume(returning: state)
                },
                errorHandler: { error in
                    watchConnectivityLog.error(
                        "syncState request failed: \(error.localizedDescription, privacy: .public)"
                    )
                    continuation.resume(returning: nil)
                }
            )
        }
    }

    @discardableResult
    private func handle(_ payload: [String: Any]) -> SharedAppState? {
        guard let state = decodedState(from: payload) else { return nil }
        apply(state)
        return state
    }

    private func decodedState(from payload: [String: Any]) -> SharedAppState? {
        guard
            let data = payload[ListerineSharedConstants.watchContextPayloadKey] as? Data,
            let state = try? decoder.decode(SharedAppState.self, from: data)
        else {
            watchConnectivityLog.error(
                "Failed to decode shared state. payloadKeys=\(payload.keys.sorted().joined(separator: ","), privacy: .public)"
            )
            return nil
        }

        return state
    }

    private func apply(_ state: SharedAppState) {
        watchConnectivityLog.debug(
            "Applying shared state. lists=\(state.lists.count) auth=\(state.authToken?.isEmpty == false) favorite=\(state.favoriteListID?.uuidString ?? "nil", privacy: .public)"
        )
        store.save(state)
        DispatchQueue.main.async { [weak self] in
            self?.onStateUpdate?(state)
        }
    }
}

extension WatchConnectivityBridge: WCSessionDelegate {
    func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: (any Error)?
    ) {
        watchConnectivityLog.debug(
            "WCSession activation completed. state=\(activationState.rawValue) error=\(error?.localizedDescription ?? "none", privacy: .public)"
        )
        if activationState == .activated {
            requestLatestState()
        }
    }

    func sessionReachabilityDidChange(_ session: WCSession) {
        watchConnectivityLog.debug("WCSession reachability changed. reachable=\(session.isReachable)")
        DispatchQueue.main.async { [weak self] in
            self?.onReachabilityChange?()
        }
    }

    func session(
        _ session: WCSession,
        didReceiveApplicationContext applicationContext: [String: Any]
    ) {
        watchConnectivityLog.debug("Received application context from iPhone.")
        handle(applicationContext)
    }
}
#else
final class WatchConnectivityBridge {
    var onStateUpdate: ((SharedAppState) -> Void)?
    var onReachabilityChange: (() -> Void)?

    func requestLatestState() {}

    func requestLatestStateAsync() async -> SharedAppState? { nil }

    var isCompanionAppInstalled: Bool { false }

    var isReachable: Bool { false }
}
#endif
