import Foundation

public struct SharedAppState: Codable, Equatable, Sendable {
    public static let defaultQuickAddItemName = "Milk"

    public var backendURL: URL?
    public var authToken: String?
    public var displayName: String?
    public var favoriteListID: UUID?
    public var quickAddItemName: String
    public var lists: [GroceryListSummary]
    public var items: [GroceryItemRecord]

    public init(
        backendURL: URL? = nil,
        authToken: String? = nil,
        displayName: String? = nil,
        favoriteListID: UUID? = nil,
        quickAddItemName: String = SharedAppState.defaultQuickAddItemName,
        lists: [GroceryListSummary] = [],
        items: [GroceryItemRecord] = []
    ) {
        self.backendURL = backendURL
        self.authToken = authToken
        self.displayName = displayName
        self.favoriteListID = favoriteListID
        self.quickAddItemName = quickAddItemName
        self.lists = lists
        self.items = items
    }

    public var favoriteList: GroceryListSummary? {
        guard let favoriteListID else { return nil }
        return lists.first { $0.id == favoriteListID }
    }

    public var favoriteListName: String? {
        favoriteList?.name
    }

    public var hasAuthenticatedSession: Bool {
        backendURL != nil && !(authToken?.isEmpty ?? true)
    }

    public var canQuickAdd: Bool {
        hasAuthenticatedSession
            && favoriteListID != nil
            && quickAddItemName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }
}

public enum PlaniniSharedConstants {
    public static let watchAppGroupID = "group.de.malaber.planini.watch"
    public static let sharedAppStateKey = "planini.shared-app-state"
    public static let watchContextPayloadKey = "state"
}
