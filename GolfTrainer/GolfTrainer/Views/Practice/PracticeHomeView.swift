import SwiftUI
import SwiftData

struct PracticeHomeView: View {
    @Query(sort: \PracticeSession.date, order: .reverse) private var sessions: [PracticeSession]
    @State private var newSessionCategory: PracticeCategory?

    var body: some View {
        NavigationStack {
            List {
                Section("Start a session") {
                    ForEach(PracticeCategory.allCases) { category in
                        Button {
                            newSessionCategory = category
                        } label: {
                            Label("New \(category.title) Session", systemImage: category.systemImage)
                                .foregroundStyle(category.color)
                        }
                    }
                }

                Section("Session logs") {
                    ForEach(PracticeCategory.allCases) { category in
                        NavigationLink {
                            SessionListView(category: category)
                        } label: {
                            HStack {
                                Label(category.title, systemImage: category.systemImage)
                                Spacer()
                                Text("\(sessions.filter { $0.category == category }.count)")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    NavigationLink {
                        DrillLibraryView()
                    } label: {
                        Label("Drill Library", systemImage: "books.vertical")
                    }
                }

                if !sessions.isEmpty {
                    Section("Recent") {
                        ForEach(sessions.prefix(5)) { session in
                            NavigationLink {
                                SessionDetailView(session: session)
                            } label: {
                                SessionRow(session: session, showsCategory: true)
                            }
                        }
                    }
                }
            }
            .navigationTitle("Practice")
            .sheet(item: $newSessionCategory) { category in
                SessionLoggerView(category: category)
            }
        }
    }
}

struct SessionListView: View {
    let category: PracticeCategory
    @Environment(\.modelContext) private var context
    @Query private var sessions: [PracticeSession]
    @State private var showingLogger = false

    init(category: PracticeCategory) {
        self.category = category
        let raw = category.rawValue
        _sessions = Query(filter: #Predicate<PracticeSession> { $0.categoryRaw == raw },
                          sort: \PracticeSession.date, order: .reverse)
    }

    var body: some View {
        List {
            if sessions.isEmpty {
                ContentUnavailableView("No \(category.title) sessions yet",
                                       systemImage: category.systemImage,
                                       description: Text("Tap + to log your first session."))
            }
            ForEach(sessions) { session in
                NavigationLink {
                    SessionDetailView(session: session)
                } label: {
                    SessionRow(session: session, showsCategory: false)
                }
            }
            .onDelete { offsets in
                for i in offsets { context.delete(sessions[i]) }
            }
        }
        .navigationTitle(category.title)
        .toolbar {
            Button { showingLogger = true } label: { Image(systemName: "plus") }
        }
        .sheet(isPresented: $showingLogger) {
            SessionLoggerView(category: category)
        }
    }
}

struct SessionRow: View {
    let session: PracticeSession
    let showsCategory: Bool

    var body: some View {
        HStack(spacing: 12) {
            if showsCategory {
                Image(systemName: session.category.systemImage)
                    .foregroundStyle(session.category.color)
                    .frame(width: 24)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(session.date.formatted(date: .abbreviated, time: .shortened))
                    .font(.headline)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            Text("\(session.durationMinutes)m")
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    private var subtitle: String {
        let names = session.sortedDrills.map(\.drillName)
        if names.isEmpty { return session.notes.isEmpty ? "No drills logged" : session.notes }
        return names.joined(separator: " · ")
    }
}

struct SessionDetailView: View {
    @Bindable var session: PracticeSession
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @State private var editing = false
    @State private var confirmDelete = false

    var body: some View {
        List {
            Section {
                LabeledContent("Type", value: session.category.title)
                LabeledContent("Date", value: session.date.formatted(date: .long, time: .shortened))
                LabeledContent("Duration", value: "\(session.durationMinutes) min")
                if let balls = session.ballsHit { LabeledContent("Balls hit", value: "\(balls)") }
                if !session.location.isEmpty { LabeledContent("Location", value: session.location) }
                LabeledContent("Rating") {
                    Text(String(repeating: "★", count: session.rating) + String(repeating: "☆", count: 5 - session.rating))
                        .foregroundStyle(.yellow)
                }
            }
            Section("Drills") {
                if session.drills.isEmpty { Text("No drills logged").foregroundStyle(.secondary) }
                ForEach(session.sortedDrills) { drill in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(drill.drillName).font(.headline)
                            Spacer()
                            Text(drill.summary).monospacedDigit()
                        }
                        if !drill.notes.isEmpty {
                            Text(drill.notes).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if !session.notes.isEmpty {
                Section("Notes") { Text(session.notes) }
            }
            Section {
                Button("Delete Session", role: .destructive) { confirmDelete = true }
            }
        }
        .navigationTitle(session.category.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Edit") { editing = true } }
        .sheet(isPresented: $editing) { SessionLoggerView(existing: session) }
        .confirmationDialog("Delete this session?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                dismiss()
                context.delete(session)
            }
        }
    }
}

struct DrillLibraryView: View {
    var body: some View {
        List {
            ForEach(PracticeCategory.allCases) { category in
                Section(category.title) {
                    ForEach(DrillLibrary.drills(for: category)) { drill in
                        DisclosureGroup {
                            Text(drill.instructions).font(.subheadline)
                            LabeledContent("Scoring", value: drill.metric.title)
                            LabeledContent("Reps", value: "\(drill.defaultAttempts)")
                            if let goal = drill.goal {
                                LabeledContent("Goal", value: goalText(goal, drill.metric))
                            }
                        } label: {
                            Text(drill.name)
                        }
                    }
                }
            }
        }
        .navigationTitle("Drill Library")
    }

    private func goalText(_ goal: Double, _ metric: DrillMetric) -> String {
        switch metric {
        case .makes: return "\(Int(goal))%+"
        case .points: return "\(Int(goal))+ pts"
        case .strokes: return "\(Int(goal)) or fewer"
        case .proximity: return "Under \(Int(goal)) ft"
        }
    }
}
