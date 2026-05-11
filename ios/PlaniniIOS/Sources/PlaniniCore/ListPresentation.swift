import Foundation

public struct GroceryListSummary: Identifiable, Equatable, Codable, Sendable {
    public let id: UUID
    public let householdID: UUID
    public let householdName: String
    public let name: String
    public let archived: Bool

    public init(id: UUID, householdID: UUID, householdName: String, name: String, archived: Bool) {
        self.id = id
        self.householdID = householdID
        self.householdName = householdName
        self.name = name
        self.archived = archived
    }
}

public struct GroceryCategorySummary: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let name: String
    public let colorHex: String?

    public init(id: UUID, name: String, colorHex: String?) {
        self.id = id
        self.name = name
        self.colorHex = colorHex
    }

    public init?(json: [String: Any]) {
        guard
            let idText = json["id"] as? String,
            let id = UUID(uuidString: idText),
            let name = json["name"] as? String
        else {
            return nil
        }

        self.init(id: id, name: name, colorHex: json["color"] as? String)
    }
}

public struct ListCategoryOrderEntry: Equatable, Sendable {
    public let categoryID: UUID
    public let sortOrder: Int

    public init(categoryID: UUID, sortOrder: Int) {
        self.categoryID = categoryID
        self.sortOrder = sortOrder
    }

    public init?(json: [String: Any]) {
        guard
            let categoryIDText = json["category_id"] as? String,
            let categoryID = UUID(uuidString: categoryIDText),
            let sortOrder = json["sort_order"] as? Int
        else {
            return nil
        }

        self.init(categoryID: categoryID, sortOrder: sortOrder)
    }
}

public struct GroceryItemRecord: Identifiable, Equatable, Codable, Sendable {
    public let id: UUID
    public let listID: UUID
    public let name: String
    public let quantityText: String?
    public let note: String?
    public let categoryID: UUID?
    public let checked: Bool
    public let checkedAt: Date?
    public let sortOrder: Int

    public init(
        id: UUID,
        listID: UUID,
        name: String,
        quantityText: String?,
        note: String?,
        categoryID: UUID?,
        checked: Bool,
        checkedAt: Date?,
        sortOrder: Int
    ) {
        self.id = id
        self.listID = listID
        self.name = name
        self.quantityText = quantityText
        self.note = note
        self.categoryID = categoryID
        self.checked = checked
        self.checkedAt = checkedAt
        self.sortOrder = sortOrder
    }

    public init?(json: [String: Any]) {
        guard
            let idText = json["id"] as? String,
            let id = UUID(uuidString: idText),
            let listIDText = json["list_id"] as? String,
            let listID = UUID(uuidString: listIDText),
            let name = json["name"] as? String
        else {
            return nil
        }

        let checkedAt: Date?
        if let checkedAtText = json["checked_at"] as? String {
            checkedAt = Self.parseCheckedAt(checkedAtText)
        } else {
            checkedAt = nil
        }

        self.init(
            id: id,
            listID: listID,
            name: name,
            quantityText: json["quantity_text"] as? String,
            note: json["note"] as? String,
            categoryID: (json["category_id"] as? String).flatMap(UUID.init(uuidString:)),
            checked: (json["checked"] as? Bool) ?? false,
            checkedAt: checkedAt,
            sortOrder: (json["sort_order"] as? Int) ?? 0
        )
    }

    private static func parseCheckedAt(_ value: String) -> Date? {
        let formatterWithFractions = ISO8601DateFormatter()
        formatterWithFractions.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let parsed = formatterWithFractions.date(from: value) {
            return parsed
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
}

public enum GroceryItemSectionKind: Hashable, Sendable {
    case uncategorized
    case category(UUID)
    case checked
}

public struct GroceryItemSection: Identifiable, Equatable, Sendable {
    public let kind: GroceryItemSectionKind
    public let title: String
    public let itemCount: Int
    public let colorHex: String?
    public let items: [GroceryItemRecord]

    public init(
        kind: GroceryItemSectionKind,
        title: String,
        itemCount: Int,
        colorHex: String?,
        items: [GroceryItemRecord]
    ) {
        self.kind = kind
        self.title = title
        self.itemCount = itemCount
        self.colorHex = colorHex
        self.items = items
    }

    public var id: String {
        switch kind {
        case .uncategorized:
            return "uncategorized"
        case let .category(categoryID):
            return "category-\(categoryID.uuidString)"
        case .checked:
            return "checked"
        }
    }
}

public enum GroceryItemSectionBuilder {
    public static func build(
        items: [GroceryItemRecord],
        categories: [GroceryCategorySummary],
        categoryOrder: [ListCategoryOrderEntry]
    ) -> [GroceryItemSection] {
        let categoryLookup = Dictionary(uniqueKeysWithValues: categories.map { ($0.id, $0) })
        let explicitOrder = Dictionary(uniqueKeysWithValues: categoryOrder.map { ($0.categoryID, $0.sortOrder) })

        let activeItems = items
            .filter { $0.checked == false }
            .sorted { left, right in
                compareActiveItems(
                    left,
                    right,
                    categoryLookup: categoryLookup,
                    explicitOrder: explicitOrder
                )
            }
        let checkedItems = items
            .filter(\.checked)
            .sorted(by: compareCheckedItems)

        var sections: [GroceryItemSection] = []

        let groupedActiveItems = Dictionary(grouping: activeItems) { item in
            item.categoryID.map(GroceryItemSectionKind.category) ?? .uncategorized
        }

        if let uncategorizedItems = groupedActiveItems[GroceryItemSectionKind.uncategorized], uncategorizedItems.isEmpty == false {
            sections.append(
                GroceryItemSection(
                    kind: .uncategorized,
                    title: "Uncategorized",
                    itemCount: uncategorizedItems.count,
                    colorHex: nil,
                    items: uncategorizedItems
                )
            )
        }

        let orderedCategoryIDs = categoryOrder
            .sorted { $0.sortOrder < $1.sortOrder }
            .map(\.categoryID)

        for categoryID in orderedCategoryIDs {
            guard
                let category = categoryLookup[categoryID],
                let sectionItems = groupedActiveItems[GroceryItemSectionKind.category(categoryID)],
                sectionItems.isEmpty == false
            else {
                continue
            }

            sections.append(
                GroceryItemSection(
                    kind: .category(categoryID),
                    title: category.name,
                    itemCount: sectionItems.count,
                    colorHex: category.colorHex,
                    items: sectionItems
                )
            )
        }

        let unorderedCategories = groupedActiveItems.keys.compactMap { key -> UUID? in
            guard case let .category(categoryID) = key, explicitOrder[categoryID] == nil else {
                return nil
            }
            return categoryID
        }
        .sorted {
            (categoryLookup[$0]?.name ?? "").localizedCaseInsensitiveCompare(categoryLookup[$1]?.name ?? "") == .orderedAscending
        }

        for categoryID in unorderedCategories {
            guard
                let category = categoryLookup[categoryID],
                let sectionItems = groupedActiveItems[GroceryItemSectionKind.category(categoryID)],
                sectionItems.isEmpty == false
            else {
                continue
            }

            sections.append(
                GroceryItemSection(
                    kind: .category(categoryID),
                    title: category.name,
                    itemCount: sectionItems.count,
                    colorHex: category.colorHex,
                    items: sectionItems
                )
            )
        }

        if checkedItems.isEmpty == false {
            sections.append(
                GroceryItemSection(
                    kind: .checked,
                    title: "Checked off",
                    itemCount: checkedItems.count,
                    colorHex: "#94a3b8",
                    items: checkedItems
                )
            )
        }

        return sections
    }

    private static func compareActiveItems(
        _ left: GroceryItemRecord,
        _ right: GroceryItemRecord,
        categoryLookup: [UUID: GroceryCategorySummary],
        explicitOrder: [UUID: Int]
    ) -> Bool {
        let leftIsUncategorized = left.categoryID == nil
        let rightIsUncategorized = right.categoryID == nil
        if leftIsUncategorized != rightIsUncategorized {
            return leftIsUncategorized
        }

        if let leftCategoryID = left.categoryID, let rightCategoryID = right.categoryID {
            let leftSortOrder = explicitOrder[leftCategoryID] ?? Int.max
            let rightSortOrder = explicitOrder[rightCategoryID] ?? Int.max

            let leftIsExplicit = explicitOrder[leftCategoryID] != nil
            let rightIsExplicit = explicitOrder[rightCategoryID] != nil
            if leftIsExplicit != rightIsExplicit {
                return leftIsExplicit
            }

            if leftSortOrder != rightSortOrder {
                return leftSortOrder < rightSortOrder
            }

            let leftCategoryName = categoryLookup[leftCategoryID]?.name ?? ""
            let rightCategoryName = categoryLookup[rightCategoryID]?.name ?? ""
            let categoryNameOrdering = leftCategoryName.localizedCaseInsensitiveCompare(rightCategoryName)
            if categoryNameOrdering != .orderedSame {
                return categoryNameOrdering == .orderedAscending
            }
        }

        if left.sortOrder != right.sortOrder {
            return left.sortOrder < right.sortOrder
        }
        return left.name.localizedCaseInsensitiveCompare(right.name) == .orderedAscending
    }

    private static func compareCheckedItems(_ left: GroceryItemRecord, _ right: GroceryItemRecord) -> Bool {
        let leftCheckedAt = left.checkedAt ?? .distantPast
        let rightCheckedAt = right.checkedAt ?? .distantPast
        if leftCheckedAt != rightCheckedAt {
            return leftCheckedAt > rightCheckedAt
        }
        return left.name.localizedCaseInsensitiveCompare(right.name) == .orderedAscending
    }
}
