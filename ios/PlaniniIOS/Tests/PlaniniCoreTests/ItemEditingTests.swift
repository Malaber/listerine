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

    @Test func itemSuggestionsMatchExistingItemsWithoutLeadingDecorationData() {
        let categoryID = UUID()
        let listID = UUID()
        let category = GroceryCategorySummary(id: categoryID, name: "Bakery", colorHex: "#f2a65a")
        let checkedBrot = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Brot",
            quantityText: nil,
            note: "Seeded checked duplicate",
            categoryID: categoryID,
            checked: true,
            checkedAt: Date(timeIntervalSince1970: 200),
            sortOrder: 1
        )
        let activeBread = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Bread rolls",
            quantityText: "6",
            note: nil,
            categoryID: nil,
            checked: false,
            checkedAt: nil,
            sortOrder: 2
        )

        let suggestions = GroceryItemSuggestionBuilder.build(
            query: "br",
            items: [checkedBrot, activeBread],
            categories: [category]
        )

        #expect(suggestions.map { $0.item.name } == ["Bread rolls", "Brot"])
        #expect(suggestions[0].id == activeBread.id)
        #expect(suggestions[1].categoryName == "Bakery")
        #expect(suggestions[1].categoryColorHex == "#f2a65a")
    }

    @Test func itemSuggestionsIgnoreShortQueriesAndRankExactPrefixAndContainsMatches() {
        let listID = UUID()
        let exact = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Milk",
            quantityText: nil,
            note: nil,
            categoryID: nil,
            checked: false,
            checkedAt: nil,
            sortOrder: 0
        )
        let prefix = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Milk chocolate",
            quantityText: nil,
            note: nil,
            categoryID: nil,
            checked: false,
            checkedAt: nil,
            sortOrder: 1
        )
        let contains = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Oat milk",
            quantityText: nil,
            note: nil,
            categoryID: nil,
            checked: false,
            checkedAt: nil,
            sortOrder: 2
        )
        let checkedPrefix = GroceryItemRecord(
            id: UUID(),
            listID: listID,
            name: "Milk bread",
            quantityText: nil,
            note: nil,
            categoryID: nil,
            checked: true,
            checkedAt: nil,
            sortOrder: 3
        )

        #expect(GroceryItemSuggestionBuilder.build(query: "m", items: [exact], categories: []).isEmpty)

        let suggestions = GroceryItemSuggestionBuilder.build(
            query: "milk",
            items: [contains, checkedPrefix, prefix, exact],
            categories: [],
            limit: 4
        )

        #expect(suggestions.map { $0.item.name } == ["Milk", "Milk chocolate", "Milk bread", "Oat milk"])
    }
}
