import SwiftUI
import SwiftData

@main
struct GolfTrainerApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
        .modelContainer(for: [
            PracticeSession.self,
            DrillResult.self,
            Round.self,
            HandicapEntry.self,
            SwingVideo.self,
            Lesson.self,
        ])
    }
}

struct RootView: View {
    enum Tab: Hashable { case practice, swing, rounds, progress }

    @Environment(\.modelContext) private var context
    @Environment(\.scenePhase) private var scenePhase
    @State private var tab: Tab = .practice

    var body: some View {
        TabView(selection: $tab) {
            PracticeHomeView()
                .tabItem { Label("Practice", systemImage: "figure.golf") }
                .tag(Tab.practice)
            SwingHomeView()
                .tabItem { Label("Swing", systemImage: "video") }
                .tag(Tab.swing)
            RoundsView()
                .tabItem { Label("Rounds", systemImage: "list.number") }
                .tag(Tab.rounds)
            ProgressDashboardView()
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
                .tag(Tab.progress)
        }
        .tint(.green)
        .onChange(of: scenePhase, initial: true) { _, phase in
            guard phase == .active else { return }
            // Pick up videos and links shared from other apps via the share extension.
            if SwingStorage.importSharedInbox(into: context) > 0 {
                tab = .swing
            }
        }
    }
}
