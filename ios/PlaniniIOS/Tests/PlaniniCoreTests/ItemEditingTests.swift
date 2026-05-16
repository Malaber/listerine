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
}
