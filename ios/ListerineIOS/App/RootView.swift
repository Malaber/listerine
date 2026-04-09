import ListerineCore
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

private enum AppTab: Hashable {
    case favorite
    case lists
    case settings
}

struct RootView: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    @State private var selectedTab: AppTab = .favorite

    var body: some View {
        Group {
            if viewModel.authToken == nil {
                NavigationStack {
                    loginPane
                        .navigationTitle("Listerine")
                }
            } else {
                appTabs
            }
        }
        .alert(
            "Error",
            isPresented: Binding(
                get: { viewModel.errorMessage != nil },
                set: { if !$0 { viewModel.errorMessage = nil } }
            )
        ) {
            Button("OK", role: .cancel) { viewModel.errorMessage = nil }
        } message: {
            Text(viewModel.errorMessage ?? "Unknown error")
        }
        .task(id: selectedTab) {
            guard selectedTab == .favorite else { return }
            await viewModel.showFavoriteList()
        }
        .task {
            await viewModel.bootstrapLaunchSessionIfNeeded()
        }
    }

    private var loginPane: some View {
        Form {
            Section("Backend") {
                LabeledContent("Configured host", value: viewModel.backendDisplayName)
            }

            Section("Sign in") {
                Button {
                    Task { await viewModel.loginWithPasskey() }
                } label: {
                    if viewModel.isAuthenticating {
                        Label("Signing in…", systemImage: "hourglass")
                    } else {
                        Label("Continue with Passkey", systemImage: "person.badge.key")
                    }
                }
                .disabled(viewModel.isAuthenticating)
                .accessibilityIdentifier("login-passkey-button")
            }
        }
    }

    private var appTabs: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                FavoriteListTab()
            }
            .tabItem {
                Label("Favorite", systemImage: viewModel.favoriteListID == nil ? "star" : "star.fill")
            }
            .tag(AppTab.favorite)
            .accessibilityIdentifier("tab-favorite")

            NavigationStack {
                ListsTab(selectedTab: $selectedTab)
            }
            .tabItem {
                Label("Lists", systemImage: "rectangle.grid.1x2")
            }
            .tag(AppTab.lists)
            .accessibilityIdentifier("tab-lists")

            NavigationStack {
                SettingsTab()
            }
            .tabItem {
                Label("Settings", systemImage: "gearshape")
            }
            .tag(AppTab.settings)
            .accessibilityIdentifier("tab-settings")
        }
        .accessibilityIdentifier("main-tab-view")
    }
}

private struct FavoriteListTab: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel

    var body: some View {
        Group {
            if let favoriteList = viewModel.favoriteList {
                ListDetailScreen(listID: favoriteList.id, showsFavoriteButton: false)
            } else {
                EmptyStateView(
                    title: "No favorite list yet",
                    systemImage: "star",
                    message: "Pick a list in the Lists tab to keep it one tap away."
                )
                .navigationTitle("Favorite")
            }
        }
    }
}

private struct ListsTab: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    @Binding var selectedTab: AppTab

    private var householdSections: [(name: String, lists: [GroceryListSummary])] {
        Dictionary(grouping: viewModel.lists, by: \.householdName)
            .map { key, value in
                (name: key, lists: value.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending })
            }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
    }

    var body: some View {
        List {
            ForEach(householdSections, id: \.name) { section in
                Section(section.name) {
                    ForEach(section.lists) { list in
                        NavigationLink {
                            ListDetailScreen(listID: list.id, showsFavoriteButton: true)
                        } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(list.name)
                                    if list.id == viewModel.favoriteListID {
                                        Label("Favorite list", systemImage: "star.fill")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }

                                Spacer()

                                if list.id == viewModel.selectedListID {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.tint)
                                }
                            }
                        }
                        .accessibilityIdentifier("list-row-\(list.name)")
                        .simultaneousGesture(TapGesture().onEnded {
                            Task { await viewModel.selectList(id: list.id) }
                        })
                        .swipeActions(edge: .leading, allowsFullSwipe: false) {
                            Button {
                                viewModel.setFavoriteList(id: list.id)
                                selectedTab = .favorite
                                Task { await viewModel.showFavoriteList() }
                            } label: {
                                Label("Favorite", systemImage: "star.fill")
                            }
                            .tint(.yellow)
                        }
                    }
                }
            }
        }
        .navigationTitle("Lists")
    }
}

private struct SettingsTab: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel

    var body: some View {
        Form {
            Section("Account") {
                LabeledContent("Signed in as", value: viewModel.displayName ?? "Unknown")
                if let favoriteList = viewModel.favoriteList {
                    LabeledContent("Favorite list", value: favoriteList.name)
                }
                Button("Sign out", role: .destructive) {
                    viewModel.signOut()
                }
                .accessibilityIdentifier("settings-sign-out-button")
            }

            Section("App") {
                LabeledContent("Backend", value: viewModel.backendDisplayName)
                LabeledContent("Available lists", value: "\(viewModel.lists.count)")
                LabeledContent("Visible categories", value: "\(viewModel.categories.count)")
            }
        }
        .navigationTitle("Settings")
        .accessibilityIdentifier("settings-screen")
    }
}

private struct ListDetailScreen: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    let listID: UUID
    let showsFavoriteButton: Bool

    @State private var editingItem: GroceryItemRecord?
    @State private var showingAddSheet = false

    private var currentList: GroceryListSummary? {
        viewModel.lists.first { $0.id == listID }
    }

    var body: some View {
        List {
            if let list = currentList {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(list.householdName)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Text(list.name)
                            .font(.title2.weight(.semibold))
                            .accessibilityIdentifier("list-detail-title")
                        Text("\(viewModel.sections.reduce(0) { $0 + $1.itemCount }) items across \(viewModel.sections.count) sections")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }

            if viewModel.sections.isEmpty {
                Section {
                    EmptyStateView(
                        title: "Nothing on this list",
                        systemImage: "basket",
                        message: "Add an item to start grouping it into categories."
                    )
                }
            } else {
                ForEach(viewModel.sections) { section in
                    Section {
                        ForEach(section.items) { item in
                            ItemRow(item: item) {
                                editingItem = item
                            }
                        }
                    } header: {
                        SectionHeader(section: section)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(currentList?.name ?? "List")
        .navigationBarTitleDisplayMode(.large)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showingAddSheet = true
                } label: {
                    Label("Add item", systemImage: "plus")
                }
                .accessibilityIdentifier("add-item-button")
            }

            if showsFavoriteButton, let currentList, currentList.id != viewModel.favoriteListID {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        viewModel.setFavoriteList(id: currentList.id)
                    } label: {
                        Label("Favorite", systemImage: "star")
                    }
                    .accessibilityIdentifier("favorite-list-button")
                }
            }
        }
        .task(id: listID) {
            await viewModel.selectList(id: listID)
        }
        .sheet(item: $editingItem) { item in
            EditItemSheet(item: item)
        }
        .sheet(isPresented: $showingAddSheet) {
            AddItemSheet()
        }
        .animation(.easeInOut(duration: 0.22), value: viewModel.sections.map(\.id))
        .accessibilityIdentifier("list-detail-screen")
    }
}

private struct SectionHeader: View {
    let section: GroceryItemSection

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(Color(hex: section.colorHex) ?? Color.secondary.opacity(0.4))
                .frame(width: 10, height: 10)
            Text(section.title)
            Spacer()
            Text("\(section.itemCount)")
                .foregroundStyle(.secondary)
        }
        .textCase(nil)
        .accessibilityIdentifier("section-\(section.id)")
    }
}

private struct ItemRow: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    let item: GroceryItemRecord
    let onEdit: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button {
                Task {
                    let toggled = await viewModel.toggle(item)
                    if toggled {
                        AppHaptics.itemToggle()
                    }
                }
            } label: {
                Image(systemName: item.checked ? "checkmark.circle.fill" : "circle")
                    .font(.title3)
                    .foregroundStyle(item.checked ? .green : .secondary)
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("toggle-item-\(item.id.uuidString)")
            .accessibilityLabel(item.checked ? "Uncheck \(item.name)" : "Check \(item.name)")

            VStack(alignment: .leading, spacing: 4) {
                Text(item.name)
                    .strikethrough(item.checked)
                    .foregroundStyle(item.checked ? .secondary : .primary)

                if let quantity = item.quantityText, quantity.isEmpty == false {
                    Text("Qty: \(quantity)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let note = item.note, note.isEmpty == false {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Spacer()
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: onEdit)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("item-row-\(item.id.uuidString)")
        .swipeActions {
            Button(role: .destructive) {
                Task {
                    let deleted = await viewModel.delete(item: item)
                    if deleted {
                        AppHaptics.destructiveAction()
                    }
                }
            } label: {
                Label("Delete", systemImage: "trash")
            }

            Button {
                onEdit()
            } label: {
                Label("Edit", systemImage: "pencil")
            }
            .tint(.blue)
        }
    }
}

private struct AddItemSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var viewModel: MobileAppViewModel

    @State private var name = ""
    @State private var quantity = ""
    @State private var note = ""
    @State private var categoryID: UUID?

    var body: some View {
        NavigationStack {
            Form {
                Section("Item") {
                    TextField("Name", text: $name)
                        .accessibilityIdentifier("add-item-name-field")
                    TextField("Quantity", text: $quantity)
                        .accessibilityIdentifier("add-item-quantity-field")
                }

                Section("Category") {
                    Picker("Category", selection: $categoryID) {
                        Text("Uncategorized").tag(Optional<UUID>.none)
                        ForEach(viewModel.availableCategories) { category in
                            Text(category.name).tag(Optional(category.id))
                        }
                    }
                    .accessibilityIdentifier("add-item-category-picker")
                }

                Section("Notes") {
                    TextField("Note", text: $note, axis: .vertical)
                        .accessibilityIdentifier("add-item-note-field")
                }
            }
            .navigationTitle("Add item")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let saved = await viewModel.addItem(
                                name: name,
                                quantity: quantity,
                                note: note,
                                categoryID: categoryID
                            )
                            if saved {
                                AppHaptics.confirmation()
                                dismiss()
                            }
                        }
                    }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    .accessibilityIdentifier("add-item-save-button")
                }
            }
        }
        .accessibilityIdentifier("add-item-sheet")
    }
}

private struct EditItemSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var viewModel: MobileAppViewModel
    let item: GroceryItemRecord

    @State private var name: String
    @State private var quantity: String
    @State private var note: String
    @State private var categoryID: UUID?

    init(item: GroceryItemRecord) {
        self.item = item
        _name = State(initialValue: item.name)
        _quantity = State(initialValue: item.quantityText ?? "")
        _note = State(initialValue: item.note ?? "")
        _categoryID = State(initialValue: item.categoryID)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Item") {
                    TextField("Name", text: $name)
                        .accessibilityIdentifier("edit-item-name-field")
                    TextField("Quantity", text: $quantity)
                        .accessibilityIdentifier("edit-item-quantity-field")
                }

                Section("Category") {
                    Picker("Category", selection: $categoryID) {
                        Text("Uncategorized").tag(Optional<UUID>.none)
                        ForEach(viewModel.availableCategories) { category in
                            Text(category.name).tag(Optional(category.id))
                        }
                    }
                    .accessibilityIdentifier("edit-item-category-picker")
                }

                Section("Notes") {
                    TextField("Note", text: $note, axis: .vertical)
                        .accessibilityIdentifier("edit-item-note-field")
                }
            }
            .navigationTitle("Edit item")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task {
                            let saved = await viewModel.saveEdit(
                                item: item,
                                name: name,
                                quantity: quantity,
                                note: note,
                                categoryID: categoryID
                            )
                            if saved {
                                AppHaptics.confirmation()
                                dismiss()
                            }
                        }
                    }
                    .accessibilityIdentifier("edit-item-save-button")
                }
            }
        }
        .accessibilityIdentifier("edit-item-sheet")
    }
}

private struct EmptyStateView: View {
    let title: String
    let systemImage: String
    let message: String

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 28))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.headline)
            Text(message)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }
}

private enum AppHaptics {
    static func itemToggle() {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.prepare()
        generator.impactOccurred(intensity: 0.75)
        #endif
    }

    static func confirmation() {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: .soft)
        generator.prepare()
        generator.impactOccurred(intensity: 0.8)
        #endif
    }

    static func destructiveAction() {
        #if canImport(UIKit)
        let generator = UIImpactFeedbackGenerator(style: .rigid)
        generator.prepare()
        generator.impactOccurred(intensity: 0.7)
        #endif
    }
}

private extension Color {
    init?(hex: String?) {
        guard let hex else { return nil }
        let cleaned = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        guard cleaned.count == 6, let value = UInt64(cleaned, radix: 16) else { return nil }

        let red = Double((value & 0xFF0000) >> 16) / 255
        let green = Double((value & 0x00FF00) >> 8) / 255
        let blue = Double(value & 0x0000FF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}
