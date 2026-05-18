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
        let categoryID = UUID()
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
            ],
            categories: [
                GroceryCategorySummary(id: categoryID, name: "Produce", colorHex: "#00ff00")
            ],
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: categoryID, sortOrder: 0)
            ]
        )

        #expect(state.favoriteList?.id == favoriteListID)
        #expect(state.favoriteListName == "Weekly shop")
        #expect(state.canQuickAdd == true)
        #expect(state.categories.map(\.name) == ["Produce"])
        #expect(state.categoryOrder.map(\.categoryID) == [categoryID])
    }

    @Test func decodesLegacyStateWithoutSyncedCategoryMetadata() throws {
        let listID = UUID()
        let payload = """
        {
          "backendURL": "https://api.example.com",
          "authToken": "token",
          "favoriteListID": "\(listID.uuidString)",
          "quickAddItemName": "Milk",
          "lists": [],
          "items": []
        }
        """

        let state = try JSONDecoder().decode(SharedAppState.self, from: Data(payload.utf8))

        #expect(state.backendURL == URL(string: "https://api.example.com"))
        #expect(state.authToken == "token")
        #expect(state.favoriteListID == listID)
        #expect(state.categories == [])
        #expect(state.categoryOrder == [])
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
        let categoryID = UUID()
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
            ],
            categories: [
                GroceryCategorySummary(id: categoryID, name: "Bakery", colorHex: "#cccccc")
            ],
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: categoryID, sortOrder: 1)
            ]
        )

        store.save(state)

        #expect(store.load() == state)

        store.clear()

        #expect(store.load() == SharedAppState())
    }
}
