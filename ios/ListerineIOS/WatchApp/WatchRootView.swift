import ListerineCore
import SwiftUI

struct WatchRootView: View {
    @StateObject private var viewModel = WatchAppViewModel()

    var body: some View {
        NavigationStack {
            List {
                if viewModel.needsPhoneSetup {
                    setupSection
                } else {
                    quickAddSection
                    addItemSection
                    itemsSection
                }
            }
            .navigationTitle(viewModel.favoriteListName)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await viewModel.refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(viewModel.isWorking)
                }
            }
        }
        .task {
            viewModel.onAppear()
            await viewModel.refresh()
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
    }

    private var setupSection: some View {
        Section {
            Text("Open the iPhone app, sign in, and choose a favorite list to sync your watch.")
                .font(.footnote)
                .foregroundStyle(.secondary)
        } header: {
            Text("Watch setup")
        }
    }

    private var quickAddSection: some View {
        Section {
            Button {
                Task { await viewModel.quickAdd() }
            } label: {
                Label("Add \(viewModel.quickAddLabel)", systemImage: "plus.circle.fill")
            }
            .disabled(viewModel.isWorking)
        }
    }

    private var addItemSection: some View {
        Section("Add something else") {
            TextField("Item name", text: $viewModel.draftItemName)
                .textInputAutocapitalization(.words)
                .submitLabel(.done)
                .onSubmit {
                    Task { await viewModel.addDraftItem() }
                }

            Button("Add item") {
                Task { await viewModel.addDraftItem() }
            }
            .disabled(viewModel.draftItemName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isWorking)
        }
    }

    private var itemsSection: some View {
        Section("Items") {
            if viewModel.state.items.isEmpty {
                Text("Nothing on this list right now.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.state.items) { item in
                    Button {
                        Task { await viewModel.toggle(item) }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: item.checked ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(item.checked ? .green : .secondary)
                            Text(item.name)
                                .strikethrough(item.checked)
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.isWorking)
                }
            }
        }
    }
}
