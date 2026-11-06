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
        ])
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            PracticeHomeView()
                .tabItem { Label("Practice", systemImage: "figure.golf") }
            RoundsView()
                .tabItem { Label("Rounds", systemImage: "list.number") }
            ProgressDashboardView()
                .tabItem { Label("Progress", systemImage: "chart.line.uptrend.xyaxis") }
        }
        .tint(.green)
    }
}
