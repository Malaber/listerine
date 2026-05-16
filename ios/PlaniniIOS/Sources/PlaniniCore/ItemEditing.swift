import Foundation

public struct GroceryItemEditPayload: Codable, Equatable, Sendable {
    public var name: String
    public var quantityText: String?
    public var note: String?
    public var categoryID: UUID?

    public init(name: String, quantityText: String?, note: String?, categoryID: UUID?) {
        self.name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        self.quantityText = Self.normalizedOptionalText(quantityText)
        self.note = Self.normalizedOptionalText(note)
        self.categoryID = categoryID
    }

    public init(item: GroceryItemRecord) {
        self.init(
            name: item.name,
            quantityText: item.quantityText,
            note: item.note,
            categoryID: item.categoryID
        )
    }

    public var isValid: Bool {
        name.isEmpty == false
    }

    public var jsonBody: [String: Any] {
        [
            "name": name,
            "quantity_text": quantityText ?? NSNull(),
            "note": note ?? NSNull(),
            "category_id": categoryID?.uuidString ?? NSNull(),
        ]
    }

    private static func normalizedOptionalText(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }
}

public struct GroceryItemEditHistory: Codable, Equatable, Sendable {
    public private(set) var undoStack: [GroceryItemEditPayload]
    public private(set) var redoStack: [GroceryItemEditPayload]
    public let limit: Int

    public init(
        undoStack: [GroceryItemEditPayload] = [],
        redoStack: [GroceryItemEditPayload] = [],
        limit: Int = 25
    ) {
        self.undoStack = Array(undoStack.suffix(limit))
        self.redoStack = Array(redoStack.suffix(limit))
        self.limit = limit
    }

    public var canUndo: Bool {
        undoStack.isEmpty == false
    }

    public var canRedo: Bool {
        redoStack.isEmpty == false
    }

    public mutating func record(previous payload: GroceryItemEditPayload, current: GroceryItemEditPayload) {
        guard payload != current else { return }
        undoStack.append(payload)
        if undoStack.count > limit {
            undoStack.removeFirst(undoStack.count - limit)
        }
        redoStack.removeAll()
    }

    public mutating func undo(current: GroceryItemEditPayload) -> GroceryItemEditPayload? {
        guard let payload = undoStack.popLast() else { return nil }
        redoStack.append(current)
        if redoStack.count > limit {
            redoStack.removeFirst(redoStack.count - limit)
        }
        return payload
    }

    public mutating func redo(current: GroceryItemEditPayload) -> GroceryItemEditPayload? {
        guard let payload = redoStack.popLast() else { return nil }
        undoStack.append(current)
        if undoStack.count > limit {
            undoStack.removeFirst(undoStack.count - limit)
        }
        return payload
    }
}

public struct GroceryItemSuggestion: Identifiable, Equatable, Sendable {
    public let item: GroceryItemRecord
    public let categoryName: String?
    public let categoryColorHex: String?

    public init(item: GroceryItemRecord, categoryName: String?, categoryColorHex: String?) {
        self.item = item
        self.categoryName = categoryName
        self.categoryColorHex = categoryColorHex
    }

    public var id: UUID {
        item.id
    }
}

public enum GroceryItemSuggestionBuilder {
    public static func build(
        query: String,
        items: [GroceryItemRecord],
        categories: [GroceryCategorySummary],
        limit: Int = 3
    ) -> [GroceryItemSuggestion] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedQuery.count >= 2 else { return [] }

        let categoryLookup = Dictionary(uniqueKeysWithValues: categories.map { ($0.id, $0) })
        return items
            .compactMap { item -> (GroceryItemRecord, Int)? in
                let candidate = item.name.localizedLowercase
                let needle = normalizedQuery.localizedLowercase
                if candidate == needle { return (item, 0) }
                if candidate.hasPrefix(needle) { return (item, 1) }
                if candidate.contains(needle) { return (item, 2) }
                return nil
            }
            .sorted { left, right in
                if left.1 != right.1 { return left.1 < right.1 }
                if left.0.checked != right.0.checked { return left.0.checked == false }
                return left.0.name.localizedCaseInsensitiveCompare(right.0.name) == .orderedAscending
            }
            .prefix(limit)
            .map { item, _ in
                GroceryItemSuggestion(
                    item: item,
                    categoryName: item.categoryID.flatMap { categoryLookup[$0]?.name },
                    categoryColorHex: item.categoryID.flatMap { categoryLookup[$0]?.colorHex }
                )
            }
    }
}

public extension GroceryItemRecord {
    func applyingEditPayload(_ payload: GroceryItemEditPayload) -> GroceryItemRecord {
        GroceryItemRecord(
            id: id,
            listID: listID,
            name: payload.name,
            quantityText: payload.quantityText,
            note: payload.note,
            categoryID: payload.categoryID,
            checked: checked,
            checkedAt: checkedAt,
            sortOrder: sortOrder
        )
    }
}
