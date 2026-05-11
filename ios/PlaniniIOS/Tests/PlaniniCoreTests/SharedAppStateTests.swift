import Foundation
import Testing
@testable import PlaniniCore

struct SharedAppStateTests {
    @Test func defaultStateUsesQuickAddFallback() {
        let state = SharedAppState()

        #expect(state.quickAddItemName == "Milk")
        #expect(state.hasAuthenticatedSession == false)
        #expect(state.canQuickAdd == false)
    }

    @Test func favoriteListResolvesFromLists() {
        let favoriteListID = UUID()
        let state = SharedAppState(
            backendURL: URL(string: "https://api.example.com"),
            authToken: "token",
            favoriteListID: favoriteListID,
            quickAddItemName: "Bananas",
            lists: [
                GroceryListSummary(
                    id: favoriteListID,
                    householdID: UUID(),
                    householdName: "Home",
                    name: "Weekly shop",
                    archived: false
                )
            ]
        )

        #expect(state.favoriteList?.id == favoriteListID)
        #expect(state.favoriteListName == "Weekly shop")
        #expect(state.canQuickAdd == true)
    }

    @Test func quickAddRequiresTrimmedNameFavoriteListAndSession() {
        let state = SharedAppState(
            backendURL: URL(string: "https://api.example.com"),
            authToken: "token",
            favoriteListID: UUID(),
            quickAddItemName: "   "
        )

        #expect(state.canQuickAdd == false)
    }

    @Test func storeLoadsDefaultWhenMissingOrInvalid() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = SharedAppStateStore(userDefaults: defaults, storageKey: "state")

        #expect(store.load() == SharedAppState())

        defaults.set(Data("not-json".utf8), forKey: "state")

        #expect(store.load() == SharedAppState())
    }

    @Test func storePersistsAndClearsState() {
        let defaults = UserDefaults(suiteName: #function)!
        defaults.removePersistentDomain(forName: #function)
        let store = SharedAppStateStore(userDefaults: defaults, storageKey: "state")
        let listID = UUID()
        let itemID = UUID()
        let state = SharedAppState(
            backendURL: URL(string: "https://api.example.com"),
            authToken: "secret",
            displayName: "Alex",
            favoriteListID: listID,
            quickAddItemName: "Apples",
            lists: [
                GroceryListSummary(
                    id: listID,
                    householdID: UUID(),
                    householdName: "Home",
                    name: "Groceries",
                    archived: false
                )
            ],
            items: [
                GroceryItemRecord(
                    id: itemID,
                    listID: listID,
                    name: "Bread",
                    quantityText: "2",
                    note: nil,
                    categoryID: nil,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 1
                )
            ]
        )

        store.save(state)

        #expect(store.load() == state)

        store.clear()

        #expect(store.load() == SharedAppState())
    }
}
