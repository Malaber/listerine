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
                    listsSection
                }
            }
            .navigationTitle("Lists")
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
            Text("The watch needs the iPhone app to be open, unlocked, and signed in before it can sync.")
                .font(.footnote)
                .foregroundStyle(.secondary)

            LabeledContent("iPhone app installed", value: viewModel.isCompanionAppInstalled ? "Yes" : "No")
            LabeledContent("iPhone reachable", value: viewModel.isPhoneReachable ? "Yes" : "No")

            Button(viewModel.setupButtonTitle) {
                Task { await viewModel.refresh() }
            }
            .disabled(viewModel.isWorking)
        } header: {
            Text("Watch setup")
        }
    }

    private var listsSection: some View {
        Section {
            ForEach(viewModel.displayedLists) { list in
                NavigationLink {
                    WatchListDetailView(list: list)
                        .environmentObject(viewModel)
                } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(list.name)
                            if viewModel.isFavorite(list) {
                                Image(systemName: "star.fill")
                                    .foregroundStyle(.yellow)
                            }
                        }
                        Text(list.householdName)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }
}

private struct WatchListDetailView: View {
    @EnvironmentObject private var viewModel: WatchAppViewModel
    let list: GroceryListSummary

    var body: some View {
        List {
            addItemSection
            itemsSection
        }
        .navigationTitle(list.name)
        .task(id: list.id) {
            await viewModel.showList(list)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await viewModel.showList(list) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(viewModel.isWorking)
            }
        }
    }

    private var addItemSection: some View {
        Section {
            TextField("What?", text: $viewModel.draftItemName)
                .textInputAutocapitalization(.words)
                .submitLabel(.done)
                .onSubmit {
                    Task { await viewModel.addDraftItem(to: list) }
                }

            Button("Add") {
                Task { await viewModel.addDraftItem(to: list) }
            }
            .disabled(
                viewModel.draftItemName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || viewModel.isWorking
            )
        } header: {
            Text("Add item")
        }
    }

    private var itemsSection: some View {
        Section("Items") {
            if viewModel.items(for: list).isEmpty {
                Text("Nothing on this list right now.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.items(for: list)) { item in
                    Button {
                        Task { await viewModel.toggle(item, in: list) }
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
