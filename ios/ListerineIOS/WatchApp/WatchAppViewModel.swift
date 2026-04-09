import Foundation
import ListerineCore
import SwiftUI

@MainActor
final class WatchAppViewModel: ObservableObject {
    @Published private(set) var state: SharedAppState
    @Published var draftItemName = ""
    @Published var errorMessage: String?
    @Published private(set) var isWorking = false

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
        self.connectivityBridge.onStateUpdate = { [weak self] updatedState in
            self?.state = updatedState
        }
    }

    var favoriteListName: String {
        state.favoriteListName ?? "Favorite list"
    }

    var quickAddLabel: String {
        state.quickAddItemName
    }

    var needsPhoneSetup: Bool {
        state.hasAuthenticatedSession == false || state.favoriteListID == nil
    }

    func onAppear() {
        connectivityBridge.requestLatestState()
    }

    func refresh() async {
        connectivityBridge.requestLatestState()
        guard needsPhoneSetup == false else { return }
        await runAction { [self] in
            try await self.backendClient.refreshFavoriteItems(using: self.state)
        }
    }

    func addDraftItem() async {
        let name = draftItemName
        draftItemName = ""
        await runAction { [self] in
            try await self.backendClient.addItem(named: name, using: self.state)
        }
    }

    func quickAdd() async {
        await runAction { [self] in
            try await self.backendClient.addItem(named: self.state.quickAddItemName, using: self.state)
        }
    }

    func toggle(_ item: GroceryItemRecord) async {
        await runAction { [self] in
            try await self.backendClient.toggle(item, using: self.state)
        }
    }

    private func runAction(_ operation: @escaping () async throws -> SharedAppState) async {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        do {
            let updatedState = try await operation()
            state = updatedState
            store.save(updatedState)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
