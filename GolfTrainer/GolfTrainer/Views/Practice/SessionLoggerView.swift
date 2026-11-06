import SwiftUI
import SwiftData

/// An in-memory drill entry, kept separate from SwiftData until the session is saved.
struct DraftDrill: Identifiable, Equatable {
    let id = UUID()
    var name: String
    var metric: DrillMetric
    var attempts: Int
    var successes: Int = 0
    var value: Double = 0
    var notes: String = ""
    var targetAttempts: Int
    /// Make/miss taps from this editing session (true = make), so Undo reverses the last tap exactly.
    var history: [Bool] = []

    mutating func record(make: Bool) {
        attempts += 1
        if make { successes += 1 }
        history.append(make)
    }

    mutating func undo() {
        guard attempts > 0 else { return }
        // With no tap history (an older entry being edited), take off a miss first.
        let wasMake = history.popLast() ?? (successes == attempts)
        attempts -= 1
        if wasMake { successes = max(0, successes - 1) }
        successes = min(successes, attempts)
    }

    init(template: DrillTemplate) {
        name = template.name
        metric = template.metric
        targetAttempts = template.defaultAttempts
        attempts = template.metric == .makes ? 0 : template.defaultAttempts
    }

    init(result: DrillResult) {
        name = result.drillName
        metric = result.metric
        attempts = result.attempts
        successes = result.successes
        value = result.value
        notes = result.notes
        targetAttempts = DrillLibrary.template(named: result.drillName)?.defaultAttempts ?? result.attempts
    }
}

/// Logs a new practice session, or edits an existing one.
struct SessionLoggerView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss

    private let existing: PracticeSession?
    private let category: PracticeCategory
    @State private var openedAt = Date.now

    @State private var date: Date
    @State private var durationMinutes: Int
    @State private var durationEdited: Bool
    @State private var ballsHit: Int?
    @State private var location: String
    @State private var notes: String
    @State private var rating: Int
    @State private var drills: [DraftDrill]
    @State private var showingPicker = false

    init(category: PracticeCategory) {
        self.existing = nil
        self.category = category
        _date = State(initialValue: .now)
        _durationMinutes = State(initialValue: 0)
        _durationEdited = State(initialValue: false)
        _ballsHit = State(initialValue: nil)
        _location = State(initialValue: UserDefaults.standard.string(forKey: "lastLocation") ?? "")
        _notes = State(initialValue: "")
        _rating = State(initialValue: 3)
        _drills = State(initialValue: [])
    }

    init(existing session: PracticeSession) {
        self.existing = session
        self.category = session.category
        _date = State(initialValue: session.date)
        _durationMinutes = State(initialValue: session.durationMinutes)
        _durationEdited = State(initialValue: true)
        _ballsHit = State(initialValue: session.ballsHit)
        _location = State(initialValue: session.location)
        _notes = State(initialValue: session.notes)
        _rating = State(initialValue: session.rating)
        _drills = State(initialValue: session.sortedDrills.map(DraftDrill.init(result:)))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    DatePicker("Date", selection: $date)
                    TextField("Location (optional)", text: $location)
                    if existing == nil {
                        TimelineView(.periodic(from: openedAt, by: 1)) { context in
                            LabeledContent("Session timer") {
                                Text(elapsedText(at: context.date)).monospacedDigit()
                            }
                        }
                    }
                    Stepper(value: Binding(
                        get: { durationMinutes },
                        set: { durationMinutes = max(0, $0); durationEdited = true }
                    ), in: 0...600, step: 5) {
                        LabeledContent("Duration", value: durationMinutes == 0 && !durationEdited
                                       ? "Uses the timer" : "\(durationMinutes) min")
                    }
                    if category == .range {
                        OptionalIntField(title: "Balls hit", value: $ballsHit)
                    }
                }

                Section {
                    ForEach($drills) { $drill in
                        DrillEntryView(drill: $drill)
                    }
                    .onDelete { drills.remove(atOffsets: $0) }
                    .onMove { drills.move(fromOffsets: $0, toOffset: $1) }

                    Button {
                        showingPicker = true
                    } label: {
                        Label("Add Drill", systemImage: "plus.circle.fill")
                    }
                } header: {
                    Text("Drills")
                } footer: {
                    if drills.isEmpty {
                        Text("Add drills from the library, or create your own. Each one is tracked over time on the Progress tab.")
                    }
                }

                Section("How did it go?") {
                    RatingView(rating: $rating)
                    TextField("Notes: swing thoughts, what worked, what to work on next", text: $notes, axis: .vertical)
                        .lineLimit(3...8)
                }
            }
            .navigationTitle(existing == nil ? "New \(category.title) Session" : "Edit Session")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }.bold()
                }
            }
            .sheet(isPresented: $showingPicker) {
                DrillPickerView(category: category) { template in
                    drills.append(DraftDrill(template: template))
                }
            }
        }
        .interactiveDismissDisabled(!drills.isEmpty)
    }

    private func elapsedText(at now: Date) -> String {
        let seconds = Int(now.timeIntervalSince(openedAt))
        return String(format: "%d:%02d:%02d", seconds / 3600, (seconds / 60) % 60, seconds % 60)
    }

    private func save() {
        let session = existing ?? PracticeSession(date: date, category: category)
        if existing == nil {
            context.insert(session)
        }
        session.date = date
        session.durationMinutes = durationEdited || durationMinutes > 0
            ? durationMinutes
            : max(1, Int((Date.now.timeIntervalSince(openedAt) / 60).rounded()))
        session.ballsHit = category == .range ? ballsHit : nil
        session.location = location.trimmingCharacters(in: .whitespaces)
        session.notes = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        session.rating = rating

        for old in session.drills { context.delete(old) }
        session.drills = []
        for (index, d) in drills.enumerated() {
            let result = DrillResult(drillName: d.name, metric: d.metric, attempts: d.attempts,
                                     successes: min(d.successes, d.attempts), value: d.value,
                                     notes: d.notes, order: index)
            context.insert(result)
            result.session = session
        }
        if !session.location.isEmpty {
            UserDefaults.standard.set(session.location, forKey: "lastLocation")
        }
        try? context.save()
        dismiss()
    }
}

/// One drill row in the logger. "Make" and "Miss" are large tap targets for use on the range.
struct DrillEntryView: View {
    @Binding var drill: DraftDrill
    @State private var showNotes = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(drill.name).font(.headline)
                Spacer()
                Text(DrillScoring.summary(metric: drill.metric, attempts: drill.attempts,
                                          successes: drill.successes, value: drill.value))
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }

            switch drill.metric {
            case .makes:
                makesControls
            case .points, .strokes:
                Stepper(value: $drill.value, in: 0...500, step: 1) {
                    Text("\(drill.metric == .points ? "Points" : "Strokes"): \(Int(drill.value))")
                }
            case .proximity:
                HStack {
                    Text("Avg. distance (ft)")
                    Spacer()
                    TextField("0", value: $drill.value, format: .number.precision(.fractionLength(0...1)))
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: 80)
                }
                Stepper("Balls: \(drill.attempts)", value: $drill.attempts, in: 0...200)
            }

            if showNotes || !drill.notes.isEmpty {
                TextField("Drill notes", text: $drill.notes, axis: .vertical)
                    .font(.subheadline)
            } else {
                Button("Add note") { showNotes = true }
                    .font(.caption)
                    .buttonStyle(.borderless)
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var makesControls: some View {
        if drill.targetAttempts > 0 {
            ProgressView(value: Double(min(drill.attempts, drill.targetAttempts)),
                         total: Double(drill.targetAttempts)) {
                Text("\(drill.attempts) of \(drill.targetAttempts) reps")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        HStack(spacing: 12) {
            Button {
                drill.record(make: false)
            } label: {
                Label("Miss", systemImage: "xmark")
                    .frame(maxWidth: .infinity, minHeight: 36)
            }
            .buttonStyle(.bordered)
            .tint(.red)

            Button {
                drill.record(make: true)
            } label: {
                Label("Make", systemImage: "checkmark")
                    .frame(maxWidth: .infinity, minHeight: 36)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)

            Button {
                drill.undo()
            } label: {
                Image(systemName: "arrow.uturn.backward")
                    .frame(minHeight: 36)
            }
            .buttonStyle(.bordered)
            .disabled(drill.attempts == 0)
        }
        .sensoryFeedback(.impact(weight: .light), trigger: drill.attempts)
    }
}

struct DrillPickerView: View {
    let category: PracticeCategory
    let onPick: (DrillTemplate) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var customName = ""
    @State private var customMetric: DrillMetric = .makes
    @State private var customReps = 10

    var body: some View {
        NavigationStack {
            List {
                Section("\(category.title) drills") {
                    ForEach(DrillLibrary.drills(for: category)) { template in
                        Button {
                            onPick(template)
                            dismiss()
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(template.name).font(.headline).foregroundStyle(.primary)
                                Text(template.instructions)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                            }
                        }
                    }
                }
                Section("Custom drill") {
                    TextField("Drill name", text: $customName)
                    Picker("Scoring", selection: $customMetric) {
                        ForEach(DrillMetric.allCases) { Text($0.title).tag($0) }
                    }
                    Stepper("Reps: \(customReps)", value: $customReps, in: 1...200)
                    Button("Add Custom Drill") {
                        let name = customName.trimmingCharacters(in: .whitespaces)
                        onPick(DrillTemplate(name, category, customMetric, attempts: customReps, "Custom drill"))
                        dismiss()
                    }
                    .disabled(customName.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .navigationTitle("Add Drill")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
        }
    }
}
