import PlaniniCore
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

private struct AppErrorAlert: Identifiable {
    let id = UUID()
    let message: String
}

private enum AppTab: Hashable {
    case favorite
    case lists
    case settings
}

private struct AddItemPresentation: Identifiable {
    let id = UUID()
    let categoryID: UUID?
}

struct RootView: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    @State private var selectedTab: AppTab = .favorite
    @State private var presentedError: AppErrorAlert?
    @State private var showingReviewerOnboarding = false
    @State private var passkeyAddLinkInput = ""

    var body: some View {
        Group {
            if viewModel.authToken == nil {
                NavigationStack {
                    loginPane
                        .navigationTitle("Planini")
                        .toolbar {
                            ToolbarItem(placement: .topBarTrailing) {
                                Menu {
                                    Button {
                                        showingReviewerOnboarding = true
                                    } label: {
                                        Label("Having trouble signing in?", systemImage: "questionmark.circle")
                                    }
                                    .accessibilityIdentifier("login-help-trouble-button")
                                } label: {
                                    Image(systemName: "ellipsis.circle")
                                }
                                .accessibilityIdentifier("login-help-menu")
                            }
                        }
                }
            } else {
                appTabs
            }
        }
        .sheet(isPresented: $showingReviewerOnboarding) {
            ReviewerOnboardingSheet(initialPasskeyAddInput: passkeyAddLinkInput)
        }
        .onOpenURL { url in
            guard MobileAppViewModel.passkeyAddToken(from: url.absoluteString) != nil else { return }
            passkeyAddLinkInput = url.absoluteString
            showingReviewerOnboarding = true
        }
        .onChange(of: viewModel.errorMessage) { newValue in
            guard showingReviewerOnboarding == false else { return }
            if let newValue, newValue.isEmpty == false {
                presentedError = AppErrorAlert(message: newValue)
            }
        }
        .alert(item: $presentedError) { error in
            Alert(
                title: Text("Error"),
                message: Text(error.message),
                dismissButton: .cancel(Text("OK")) {
                    viewModel.errorMessage = nil
                }
            )
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
                Label(
                    viewModel.favoriteList?.name ?? "Favorite",
                    systemImage: viewModel.favoriteListID == nil ? "star" : "star.fill"
                )
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

private struct ReviewerOnboardingSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var viewModel: MobileAppViewModel

    private enum Action {
        case addPasskey
        case registerAccount
    }

    let initialPasskeyAddInput: String

    @State private var passkeyAddInput: String
    @State private var registrationDisplayName = ""
    @State private var registrationEmail = ""
    @State private var busyAction: Action?
    @State private var addPasskeyErrorMessage: String?
    @State private var registrationErrorMessage: String?

    init(initialPasskeyAddInput: String) {
        self.initialPasskeyAddInput = initialPasskeyAddInput
        _passkeyAddInput = State(initialValue: initialPasskeyAddInput)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Add passkey") {
                    TextField("Passkey add link or key", text: $passkeyAddInput, axis: .vertical)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("passkey-add-link-field")

                    Button {
                        closeKeyboard()
                        Task {
                            busyAction = .addPasskey
                            addPasskeyErrorMessage = nil
                            registrationErrorMessage = nil
                            viewModel.errorMessage = nil
                            let added = await viewModel.addPasskeyFromLinkInput(passkeyAddInput)
                            busyAction = nil
                            if added {
                                AppHaptics.confirmation()
                                dismiss()
                            } else {
                                addPasskeyErrorMessage = viewModel.errorMessage ?? "Could not add that passkey."
                            }
                        }
                    } label: {
                        if busyAction == .addPasskey {
                            HStack {
                                ProgressView()
                                Text("Adding passkey…")
                            }
                        } else {
                            Label("Add passkey", systemImage: "person.badge.key")
                        }
                    }
                    .disabled(busyAction != nil || trimmedPasskeyAddInput.isEmpty)
                    .accessibilityIdentifier("passkey-add-submit-button")

                    if let addPasskeyErrorMessage, addPasskeyErrorMessage.isEmpty == false {
                        Label(addPasskeyErrorMessage, systemImage: "exclamationmark.triangle")
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .accessibilityIdentifier("passkey-add-error")
                    }
                }

                Section("Create account") {
                    TextField("Name", text: $registrationDisplayName)
                        .textContentType(.name)
                        .accessibilityIdentifier("registration-display-name-field")

                    TextField("Email", text: $registrationEmail)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .textContentType(.emailAddress)
                        .accessibilityIdentifier("registration-email-field")

                    Button {
                        closeKeyboard()
                        Task {
                            busyAction = .registerAccount
                            addPasskeyErrorMessage = nil
                            registrationErrorMessage = nil
                            viewModel.errorMessage = nil
                            let created = await viewModel.registerAccount(
                                displayName: registrationDisplayName,
                                email: registrationEmail
                            )
                            busyAction = nil
                            if created {
                                AppHaptics.confirmation()
                                dismiss()
                            } else {
                                registrationErrorMessage = viewModel.errorMessage ?? "Could not create that account."
                            }
                        }
                    } label: {
                        if busyAction == .registerAccount {
                            HStack {
                                ProgressView()
                                Text("Creating account…")
                            }
                        } else {
                            Label("Create account", systemImage: "person.crop.circle.badge.plus")
                        }
                    }
                    .disabled(busyAction != nil || trimmedName.isEmpty || trimmedEmail.isEmpty)
                    .accessibilityIdentifier("registration-submit-button")

                    if let registrationErrorMessage, registrationErrorMessage.isEmpty == false {
                        Label(registrationErrorMessage, systemImage: "exclamationmark.triangle")
                            .font(.footnote)
                            .foregroundStyle(.red)
                            .accessibilityIdentifier("registration-error")
                    }
                }

                if let message = viewModel.reviewerOnboardingMessage, message.isEmpty == false {
                    Section {
                        Text(message)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Sign-in help")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
        .onChange(of: initialPasskeyAddInput) { newValue in
            passkeyAddInput = newValue
        }
        .accessibilityIdentifier("reviewer-onboarding-sheet")
    }

    private var trimmedPasskeyAddInput: String {
        passkeyAddInput.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedName: String {
        registrationDisplayName.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var trimmedEmail: String {
        registrationEmail.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func closeKeyboard() {
        #if canImport(UIKit)
        UIApplication.shared.sendAction(
            #selector(UIResponder.resignFirstResponder),
            to: nil,
            from: nil,
            for: nil
        )
        #endif
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
                            }
                            .contentShape(Rectangle())
                        }
                        .accessibilityIdentifier("list-row-\(list.name)")
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
    @EnvironmentObject private var appearanceSettings: AppearanceSettings
    @EnvironmentObject private var viewModel: MobileAppViewModel

    var body: some View {
        Form {
            Section("Appearance") {
                Picker("Appearance", selection: $appearanceSettings.mode) {
                    ForEach(AppearanceMode.allCases) { mode in
                        Text(mode.settingsLabel)
                            .tag(mode)
                            .accessibilityIdentifier("settings-appearance-\(mode.rawValue)-option")
                    }
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("settings-appearance-picker")
            }

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
    @State private var addItemPresentation: AddItemPresentation?
    @State private var highlightedItemID: UUID?

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
                            .background(rowHighlight(for: item))
                        }
                    } header: {
                        SectionHeader(section: section) { categoryID in
                            addItemPresentation = AddItemPresentation(categoryID: categoryID)
                        }
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
                    addItemPresentation = AddItemPresentation(categoryID: nil)
                } label: {
                    Label("Add item", systemImage: "plus")
                }
                .accessibilityIdentifier("add-item-button")
            }

            if showsFavoriteButton, let currentList {
                ToolbarItem(placement: .topBarTrailing) {
                    let isFavorite = currentList.id == viewModel.favoriteListID
                    Button {
                        viewModel.toggleFavoriteList(id: currentList.id)
                    } label: {
                        Label(
                            isFavorite ? "Unfavorite" : "Favorite",
                            systemImage: isFavorite ? "star.fill" : "star"
                        )
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
        .sheet(item: $addItemPresentation) { presentation in
            AddItemSheet(initialCategoryID: presentation.categoryID) { itemID in
                highlightedItemID = itemID
            }
        }
        .animation(.easeInOut(duration: 0.22), value: viewModel.sections.map(\.id))
        .animation(.easeInOut(duration: 0.22), value: highlightedItemID)
        .accessibilityIdentifier("list-detail-screen")
    }

    private func rowHighlight(for item: GroceryItemRecord) -> Color {
        item.id == highlightedItemID ? Color.accentColor.opacity(0.16) : Color.clear
    }
}

private struct SectionHeader: View {
    let section: GroceryItemSection
    let onQuickAdd: (UUID?) -> Void

    private var allowsQuickAdd: Bool {
        switch section.kind {
        case .checked:
            return false
        case .uncategorized, .category:
            return true
        }
    }

    private var quickAddCategoryID: UUID? {
        switch section.kind {
        case .uncategorized, .checked:
            return nil
        case let .category(categoryID):
            return categoryID
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(Color(hex: section.colorHex) ?? Color.secondary.opacity(0.4))
                .frame(width: 10, height: 10)
            Text(section.title)
            Spacer()
            Text("\(section.itemCount)")
                .foregroundStyle(.secondary)
            if allowsQuickAdd {
                Button {
                    onQuickAdd(quickAddCategoryID)
                } label: {
                    Image(systemName: "plus")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .accessibilityIdentifier("quick-add-category-\(section.id)")
                .accessibilityLabel(section.kind == .uncategorized ? "Quick add uncategorized item" : "Quick add to \(section.title)")
            }
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
    let initialCategoryID: UUID?
    let onSuggestionFocused: (UUID) -> Void

    private enum FocusedField {
        case name
    }

    @State private var name = ""
    @State private var quantity = ""
    @State private var note = ""
    @State private var categoryID: UUID?
    @State private var isSaving = false
    @FocusState private var focusedField: FocusedField?

    init(initialCategoryID: UUID? = nil, onSuggestionFocused: @escaping (UUID) -> Void = { _ in }) {
        self.initialCategoryID = initialCategoryID
        self.onSuggestionFocused = onSuggestionFocused
        _categoryID = State(initialValue: initialCategoryID)
    }

    private var suggestions: [GroceryItemSuggestion] {
        GroceryItemSuggestionMatcher.suggestions(
            for: name,
            items: viewModel.items,
            categories: viewModel.categories
        )
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Item") {
                    TextField("Name", text: $name)
                        .focused($focusedField, equals: .name)
                        .submitLabel(.done)
                        .onSubmit(saveItem)
                        .accessibilityIdentifier("add-item-name-field")
                    TextField("Quantity", text: $quantity)
                        .accessibilityIdentifier("add-item-quantity-field")
                }

                if suggestions.isEmpty == false {
                    Section("Suggestions") {
                        ForEach(suggestions) { suggestion in
                            Button {
                                Task { await useSuggestion(suggestion) }
                            } label: {
                                ItemSuggestionRow(suggestion: suggestion)
                            }
                            .buttonStyle(.plain)
                            .contentShape(Rectangle())
                            .accessibilityIdentifier("add-item-suggestion-\(suggestion.item.id.uuidString)")
                            .accessibilityLabel(
                                suggestion.item.checked
                                    ? "Add \(suggestion.item.name) back to the list"
                                    : "Jump to \(suggestion.item.name) in the list"
                            )
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
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
            .animation(.easeInOut(duration: 0.18), value: suggestions.map(\.id))
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        saveItem()
                    }
                    .disabled(canSave == false)
                    .accessibilityIdentifier("add-item-save-button")
                }
            }
        }
        .task {
            categoryID = initialCategoryID
            try? await Task.sleep(nanoseconds: 250_000_000)
            focusedField = .name
        }
        .accessibilityIdentifier("add-item-sheet")
    }

    private var canSave: Bool {
        isSaving == false && name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
    }

    private func saveItem() {
        guard canSave else { return }
        isSaving = true
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
            } else {
                isSaving = false
            }
        }
    }

    @MainActor
    private func useSuggestion(_ suggestion: GroceryItemSuggestion) async {
        if suggestion.item.checked {
            dismiss()
            let toggled = await viewModel.toggle(suggestion.item)
            guard toggled else { return }
            AppHaptics.confirmation()
            onSuggestionFocused(suggestion.item.id)
            return
        }
        onSuggestionFocused(suggestion.item.id)
        dismiss()
    }
}

private struct ItemSuggestionRow: View {
    let suggestion: GroceryItemSuggestion

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 2)
                .fill(Color(hex: suggestion.category?.colorHex) ?? Color.secondary.opacity(0.4))
                .frame(width: 4, height: 36)
            Image(systemName: "plus")
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 3) {
                Text(suggestion.item.name)
                    .foregroundStyle(.primary)
                Text(metaText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var metaText: String {
        let categoryName = suggestion.category?.name ?? "Uncategorized"
        return suggestion.item.checked ? "\(categoryName) · checked off" : categoryName
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
    @State private var history: GroceryItemEditHistory
    @State private var lastSavedPayload: GroceryItemEditPayload
    @State private var saveTask: Task<Void, Never>?
    @State private var saveStatus: SaveStatus = .saved
    @State private var suppressHistoryRecording = false

    private enum SaveStatus: Equatable {
        case saved
        case saving
        case offline
        case invalid

        var label: String {
            switch self {
            case .saved:
                return "Saved"
            case .saving:
                return "Saving..."
            case .offline:
                return "Saved offline"
            case .invalid:
                return "Name required"
            }
        }

        var systemImage: String {
            switch self {
            case .saved:
                return "checkmark.circle"
            case .saving:
                return "arrow.triangle.2.circlepath"
            case .offline:
                return "icloud.slash"
            case .invalid:
                return "exclamationmark.triangle"
            }
        }
    }

    init(item: GroceryItemRecord) {
        self.item = item
        let payload = GroceryItemEditPayload(item: item)
        _name = State(initialValue: item.name)
        _quantity = State(initialValue: item.quantityText ?? "")
        _note = State(initialValue: item.note ?? "")
        _categoryID = State(initialValue: item.categoryID)
        _history = State(initialValue: Self.loadHistory(itemID: item.id))
        _lastSavedPayload = State(initialValue: payload)
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

                Section {
                    Label(saveStatus.label, systemImage: saveStatus.systemImage)
                        .font(.footnote)
                        .foregroundStyle(saveStatus == .invalid ? .red : .secondary)
                        .accessibilityIdentifier("edit-item-save-status")
                }
            }
            .navigationTitle("Edit item")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") {
                        flushCurrentEdit()
                        dismiss()
                    }
                }
                ToolbarItemGroup(placement: .confirmationAction) {
                    Button {
                        applyUndo()
                    } label: {
                        Label("Undo", systemImage: "arrow.uturn.backward")
                    }
                    .disabled(history.canUndo == false)
                    .accessibilityIdentifier("edit-item-undo-button")

                    Button {
                        applyRedo()
                    } label: {
                        Label("Redo", systemImage: "arrow.uturn.forward")
                    }
                    .disabled(history.canRedo == false)
                    .accessibilityIdentifier("edit-item-redo-button")
                }
            }
        }
        .onChange(of: name) { _ in scheduleAutosave() }
        .onChange(of: quantity) { _ in scheduleAutosave() }
        .onChange(of: note) { _ in scheduleAutosave() }
        .onChange(of: categoryID) { _ in scheduleAutosave() }
        .onDisappear {
            persistHistory()
            flushCurrentEdit()
        }
        .accessibilityIdentifier("edit-item-sheet")
    }

    private var currentPayload: GroceryItemEditPayload {
        GroceryItemEditPayload(
            name: name,
            quantityText: quantity,
            note: note,
            categoryID: categoryID
        )
    }

    private static func historyKey(itemID: UUID) -> String {
        "planini.itemEditHistory.\(itemID.uuidString)"
    }

    private static func loadHistory(itemID: UUID) -> GroceryItemEditHistory {
        guard
            let data = UserDefaults.standard.data(forKey: historyKey(itemID: itemID)),
            let decoded = try? JSONDecoder().decode(GroceryItemEditHistory.self, from: data)
        else {
            return GroceryItemEditHistory()
        }
        return decoded
    }

    private func persistHistory() {
        guard let data = try? JSONEncoder().encode(history) else { return }
        UserDefaults.standard.set(data, forKey: Self.historyKey(itemID: item.id))
    }

    private func scheduleAutosave() {
        scheduleAutosave(recordHistory: suppressHistoryRecording == false)
    }

    private func scheduleAutosave(recordHistory: Bool) {
        saveTask?.cancel()
        let payload = currentPayload
        guard payload.isValid else {
            saveStatus = .invalid
            return
        }
        if recordHistory {
            history.record(previous: lastSavedPayload, current: payload)
        }
        persistHistory()
        saveStatus = .saving
        saveTask = Task {
            try? await Task.sleep(nanoseconds: 450_000_000)
            guard Task.isCancelled == false else { return }
            let saved = await viewModel.saveEdit(item: item, payload: payload)
            guard Task.isCancelled == false else { return }
            await MainActor.run {
                if saved {
                    lastSavedPayload = payload
                    saveStatus = viewModel.hasPendingEdit(for: item.id) ? .offline : .saved
                } else {
                    saveStatus = .invalid
                }
            }
        }
    }

    private func apply(_ payload: GroceryItemEditPayload) {
        suppressHistoryRecording = true
        name = payload.name
        quantity = payload.quantityText ?? ""
        note = payload.note ?? ""
        categoryID = payload.categoryID
        persistHistory()
        scheduleAutosave(recordHistory: false)
        DispatchQueue.main.async {
            suppressHistoryRecording = false
        }
    }

    private func applyUndo() {
        guard let payload = history.undo(current: currentPayload) else { return }
        apply(payload)
    }

    private func applyRedo() {
        guard let payload = history.redo(current: currentPayload) else { return }
        apply(payload)
    }

    private func flushCurrentEdit() {
        saveTask?.cancel()
        let payload = currentPayload
        guard payload.isValid, payload != lastSavedPayload else { return }
        Task {
            _ = await viewModel.saveEdit(item: item, payload: payload)
        }
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
