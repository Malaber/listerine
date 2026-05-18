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
    public var categories: [GroceryCategorySummary]
    public var categoryOrder: [ListCategoryOrderEntry]

    public init(
        backendURL: URL? = nil,
        authToken: String? = nil,
        displayName: String? = nil,
        favoriteListID: UUID? = nil,
        quickAddItemName: String = SharedAppState.defaultQuickAddItemName,
        lists: [GroceryListSummary] = [],
        items: [GroceryItemRecord] = [],
        categories: [GroceryCategorySummary] = [],
        categoryOrder: [ListCategoryOrderEntry] = []
    ) {
        self.backendURL = backendURL
        self.authToken = authToken
        self.displayName = displayName
        self.favoriteListID = favoriteListID
        self.quickAddItemName = quickAddItemName
        self.lists = lists
        self.items = items
        self.categories = categories
        self.categoryOrder = categoryOrder
    }

    private enum CodingKeys: String, CodingKey {
        case backendURL
        case authToken
        case displayName
        case favoriteListID
        case quickAddItemName
        case lists
        case items
        case categories
        case categoryOrder
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        backendURL = try container.decodeIfPresent(URL.self, forKey: .backendURL)
        authToken = try container.decodeIfPresent(String.self, forKey: .authToken)
        displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        favoriteListID = try container.decodeIfPresent(UUID.self, forKey: .favoriteListID)
        quickAddItemName = try container.decodeIfPresent(String.self, forKey: .quickAddItemName)
            ?? SharedAppState.defaultQuickAddItemName
        lists = try container.decodeIfPresent([GroceryListSummary].self, forKey: .lists) ?? []
        items = try container.decodeIfPresent([GroceryItemRecord].self, forKey: .items) ?? []
        categories = try container.decodeIfPresent([GroceryCategorySummary].self, forKey: .categories) ?? []
        categoryOrder = try container.decodeIfPresent([ListCategoryOrderEntry].self, forKey: .categoryOrder) ?? []
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
