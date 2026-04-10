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
    @Published private(set) var selectedListID: UUID?
    @Published var draftItemName = ""
    @Published var errorMessage: String?
    @Published private(set) var isWorking = false
    @Published private(set) var isCompanionAppInstalled = false
    @Published private(set) var isPhoneReachable = false

    private let store: SharedAppStateStore
    private let backendClient: WatchBackendClient
    private let connectivityBridge: WatchConnectivityBridge

    init(
        store: SharedAppStateStore = WatchSharedContainer.stateStore,
        backendClient: WatchBackendClient = WatchBackendClient(),
        connectivityBridge: WatchConnectivityBridge = WatchConnectivityBridge()
    ) {
        self.store = store
        self.backendClient = backendClient
        self.connectivityBridge = connectivityBridge
        state = store.load()
        selectedListID = store.load().favoriteListID
        self.connectivityBridge.onStateUpdate = { [weak self] updatedState in
            self?.applySyncedState(updatedState)
        }
        self.connectivityBridge.onReachabilityChange = { [weak self] in
            self?.refreshConnectivityStatus()
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

    var needsPhoneSetup: Bool {
        state.hasAuthenticatedSession == false
    }

    var setupButtonTitle: String {
        isPhoneReachable ? "Sync from iPhone" : "Open and unlock iPhone app"
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
        }
        await refreshSelectedList()
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
        store.save(updatedState)
    }

    private func refreshSelectedList() async {
        guard
            needsPhoneSetup == false,
            let selectedListID
        else {
            return
        }

        await runAction { [self] in
            try await self.backendClient.refreshItems(for: selectedListID, using: self.state)
        }
    }

    private func applySyncedState(_ updatedState: SharedAppState) {
        state = updatedState
        if selectedListID == nil || displayedLists.contains(where: { $0.id == selectedListID }) == false {
            selectedListID = updatedState.favoriteListID ?? updatedState.lists.first?.id
        }
        store.save(updatedState)
    }

    private func refreshConnectivityStatus() {
        isCompanionAppInstalled = connectivityBridge.isCompanionAppInstalled
        isPhoneReachable = connectivityBridge.isReachable
    }
}
