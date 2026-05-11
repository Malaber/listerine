import Foundation
import Testing
@testable import PlaniniCore

struct ListPresentationTests {
    @Test func groceryListSummaryStoresInitializerArguments() {
        let listID = UUID()
        let householdID = UUID()

        let summary = GroceryListSummary(
            id: listID,
            householdID: householdID,
            householdName: "Home",
            name: "Weekly shop",
            archived: true
        )

        #expect(summary.id == listID)
        #expect(summary.householdID == householdID)
        #expect(summary.householdName == "Home")
        #expect(summary.name == "Weekly shop")
        #expect(summary.archived == true)
    }

    @Test func groceryCategorySummaryParsesJSON() {
        let categoryID = UUID()

        let category = GroceryCategorySummary(
            json: [
                "id": categoryID.uuidString,
                "name": "Produce",
                "color": "#00ff00",
            ]
        )

        #expect(category == GroceryCategorySummary(id: categoryID, name: "Produce", colorHex: "#00ff00"))
    }

    @Test func groceryCategorySummaryRejectsInvalidJSON() {
        #expect(GroceryCategorySummary(json: [:]) == nil)
        #expect(
            GroceryCategorySummary(
                json: [
                    "id": "not-a-uuid",
                    "name": "Produce",
                ]
            ) == nil
        )
    }

    @Test func listCategoryOrderEntryParsesJSON() {
        let categoryID = UUID()

        let entry = ListCategoryOrderEntry(
            json: [
                "category_id": categoryID.uuidString,
                "sort_order": 3,
            ]
        )

        #expect(entry == ListCategoryOrderEntry(categoryID: categoryID, sortOrder: 3))
    }

    @Test func listCategoryOrderEntryRejectsInvalidJSON() {
        #expect(ListCategoryOrderEntry(json: [:]) == nil)
        #expect(
            ListCategoryOrderEntry(
                json: [
                    "category_id": "not-a-uuid",
                    "sort_order": 3,
                ]
            ) == nil
        )
    }

    @Test func groceryItemRecordParsesJSONWithFractionalCheckedAt() {
        let itemID = UUID()
        let listID = UUID()
        let categoryID = UUID()

        let item = GroceryItemRecord(
            json: [
                "id": itemID.uuidString,
                "list_id": listID.uuidString,
                "name": "Milk",
                "quantity_text": "2",
                "note": "Semi-skimmed",
                "category_id": categoryID.uuidString,
                "checked": true,
                "checked_at": "2026-04-09T10:00:00.123Z",
                "sort_order": 7,
            ]
        )

        #expect(item?.id == itemID)
        #expect(item?.listID == listID)
        #expect(item?.name == "Milk")
        #expect(item?.quantityText == "2")
        #expect(item?.note == "Semi-skimmed")
        #expect(item?.categoryID == categoryID)
        #expect(item?.checked == true)
        #expect(item?.sortOrder == 7)
        #expect(item?.checkedAt != nil)
    }

    @Test func groceryItemRecordParsesJSONWithoutFractionalCheckedAtAndDefaults() {
        let itemID = UUID()
        let listID = UUID()

        let item = GroceryItemRecord(
            json: [
                "id": itemID.uuidString,
                "list_id": listID.uuidString,
                "name": "Bread",
                "checked_at": "2026-04-09T10:00:00Z",
            ]
        )

        #expect(item?.id == itemID)
        #expect(item?.listID == listID)
        #expect(item?.checked == false)
        #expect(item?.sortOrder == 0)
        #expect(item?.checkedAt != nil)
    }

    @Test func groceryItemRecordLeavesCheckedAtNilWhenMissing() {
        let itemID = UUID()
        let listID = UUID()

        let item = GroceryItemRecord(
            json: [
                "id": itemID.uuidString,
                "list_id": listID.uuidString,
                "name": "Pasta",
            ]
        )

        #expect(item?.checkedAt == nil)
    }

    @Test func groceryItemRecordRejectsInvalidJSONAndInvalidCategory() {
        #expect(GroceryItemRecord(json: [:]) == nil)

        let itemID = UUID()
        let listID = UUID()
        let item = GroceryItemRecord(
            json: [
                "id": itemID.uuidString,
                "list_id": listID.uuidString,
                "name": "Eggs",
                "category_id": "not-a-uuid",
                "checked_at": "not-a-date",
            ]
        )

        #expect(item?.categoryID == nil)
        #expect(item?.checkedAt == nil)
    }

    @Test func groceryItemSectionIDMatchesKind() {
        let categoryID = UUID()

        #expect(
            GroceryItemSection(
                kind: .uncategorized,
                title: "Uncategorized",
                itemCount: 0,
                colorHex: nil,
                items: []
            ).id == "uncategorized"
        )
        #expect(
            GroceryItemSection(
                kind: .category(categoryID),
                title: "Produce",
                itemCount: 0,
                colorHex: nil,
                items: []
            ).id == "category-\(categoryID.uuidString)"
        )
        #expect(
            GroceryItemSection(
                kind: .checked,
                title: "Checked off",
                itemCount: 0,
                colorHex: nil,
                items: []
            ).id == "checked"
        )
    }

    @Test func buildsSectionsInWebParityOrder() {
        let categoryOne = GroceryCategorySummary(id: UUID(), name: "Konserven", colorHex: "#94a3b8")
        let categoryTwo = GroceryCategorySummary(id: UUID(), name: "Milch & Eier", colorHex: "#d8b4e2")
        let categoryThree = GroceryCategorySummary(id: UUID(), name: "Other", colorHex: "#000000")
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Loose item",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Tomaten",
                    quantityText: nil,
                    note: nil,
                    categoryID: categoryOne.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Eier",
                    quantityText: nil,
                    note: nil,
                    categoryID: categoryTwo.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Z item",
                    quantityText: nil,
                    note: nil,
                    categoryID: categoryThree.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Bread",
                    quantityText: nil,
                    note: nil,
                    categoryID: categoryTwo.id,
                    checked: true,
                    checkedAt: Date(timeIntervalSince1970: 200),
                    sortOrder: 0
                ),
            ],
            categories: [categoryOne, categoryTwo, categoryThree],
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: categoryOne.id, sortOrder: 0),
                ListCategoryOrderEntry(categoryID: categoryTwo.id, sortOrder: 1),
            ]
        )

        #expect(
            sections.map(\.title) == ["Uncategorized", "Konserven", "Milch & Eier", "Other", "Checked off"]
        )
        #expect(sections[0].items.map(\.name) == ["Loose item"])
        #expect(sections[1].items.map(\.name) == ["Tomaten"])
        #expect(sections[2].items.map(\.name) == ["Eier"])
        #expect(sections[3].items.map(\.name) == ["Z item"])
        #expect(sections[4].items.map(\.name) == ["Bread"])
    }

    @Test func skipsOrderedCategoriesWithoutKnownMetadataOrItems() {
        let knownCategory = GroceryCategorySummary(id: UUID(), name: "Produce", colorHex: "#00ff00")
        let unknownCategoryID = UUID()
        let emptyCategory = GroceryCategorySummary(id: UUID(), name: "Bakery", colorHex: "#cccccc")
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Apples",
                    quantityText: nil,
                    note: nil,
                    categoryID: knownCategory.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
            ],
            categories: [knownCategory, emptyCategory],
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: unknownCategoryID, sortOrder: 0),
                ListCategoryOrderEntry(categoryID: emptyCategory.id, sortOrder: 1),
                ListCategoryOrderEntry(categoryID: knownCategory.id, sortOrder: 2),
            ]
        )

        #expect(sections.map(\.title) == ["Produce"])
    }

    @Test func sortsUnorderedCategoriesAlphabeticallyWhenNoExplicitOrderExists() {
        let bakery = GroceryCategorySummary(id: UUID(), name: "Bakery", colorHex: "#cccccc")
        let produce = GroceryCategorySummary(id: UUID(), name: "Produce", colorHex: "#00ff00")
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Apples",
                    quantityText: nil,
                    note: nil,
                    categoryID: produce.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Bread",
                    quantityText: nil,
                    note: nil,
                    categoryID: bakery.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
            ],
            categories: [produce, bakery],
            categoryOrder: []
        )

        #expect(sections.map(\.title) == ["Bakery", "Produce"])
    }

    @Test func skipsItemsWhoseCategoriesAreMissingFromMetadata() {
        let unknownCategoryOne = UUID()
        let unknownCategoryTwo = UUID()
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Mystery apples",
                    quantityText: nil,
                    note: nil,
                    categoryID: unknownCategoryOne,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Mystery bread",
                    quantityText: nil,
                    note: nil,
                    categoryID: unknownCategoryTwo,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
            ],
            categories: [],
            categoryOrder: []
        )

        #expect(sections.isEmpty)
    }

    @Test func sortsUncheckedItemsByCategoryPrioritySortOrderAndName() {
        let produce = GroceryCategorySummary(id: UUID(), name: "Produce", colorHex: "#00ff00")
        let dairy = GroceryCategorySummary(id: UUID(), name: "Dairy", colorHex: "#ffffff")
        let bakery = GroceryCategorySummary(id: UUID(), name: "Bakery", colorHex: "#cccccc")
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Zucchini",
                    quantityText: nil,
                    note: nil,
                    categoryID: produce.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 5
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Apples",
                    quantityText: nil,
                    note: nil,
                    categoryID: produce.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 1
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Milk",
                    quantityText: nil,
                    note: nil,
                    categoryID: dairy.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Bagel",
                    quantityText: nil,
                    note: nil,
                    categoryID: bakery.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Loose item",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 0
                ),
            ],
            categories: [produce, dairy, bakery],
            categoryOrder: [ListCategoryOrderEntry(categoryID: dairy.id, sortOrder: 0)]
        )

        #expect(sections.map(\.title) == ["Uncategorized", "Dairy", "Bakery", "Produce"])
        #expect(sections[0].items.map(\.name) == ["Loose item"])
        #expect(sections[1].items.map(\.name) == ["Milk"])
        #expect(sections[2].items.map(\.name) == ["Bagel"])
        #expect(sections[3].items.map(\.name) == ["Apples", "Zucchini"])
    }

    @Test func sortsItemsByCategoryNameThenSortOrderThenItemName() {
        let bakery = GroceryCategorySummary(id: UUID(), name: "Bakery", colorHex: "#cccccc")
        let produce = GroceryCategorySummary(id: UUID(), name: "Produce", colorHex: "#00ff00")
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Bananas",
                    quantityText: nil,
                    note: nil,
                    categoryID: produce.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 1
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Apples",
                    quantityText: nil,
                    note: nil,
                    categoryID: produce.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 1
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Sourdough",
                    quantityText: nil,
                    note: nil,
                    categoryID: bakery.id,
                    checked: false,
                    checkedAt: nil,
                    sortOrder: 5
                ),
            ],
            categories: [produce, bakery],
            categoryOrder: []
        )

        #expect(sections.map(\.title) == ["Bakery", "Produce"])
        #expect(sections[1].items.map(\.name) == ["Apples", "Bananas"])
    }

    @Test func sortsCheckedItemsByNewestFirst() {
        let listID = UUID()

        let sections = GroceryItemSectionBuilder.build(
            items: [
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Older",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: true,
                    checkedAt: Date(timeIntervalSince1970: 100),
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Alphabetical",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: true,
                    checkedAt: nil,
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Newer",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: true,
                    checkedAt: Date(timeIntervalSince1970: 200),
                    sortOrder: 0
                ),
                GroceryItemRecord(
                    id: UUID(),
                    listID: listID,
                    name: "Zulu",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: true,
                    checkedAt: nil,
                    sortOrder: 0
                ),
            ],
            categories: [],
            categoryOrder: []
        )

        let checkedSection = try! #require(sections.first)
        #expect(checkedSection.title == "Checked off")
        #expect(checkedSection.items.map(\.name) == ["Newer", "Older", "Alphabetical", "Zulu"])
    }
}
