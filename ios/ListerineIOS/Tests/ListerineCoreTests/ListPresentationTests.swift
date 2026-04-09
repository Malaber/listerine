import Foundation
import Testing
@testable import ListerineCore

struct ListPresentationTests {
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
                )
            ],
            categories: [categoryOne, categoryTwo, categoryThree],
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: categoryOne.id, sortOrder: 0),
                ListCategoryOrderEntry(categoryID: categoryTwo.id, sortOrder: 1)
            ]
        )

        #expect(sections.map(\.title) == ["Uncategorized", "Konserven", "Milch & Eier", "Other", "Checked off"])
        #expect(sections[0].items.map(\.name) == ["Loose item"])
        #expect(sections[1].items.map(\.name) == ["Tomaten"])
        #expect(sections[2].items.map(\.name) == ["Eier"])
        #expect(sections[4].items.map(\.name) == ["Bread"])
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
                    name: "Newer",
                    quantityText: nil,
                    note: nil,
                    categoryID: nil,
                    checked: true,
                    checkedAt: Date(timeIntervalSince1970: 200),
                    sortOrder: 0
                )
            ],
            categories: [],
            categoryOrder: []
        )

        let checkedSection = try! #require(sections.first)
        #expect(checkedSection.title == "Checked off")
        #expect(checkedSection.items.map(\.name) == ["Newer", "Older"])
    }
}
