import Foundation
import Testing
@testable import PlaniniCore

struct ItemEditingTests {
    @Test func editPayloadNormalizesFieldsAndBuildsJSONBody() {
        let categoryID = UUID()
        let payload = GroceryItemEditPayload(
            name: "  Milk  ",
            quantityText: "  ",
            note: "  cold  ",
            categoryID: categoryID
        )

        #expect(payload.name == "Milk")
        #expect(payload.quantityText == nil)
        #expect(payload.note == "cold")
        #expect(payload.categoryID == categoryID)
        #expect(payload.isValid)
        #expect(payload.jsonBody["name"] as? String == "Milk")
        #expect(payload.jsonBody["quantity_text"] is NSNull)
        #expect(payload.jsonBody["note"] as? String == "cold")
        #expect(payload.jsonBody["category_id"] as? String == categoryID.uuidString)
    }

    @Test func editPayloadRejectsBlankNames() {
        let payload = GroceryItemEditPayload(
            name: "   ",
            quantityText: "2",
            note: nil,
            categoryID: nil
        )

        #expect(payload.name == "")
        #expect(payload.isValid == false)
    }

    @Test func editPayloadJSONBodyUsesNullsForMissingOptionalFields() {
        let payload = GroceryItemEditPayload(
            name: "Milk",
            quantityText: nil,
            note: nil,
            categoryID: nil
        )

        #expect(payload.jsonBody["name"] as? String == "Milk")
        #expect(payload.jsonBody["quantity_text"] is NSNull)
        #expect(payload.jsonBody["note"] is NSNull)
        #expect(payload.jsonBody["category_id"] is NSNull)
    }

    @Test func editPayloadCanApplyToExistingItemWithoutChangingStateFields() {
        let itemID = UUID()
        let listID = UUID()
        let movedListID = UUID()
        let checkedAt = Date(timeIntervalSince1970: 100)
        let item = GroceryItemRecord(
            id: itemID,
            listID: listID,
            name: "Old",
            quantityText: nil,
            note: nil,
            categoryID: nil,
            checked: true,
            checkedAt: checkedAt,
            sortOrder: 7
        )
        let categoryID = UUID()

        let edited = item.applyingEditPayload(
            GroceryItemEditPayload(
                name: "New",
                quantityText: "3",
                note: "fresh",
                categoryID: categoryID
            )
        )

        #expect(edited.id == itemID)
        #expect(edited.listID == listID)
        #expect(edited.name == "New")
        #expect(edited.quantityText == "3")
        #expect(edited.note == "fresh")
        #expect(edited.categoryID == categoryID)
        #expect(edited.checked == true)
        #expect(edited.checkedAt == checkedAt)
        #expect(edited.sortOrder == 7)

        let moved = edited.moving(to: movedListID)
        #expect(moved.id == itemID)
        #expect(moved.listID == movedListID)
        #expect(moved.name == "New")
        #expect(moved.quantityText == "3")
        #expect(moved.note == "fresh")
        #expect(moved.categoryID == categoryID)
        #expect(moved.checked == true)
        #expect(moved.checkedAt == checkedAt)
        #expect(moved.sortOrder == 7)
    }

    @Test func editPayloadInitializesFromExistingItem() {
        let categoryID = UUID()
        let item = GroceryItemRecord(
            id: UUID(),
            listID: UUID(),
            name: "Apples",
            quantityText: "4",
            note: "green",
            categoryID: categoryID,
            checked: false,
            checkedAt: nil,
            sortOrder: 0
        )

        let payload = GroceryItemEditPayload(item: item)

        #expect(payload.name == "Apples")
        #expect(payload.quantityText == "4")
        #expect(payload.note == "green")
        #expect(payload.categoryID == categoryID)
    }

    @Test func editHistorySupportsUndoRedoAndClearsRedoOnNewEdit() {
        let first = GroceryItemEditPayload(name: "Milk", quantityText: nil, note: nil, categoryID: nil)
        let second = GroceryItemEditPayload(name: "Oat milk", quantityText: nil, note: nil, categoryID: nil)
        let third = GroceryItemEditPayload(name: "Soy milk", quantityText: nil, note: nil, categoryID: nil)
        var history = GroceryItemEditHistory(limit: 2)

        history.record(previous: first, current: second)
        #expect(history.canUndo)
        #expect(history.undo(current: second) == first)
        #expect(history.canRedo)
        #expect(history.redo(current: first) == second)

        history.record(previous: second, current: third)
        #expect(history.canRedo == false)
        #expect(history.undo(current: third) == second)
    }

    @Test func editHistoryHandlesNoopsEmptyStacksAndLimits() {
        let first = GroceryItemEditPayload(name: "Milk", quantityText: nil, note: nil, categoryID: nil)
        let second = GroceryItemEditPayload(name: "Oat milk", quantityText: nil, note: nil, categoryID: nil)
        let third = GroceryItemEditPayload(name: "Soy milk", quantityText: nil, note: nil, categoryID: nil)
        var history = GroceryItemEditHistory(limit: 1)

        history.record(previous: first, current: first)
        #expect(history.canUndo == false)
        #expect(history.undo(current: first) == nil)
        #expect(history.redo(current: first) == nil)

        history.record(previous: first, current: second)
        history.record(previous: second, current: third)
        #expect(history.undo(current: third) == second)
        history.record(previous: second, current: third)
        history.record(previous: third, current: first)
        #expect(history.redo(current: third) == nil)
    }

    @Test func editHistoryInitializesWithLimitedStacks() {
        let first = GroceryItemEditPayload(name: "Milk", quantityText: nil, note: nil, categoryID: nil)
        let second = GroceryItemEditPayload(name: "Oat milk", quantityText: nil, note: nil, categoryID: nil)
        let third = GroceryItemEditPayload(name: "Soy milk", quantityText: nil, note: nil, categoryID: nil)

        let history = GroceryItemEditHistory(
            undoStack: [first, second],
            redoStack: [second, third],
            limit: 1
        )

        #expect(history.undoStack == [second])
        #expect(history.redoStack == [third])
    }

    @Test func editHistoryLimitsStacksDuringUndoAndRedo() {
        let first = GroceryItemEditPayload(name: "Milk", quantityText: nil, note: nil, categoryID: nil)
        let second = GroceryItemEditPayload(name: "Oat milk", quantityText: nil, note: nil, categoryID: nil)
        let third = GroceryItemEditPayload(name: "Soy milk", quantityText: nil, note: nil, categoryID: nil)
        var undoHistory = GroceryItemEditHistory(
            undoStack: [first],
            redoStack: [second],
            limit: 1
        )
        var redoHistory = GroceryItemEditHistory(
            undoStack: [first],
            redoStack: [second],
            limit: 1
        )

        #expect(undoHistory.undo(current: third) == first)
        #expect(undoHistory.redoStack == [third])
        #expect(redoHistory.redo(current: third) == second)
        #expect(redoHistory.undoStack == [third])
    }

    @Test func categorySelectionUsesListOrderAndSearch() {
        let pantry = GroceryCategorySummary(id: UUID(), name: "Konserven", colorHex: "#94a3b8")
        let dairy = GroceryCategorySummary(
            id: UUID(),
            name: "Milch & Eier",
            colorHex: "#d8b4e2",
            aliases: ["Molkerei"]
        )
        let produce = GroceryCategorySummary(id: UUID(), name: "Gemuese", colorHex: "#7ed957")
        let bakery = GroceryCategorySummary(id: UUID(), name: "Backwaren", colorHex: "#fb923c")
        let items = [
            makeItem(name: "Beans", categoryID: pantry.id),
            makeItem(name: "Milk", categoryID: dairy.id),
            makeItem(name: "Loose", categoryID: nil),
        ]

        let options = GroceryCategorySelectionBuilder.options(
            categories: [produce, dairy, bakery, pantry],
            items: items,
            categoryOrder: [
                ListCategoryOrderEntry(categoryID: dairy.id, sortOrder: 1),
                ListCategoryOrderEntry(categoryID: pantry.id, sortOrder: 0),
            ],
            query: "",
            sort: .listOrder
        )
        let filteredOptions = GroceryCategorySelectionBuilder.options(
            categories: [produce, dairy, pantry],
            items: items,
            categoryOrder: [],
            query: "mil",
            sort: .nameAscending
        )

        #expect(options.map(\.category.name) == ["Konserven", "Milch & Eier", "Backwaren", "Gemuese"])
        #expect(options.map(\.itemCount) == [1, 1, 0, 0])
        #expect(filteredOptions.map(\.category.name) == ["Milch & Eier"])
        #expect(GroceryCategorySelectionBuilder.uncategorizedItemCount(items: items) == 1)
    }

    @Test func categorySelectionSearchesAliasesAndToleratesTypos() {
        let dairy = GroceryCategorySummary(
            id: UUID(),
            name: "Milch & Eier",
            colorHex: "#d8b4e2",
            aliases: ["Molkerei"]
        )
        let pantry = GroceryCategorySummary(
            id: UUID(),
            name: "Konserven",
            colorHex: "#94a3b8",
            aliases: ["Dose"]
        )

        let aliasOptions = GroceryCategorySelectionBuilder.options(
            categories: [pantry, dairy],
            items: [],
            categoryOrder: [],
            query: "molkrei",
            sort: .nameAscending
        )
        let typoOptions = GroceryCategorySelectionBuilder.options(
            categories: [pantry, dairy],
            items: [],
            categoryOrder: [],
            query: "konserveb",
            sort: .nameAscending
        )

        #expect(aliasOptions.map(\.category.name) == ["Milch & Eier"])
        #expect(typoOptions.map(\.category.name) == ["Konserven"])
    }

    @Test func categorySelectionSortsByNameAndMostUsed() {
        let bakery = GroceryCategorySummary(id: UUID(), name: "Backwaren", colorHex: "#fb923c")
        let pantry = GroceryCategorySummary(id: UUID(), name: "Konserven", colorHex: "#94a3b8")
        let dairy = GroceryCategorySummary(id: UUID(), name: "Milch & Eier", colorHex: "#d8b4e2")
        let lowercaseDairy = GroceryCategorySummary(id: UUID(), name: "milch & eier", colorHex: "#d8b4e2")
        let items = [
            makeItem(name: "Bread", categoryID: bakery.id),
            makeItem(name: "Beans", categoryID: pantry.id),
            makeItem(name: "Tomatoes", categoryID: pantry.id, checked: true),
            makeItem(name: "Milk", categoryID: dairy.id),
            makeItem(name: "Eggs", categoryID: dairy.id),
        ]

        let ascending = GroceryCategorySelectionBuilder.options(
            categories: [pantry, dairy, bakery],
            items: items,
            categoryOrder: [],
            query: "",
            sort: .nameAscending
        )
        let descending = GroceryCategorySelectionBuilder.options(
            categories: [pantry, dairy, bakery],
            items: items,
            categoryOrder: [],
            query: "",
            sort: .nameDescending
        )
        let mostUsed = GroceryCategorySelectionBuilder.options(
            categories: [bakery, dairy, pantry],
            items: items,
            categoryOrder: [],
            query: "",
            sort: .mostUsed
        )
        let equalNames = GroceryCategorySelectionBuilder.options(
            categories: [lowercaseDairy, dairy],
            items: items,
            categoryOrder: [],
            query: "",
            sort: .nameAscending
        )

        #expect(ascending.map(\.category.name) == ["Backwaren", "Konserven", "Milch & Eier"])
        #expect(descending.map(\.category.name) == ["Milch & Eier", "Konserven", "Backwaren"])
        #expect(mostUsed.map(\.category.name) == ["Konserven", "Milch & Eier", "Backwaren"])
        #expect(mostUsed.map(\.itemCount) == [2, 2, 1])
        #expect(Set(equalNames.map(\.id)) == Set([lowercaseDairy.id, dairy.id]))
    }

    private func makeItem(name: String, categoryID: UUID?, checked: Bool = false) -> GroceryItemRecord {
        GroceryItemRecord(
            id: UUID(),
            listID: UUID(),
            name: name,
            quantityText: nil,
            note: nil,
            categoryID: categoryID,
            checked: checked,
            checkedAt: checked ? Date(timeIntervalSince1970: 10) : nil,
            sortOrder: 0
        )
    }
}
