import AppIntents
import PlaniniCore
import SwiftUI
import WidgetKit

struct QuickAddFavoriteItemIntent: AppIntent {
    static let title: LocalizedStringResource = "Quick Add Favorite Item"
    static let description = IntentDescription("Adds the configured quick item to your favorite Planini list.")
    static let openAppWhenRun = false

    func perform() async throws -> some IntentResult {
        let store = WatchSharedContainer.stateStore
        let currentState = store.load()
        let updatedState = try await WatchBackendClient().addItem(
            named: currentState.quickAddItemName,
            using: currentState
        )
        store.save(updatedState)
        WidgetCenter.shared.reloadAllTimelines()
        return .result(
            dialog: IntentDialog("Added \(currentState.quickAddItemName) to \(updatedState.favoriteListName ?? "your list").")
        )
    }
}

struct PlaniniWatchWidgetEntry: TimelineEntry {
    let date: Date
    let state: SharedAppState
}

struct PlaniniWatchWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> PlaniniWatchWidgetEntry {
        PlaniniWatchWidgetEntry(date: .now, state: SharedAppState(favoriteListID: UUID(), quickAddItemName: "Milk"))
    }

    func getSnapshot(in context: Context, completion: @escaping (PlaniniWatchWidgetEntry) -> Void) {
        completion(PlaniniWatchWidgetEntry(date: .now, state: WatchSharedContainer.stateStore.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<PlaniniWatchWidgetEntry>) -> Void) {
        let entry = PlaniniWatchWidgetEntry(date: .now, state: WatchSharedContainer.stateStore.load())
        completion(
            Timeline(
                entries: [entry],
                policy: .after(Calendar.current.date(byAdding: .minute, value: 15, to: .now) ?? .now)
            )
        )
    }
}

struct PlaniniWatchWidgetEntryView: View {
    let entry: PlaniniWatchWidgetEntry
    @Environment(\.widgetFamily) private var family

    var body: some View {
        if entry.state.canQuickAdd {
            Button(intent: QuickAddFavoriteItemIntent()) {
                switch family {
                case .accessoryCircular:
                    ZStack {
                        Circle()
                            .fill(.tint.opacity(0.18))
                        Image(systemName: "plus")
                            .font(.title3.weight(.bold))
                    }
                case .accessoryInline:
                    Text("Add \(entry.state.quickAddItemName)")
                default:
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.state.favoriteListName ?? "Favorite")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text("Add \(entry.state.quickAddItemName)")
                            .font(.headline)
                            .lineLimit(2)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .buttonStyle(.plain)
        } else {
            Text(family == .accessoryInline ? "Open iPhone app" : "Set up in iPhone app")
        }
    }
}

struct PlaniniWatchWidget: Widget {
    let kind = "PlaniniWatchWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: PlaniniWatchWidgetProvider()) { entry in
            PlaniniWatchWidgetEntryView(entry: entry)
        }
        .configurationDisplayName("Quick Add")
        .description("Add your go-to item to your favorite list right from the watch face.")
        .supportedFamilies([.accessoryCircular, .accessoryInline, .accessoryRectangular])
    }
}

@main
struct PlaniniWatchWidgetBundle: WidgetBundle {
    var body: some Widget {
        PlaniniWatchWidget()
    }
}
