import Foundation
import ListerineCore
#if canImport(WatchConnectivity)
import WatchConnectivity

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
            apply(state)
            return state
        }

        guard let session, session.isReachable else { return nil }
        return await withCheckedContinuation { continuation in
            session.sendMessage(
                ["command": "syncState"],
                replyHandler: { [weak self] payload in
                    let state = self?.handle(payload)
                    continuation.resume(returning: state)
                },
                errorHandler: { _ in
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
            return nil
        }

        return state
    }

    private func apply(_ state: SharedAppState) {
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

    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async { [weak self] in
            self?.onReachabilityChange?()
        }
    }

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
    var onReachabilityChange: (() -> Void)?

    func requestLatestState() {}

    func requestLatestStateAsync() async -> SharedAppState? { nil }

    var isCompanionAppInstalled: Bool { false }

    var isReachable: Bool { false }
}
#endif
