import Foundation
import ListerineCore
#if canImport(WatchConnectivity)
import WatchConnectivity

final class WatchConnectivityBridge: NSObject {
    var onStateUpdate: ((SharedAppState) -> Void)?

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

    func requestLatestState() {
        guard let session, session.isReachable else { return }
        session.sendMessage(["command": "syncState"], replyHandler: { [weak self] payload in
            self?.handle(payload)
        })
    }

    private func handle(_ payload: [String: Any]) {
        guard
            let data = payload[ListerineSharedConstants.watchContextPayloadKey] as? Data,
            let state = try? decoder.decode(SharedAppState.self, from: data)
        else {
            return
        }

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
        if activationState == .activated {
            requestLatestState()
        }
    }

    func sessionReachabilityDidChange(_ session: WCSession) {}

    func session(
        _ session: WCSession,
        didReceiveApplicationContext applicationContext: [String: Any]
    ) {
        handle(applicationContext)
    }
}
#else
final class WatchConnectivityBridge {
    var onStateUpdate: ((SharedAppState) -> Void)?

    func requestLatestState() {}
}
#endif
