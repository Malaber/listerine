import Foundation
import ListerineCore
import os.log
import SwiftUI

private let watchAppLog = Logger(
    subsystem: "de.malaber.listerine.watch",
    category: "view-model"
)

@MainActor
final class WatchAppViewModel: ObservableObject {
    @Published private(set) var state: SharedAppState
    @Published private(set) var categories: [GroceryCategorySummary] = []
    @Published private(set) var selectedListID: UUID?
    @Published var draftItemName = ""
    @Published var errorMessage: String?
    @Published private(set) var isWorking = false
    @Published private(set) var isCompanionAppInstalled = false
    @Published private(set) var isPhoneReachable = false

    private let store: SharedAppStateStore
    private let backendClient: WatchBackendClient
    private let connectivityBridge: WatchConnectivityBridge
    private let liveUpdates: WatchListLiveUpdateClient

    init(
        store: SharedAppStateStore = WatchSharedContainer.stateStore,
        backendClient: WatchBackendClient = WatchBackendClient(),
        connectivityBridge: WatchConnectivityBridge = WatchConnectivityBridge(),
        liveUpdates: WatchListLiveUpdateClient = WatchListLiveUpdateClient()
    ) {
        self.store = store
        self.backendClient = backendClient
        self.connectivityBridge = connectivityBridge
        self.liveUpdates = liveUpdates
        state = store.load()
        selectedListID = store.load().favoriteListID
        self.connectivityBridge.onStateUpdate = { [weak self] updatedState in
            self?.applySyncedState(updatedState)
        }
        self.connectivityBridge.onReachabilityChange = { [weak self] in
            self?.refreshConnectivityStatus()
        }
        self.liveUpdates.onListChanged = { [weak self] listID in
            Task { @MainActor in
                await self?.handleLiveListChanged(listID)
            }
        }
        refreshConnectivityStatus()
    }

    var displayedLists: [GroceryListSummary] {
        let favoriteID = state.favoriteListID
        return state.lists.sorted { left, right in
            if left.id == favoriteID, right.id != favoriteID {
                return true
            }
            if left.id != favoriteID, right.id == favoriteID {
                return false
            }
            if left.householdName != right.householdName {
                return left.householdName.localizedCaseInsensitiveCompare(right.householdName) == .orderedAscending
            }
            return left.name.localizedCaseInsensitiveCompare(right.name) == .orderedAscending
        }
    }

    func isFavorite(_ list: GroceryListSummary) -> Bool {
        list.id == state.favoriteListID
    }

    func items(for list: GroceryListSummary) -> [GroceryItemRecord] {
        guard selectedListID == list.id else { return [] }
        return state.items.sorted { left, right in
            if left.checked != right.checked {
                return left.checked == false
            }
            return left.sortOrder < right.sortOrder
        }
    }

    func categoryColorHex(for item: GroceryItemRecord) -> String? {
        guard let categoryID = item.categoryID else { return nil }
        return categories.first(where: { $0.id == categoryID })?.colorHex
    }

    var availableCategories: [GroceryCategorySummary] {
        categories.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var needsPhoneSetup: Bool {
        state.hasAuthenticatedSession == false
    }

    var setupButtonTitle: String {
        isPhoneReachable ? "Sync from iPhone" : "Open and unlock iPhone app"
    }

    func performInitialLoad() async {
        await Task.yield()
        connectivityBridge.requestLatestState()
        refreshConnectivityStatus()
        await refresh()
    }

    func onAppear() {
        connectivityBridge.requestLatestState()
        refreshConnectivityStatus()
    }

    func refresh() async {
        watchAppLog.debug("Manual watch refresh started.")
        await syncLatestState()
        await refreshSelectedList()
    }

    func showList(_ list: GroceryListSummary) async {
        if selectedListID != list.id {
            selectedListID = list.id
            if state.items.first?.listID != list.id {
                state.items = []
            }
            categories = []
        }
        await refreshSelectedList()
    }

    func startLiveUpdates(for list: GroceryListSummary) {
        liveUpdates.connect(listID: list.id, using: state)
    }

    func stopLiveUpdates(for list: GroceryListSummary) {
        liveUpdates.disconnect(listID: list.id)
    }

    func addDraftItem(to list: GroceryListSummary) async {
        let name = draftItemName
        draftItemName = ""
        await runAction { [self] in
            try await self.backendClient.addItem(named: name, to: list.id, using: self.state)
        }
    }

    func toggle(_ item: GroceryItemRecord, in list: GroceryListSummary) async {
        await runAction { [self] in
            try await self.backendClient.toggle(item, in: list.id, using: self.state)
        }
    }

    func saveEdit(
        item: GroceryItemRecord,
        note: String,
        categoryID: UUID?,
        in list: GroceryListSummary
    ) async -> Bool {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        do {
            await syncLatestState()
            let snapshot = try await backendClient.saveEdit(
                item: item,
                note: note,
                categoryID: categoryID,
                in: list.id,
                using: state
            )
            applySnapshot(snapshot)
            watchAppLog.debug("Watch item edit completed successfully.")
            return true
        } catch {
            if let backendError = error as? WatchBackendClientError, backendError == .unauthorized {
                clearAuthenticatedSession()
            }
            watchAppLog.error("Watch item edit failed: \(error.localizedDescription, privacy: .public)")
            errorMessage = error.localizedDescription
            return false
        }
    }

    private func runAction(_ operation: @escaping () async throws -> SharedAppState) async {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        do {
            await syncLatestState()
            let updatedState = try await operation()
            state = updatedState
            store.save(updatedState)
            watchAppLog.debug("Watch action completed successfully.")
        } catch {
            if let backendError = error as? WatchBackendClientError, backendError == .unauthorized {
                clearAuthenticatedSession()
            }
            watchAppLog.error("Watch action failed: \(error.localizedDescription, privacy: .public)")
            errorMessage = error.localizedDescription
        }
    }

    private func syncLatestState() async {
        refreshConnectivityStatus()
        guard let updatedState = await connectivityBridge.requestLatestStateAsync() else {
            watchAppLog.error(
                "No shared state returned from iPhone. companionInstalled=\(self.isCompanionAppInstalled) reachable=\(self.isPhoneReachable)"
            )
            return
        }
        watchAppLog.debug(
            "Synced shared state from iPhone. lists=\(updatedState.lists.count) auth=\(updatedState.authToken?.isEmpty == false) favorite=\(updatedState.favoriteListID?.uuidString ?? "nil", privacy: .public)"
        )
        applySyncedState(updatedState)
        refreshConnectivityStatus()
    }

    private func clearAuthenticatedSession() {
        var updatedState = state
        updatedState.authToken = nil
        updatedState.items = []
        state = updatedState
        categories = []
        store.save(updatedState)
        liveUpdates.disconnect()
    }

    private func refreshSelectedList() async {
        guard
            needsPhoneSetup == false,
            let selectedListID
        else {
            return
        }

        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        do {
            await syncLatestState()
            let snapshot = try await backendClient.refreshList(for: selectedListID, using: state)
            applySnapshot(snapshot)
            watchAppLog.debug("Watch list refresh completed successfully.")
        } catch {
            if let backendError = error as? WatchBackendClientError, backendError == .unauthorized {
                clearAuthenticatedSession()
            }
            watchAppLog.error("Watch list refresh failed: \(error.localizedDescription, privacy: .public)")
            errorMessage = error.localizedDescription
        }
    }

    private func applySyncedState(_ updatedState: SharedAppState) {
        state = updatedState
        if selectedListID == nil || displayedLists.contains(where: { $0.id == selectedListID }) == false {
            selectedListID = updatedState.favoriteListID ?? updatedState.lists.first?.id
        }
        store.save(updatedState)
        if let selectedListID {
            liveUpdates.connect(listID: selectedListID, using: updatedState)
        } else {
            liveUpdates.disconnect()
        }
    }

    private func refreshConnectivityStatus() {
        isCompanionAppInstalled = connectivityBridge.isCompanionAppInstalled
        isPhoneReachable = connectivityBridge.isReachable
    }

    private func handleLiveListChanged(_ listID: UUID) async {
        guard selectedListID == listID, needsPhoneSetup == false else { return }
        watchAppLog.debug("Received live list update for selected list.")
        await refreshListItemsSilently(for: listID)
    }

    private func refreshListItemsSilently(for listID: UUID) async {
        do {
            let snapshot = try await backendClient.refreshList(for: listID, using: state)
            state = snapshot.state
            categories = snapshot.categories
            store.save(snapshot.state)
        } catch {
            if let backendError = error as? WatchBackendClientError, backendError == .unauthorized {
                clearAuthenticatedSession()
            }
            watchAppLog.error(
                "Silent live refresh failed: \(error.localizedDescription, privacy: .public)"
            )
        }
    }

    private func applySnapshot(_ snapshot: WatchListSnapshot) {
        state = snapshot.state
        categories = snapshot.categories
        store.save(snapshot.state)
    }
}

final class WatchListLiveUpdateClient {
    var onListChanged: ((UUID) -> Void)?

    private var webSocketTask: URLSessionWebSocketTask?
    private var reconnectTask: Task<Void, Never>?
    private var currentListID: UUID?
    private var backendURL: URL?
    private var authToken: String?

    func connect(listID: UUID, using state: SharedAppState) {
        guard
            let backendURL = state.backendURL,
            let authToken = state.authToken,
            authToken.isEmpty == false
        else {
            disconnect()
            return
        }

        if
            currentListID == listID,
            self.backendURL == backendURL,
            self.authToken == authToken,
            webSocketTask != nil
        {
            return
        }

        disconnect()
        currentListID = listID
        self.backendURL = backendURL
        self.authToken = authToken
        openSocket()
    }

    func disconnect(listID: UUID? = nil) {
        if let listID, currentListID != listID {
            return
        }

        reconnectTask?.cancel()
        reconnectTask = nil
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        currentListID = nil
        backendURL = nil
        authToken = nil
    }

    private func openSocket() {
        guard
            let currentListID,
            let backendURL,
            let authToken,
            let url = makeWebSocketURL(
                backendURL: backendURL,
                listID: currentListID,
                authToken: authToken
            )
        else {
            return
        }

        watchAppLog.debug(
            "Connecting live updates socket for list \(currentListID.uuidString, privacy: .public)."
        )
        let task = URLSession.shared.webSocketTask(with: url)
        webSocketTask = task
        task.resume()
        receiveNextMessage(from: task, listID: currentListID)
    }

    private func receiveNextMessage(from task: URLSessionWebSocketTask, listID: UUID) {
        task.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case let .success(message):
                self.handle(message, for: listID)
                if self.webSocketTask === task {
                    self.receiveNextMessage(from: task, listID: listID)
                }
            case let .failure(error):
                watchAppLog.error(
                    "Live updates socket failed: \(error.localizedDescription, privacy: .public)"
                )
                self.scheduleReconnect()
            }
        }
    }

    private func handle(_ message: URLSessionWebSocketTask.Message, for listID: UUID) {
        let data: Data?
        switch message {
        case let .data(payload):
            data = payload
        case let .string(text):
            data = text.data(using: .utf8)
        @unknown default:
            data = nil
        }

        guard
            let data,
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let type = payload["type"] as? String
        else {
            return
        }

        let liveUpdateTypes: Set<String> = [
            "list_snapshot",
            "item_created",
            "item_updated",
            "item_checked",
            "item_unchecked",
            "item_deleted",
            "category_order_updated",
        ]
        guard liveUpdateTypes.contains(type) else { return }

        watchAppLog.debug(
            "Received live updates event \(type, privacy: .public) for list \(listID.uuidString, privacy: .public)."
        )
        onListChanged?(listID)
    }

    private func scheduleReconnect() {
        guard currentListID != nil, backendURL != nil, authToken != nil else { return }
        reconnectTask?.cancel()
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            guard Task.isCancelled == false else { return }
            self?.openSocket()
        }
    }

    private func makeWebSocketURL(
        backendURL: URL,
        listID: UUID,
        authToken: String
    ) -> URL? {
        guard var components = URLComponents(url: backendURL, resolvingAgainstBaseURL: false) else {
            return nil
        }
        components.scheme = backendURL.scheme == "https" ? "wss" : "ws"
        let basePath = components.path == "/" ? "" : components.path
        components.path = "\(basePath)/api/v1/ws/lists/\(listID.uuidString)"
        components.queryItems = (components.queryItems ?? []) + [
            URLQueryItem(name: "token", value: authToken)
        ]
        return components.url
    }
}
