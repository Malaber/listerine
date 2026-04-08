import SwiftUI
import ListerineCore

struct RootView: View {
    @EnvironmentObject private var viewModel: MobileAppViewModel
    @State private var editingItem: AppGroceryItem?

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.authToken == nil {
                    loginPane
                } else {
                    listPane
                }
            }
            .navigationTitle("Listerine")
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
            .sheet(item: $editingItem) { item in
                EditItemSheet(item: item) { name, quantity, note in
                    Task { await viewModel.saveEdit(item: item, name: name, quantity: quantity, note: note) }
                    editingItem = nil
                }
            }
        }
    }

    private var loginPane: some View {
        Form {
            Section("Backend") {
                TextField("https://listerine.malaber.de", text: $viewModel.backendURLInput)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Save") { viewModel.saveBackendURL() }
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
            }
        }
    }

    private var listPane: some View {
        VStack(spacing: 12) {
            Picker("List", selection: $viewModel.selectedListID) {
                ForEach(viewModel.lists) { list in
                    Text(list.name).tag(Optional(list.id))
                }
            }
            .pickerStyle(.menu)
            .padding()
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .onChange(of: viewModel.selectedListID) { _ in
                Task { try? await viewModel.reloadItems() }
            }

            HStack {
                TextField("Add item", text: $viewModel.newItemName)
                Button("Add") { Task { await viewModel.addItem() } }
            }
            .padding()
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

            List {
                ForEach(viewModel.items) { item in
                    HStack(spacing: 10) {
                        Button {
                            Task { await viewModel.toggle(item) }
                        } label: {
                            Image(systemName: item.checked ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(item.checked ? .green : .secondary)
                        }
                        .buttonStyle(.plain)

                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.name).strikethrough(item.checked)
                            if let quantity = item.quantityText, quantity.isEmpty == false {
                                Text(quantity).font(.caption).foregroundStyle(.secondary)
                            }
                            if let note = item.note, note.isEmpty == false {
                                Text(note).font(.caption2).foregroundStyle(.secondary)
                            }
                        }

                        Spacer()

                        Button { editingItem = item } label: { Image(systemName: "pencil") }
                            .buttonStyle(.plain)
                        Button(role: .destructive) {
                            Task { await viewModel.delete(item: item) }
                        } label: { Image(systemName: "trash") }
                        .buttonStyle(.plain)
                    }
                    .listRowBackground(Color.clear)
                }
            }
            .scrollContentBackground(.hidden)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .padding()
        .background(
            LinearGradient(colors: [Color.cyan.opacity(0.2), Color.blue.opacity(0.35)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()
        )
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                if let name = viewModel.displayName {
                    Text(name).font(.caption)
                }
            }
        }
    }
}

private struct EditItemSheet: View {
    let item: AppGroceryItem
    let onSave: (String, String, String) -> Void

    @State private var name: String
    @State private var quantity: String
    @State private var note: String

    init(item: AppGroceryItem, onSave: @escaping (String, String, String) -> Void) {
        self.item = item
        self.onSave = onSave
        _name = State(initialValue: item.name)
        _quantity = State(initialValue: item.quantityText ?? "")
        _note = State(initialValue: item.note ?? "")
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Name", text: $name)
                TextField("Quantity", text: $quantity)
                TextField("Note", text: $note)
            }
            .navigationTitle("Edit item")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { onSave(name, quantity, note) }
                }
            }
        }
    }
}
