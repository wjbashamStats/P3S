import SwiftUI
import SwiftData

struct RoundsView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \Round.date, order: .reverse) private var rounds: [Round]
    @Query(sort: \HandicapEntry.date, order: .reverse) private var handicaps: [HandicapEntry]

    @State private var showingNewRound = false
    @State private var showingImport = false
    @State private var showingHandicap = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Button { showingHandicap = true } label: {
                        HStack {
                            VStack(alignment: .leading) {
                                Text("Handicap Index").font(.caption).foregroundStyle(.secondary)
                                Text(handicaps.first.map { formatIndex($0.index) } ?? "Not set")
                                    .font(.largeTitle.bold())
                                    .foregroundStyle(.primary)
                            }
                            Spacer()
                            if let latest = handicaps.first {
                                Text("Updated \(latest.date.formatted(date: .abbreviated, time: .omitted))")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }

                Section("Rounds") {
                    if rounds.isEmpty {
                        ContentUnavailableView("No rounds yet", systemImage: "flag.2.crossed",
                                               description: Text("Add a round yourself, or import your TheGrint history from the menu."))
                    }
                    ForEach(rounds) { round in
                        NavigationLink {
                            RoundEditorView(round: round)
                        } label: {
                            RoundRow(round: round)
                        }
                    }
                    .onDelete { offsets in
                        for i in offsets { context.delete(rounds[i]) }
                    }
                }
            }
            .navigationTitle("Rounds")
            .toolbar {
                Menu {
                    Button { showingNewRound = true } label: { Label("Add Round", systemImage: "plus") }
                    Button { showingImport = true } label: {
                        Label("Import from TheGrint (CSV)", systemImage: "square.and.arrow.down")
                    }
                    Link(destination: URL(string: "https://thegrint.com")!) {
                        Label("Open TheGrint", systemImage: "arrow.up.forward.app")
                    }
                } label: {
                    Image(systemName: "plus")
                }
            }
            .sheet(isPresented: $showingNewRound) {
                NavigationStack { RoundEditorView(round: nil) }
            }
            .sheet(isPresented: $showingImport) { GrintImportView() }
            .sheet(isPresented: $showingHandicap) { HandicapEditorView() }
        }
    }
}

func formatIndex(_ index: Double) -> String {
    index < 0 ? "+" + abs(index).formatted(.number.precision(.fractionLength(1)))
              : index.formatted(.number.precision(.fractionLength(1)))
}

struct RoundRow: View {
    let round: Round

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(round.courseName.isEmpty ? "Round" : round.courseName).font(.headline)
                    if round.source == .grint {
                        Text("Grint")
                            .font(.caption2.bold())
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.green.opacity(0.15), in: Capsule())
                            .foregroundStyle(.green)
                    }
                }
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing) {
                Text("\(round.score)").font(.title2.bold().monospacedDigit())
                Text(round.toParText).font(.caption).foregroundStyle(round.toPar <= 0 ? Color.green : Color.secondary)
            }
        }
    }

    private var detail: String {
        var parts = [round.date.formatted(date: .abbreviated, time: .omitted)]
        if round.holes != 18 { parts.append("\(round.holes) holes") }
        if let p = round.putts { parts.append("\(p) putts") }
        if let g = round.greensInRegulation { parts.append("\(g) GIR") }
        return parts.joined(separator: " · ")
    }
}

struct RoundEditorView: View {
    let round: Round?
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss

    @State private var date: Date
    @State private var courseName: String
    @State private var holes: Int
    @State private var par: Int
    @State private var score: Int
    @State private var putts: Int?
    @State private var fairwaysHit: Int?
    @State private var fairwaysPossible: Int?
    @State private var gir: Int?
    @State private var udMade: Int?
    @State private var udAttempts: Int?
    @State private var penalties: Int?
    @State private var notes: String

    init(round: Round?) {
        self.round = round
        _date = State(initialValue: round?.date ?? .now)
        _courseName = State(initialValue: round?.courseName ?? "")
        _holes = State(initialValue: round?.holes ?? 18)
        _par = State(initialValue: round?.par ?? 72)
        _score = State(initialValue: round?.score ?? 85)
        _putts = State(initialValue: round?.putts)
        _fairwaysHit = State(initialValue: round?.fairwaysHit)
        _fairwaysPossible = State(initialValue: round?.fairwaysPossible ?? (round == nil ? 14 : nil))
        _gir = State(initialValue: round?.greensInRegulation)
        _udMade = State(initialValue: round?.upAndDownsMade)
        _udAttempts = State(initialValue: round?.upAndDownAttempts)
        _penalties = State(initialValue: round?.penalties)
        _notes = State(initialValue: round?.notes ?? "")
    }

    var body: some View {
        Form {
            Section {
                TextField("Course", text: $courseName)
                DatePicker("Date", selection: $date, displayedComponents: .date)
                Picker("Holes", selection: $holes) {
                    Text("9").tag(9)
                    Text("18").tag(18)
                }
                .pickerStyle(.segmented)
                .onChange(of: holes) { _, new in
                    if round == nil { par = new == 9 ? 36 : 72; fairwaysPossible = new == 9 ? 7 : 14 }
                }
                Stepper("Par: \(par)", value: $par, in: 27...80)
                Stepper("Score: \(score)", value: $score, in: 20...200)
            }
            Section("Stats (optional)") {
                OptionalIntField(title: "Putts", value: $putts)
                OptionalIntField(title: "Fairways hit", value: $fairwaysHit)
                OptionalIntField(title: "Fairways possible", value: $fairwaysPossible)
                OptionalIntField(title: "Greens in regulation", value: $gir)
                OptionalIntField(title: "Up & downs made", value: $udMade)
                OptionalIntField(title: "Up & down chances", value: $udAttempts)
                OptionalIntField(title: "Penalty strokes", value: $penalties)
            }
            Section("Notes") {
                TextField("Notes", text: $notes, axis: .vertical).lineLimit(2...6)
            }
            if let round, round.source == .grint {
                Section { Text("Imported from TheGrint").foregroundStyle(.secondary) }
            }
        }
        .navigationTitle(round == nil ? "New Round" : "Round")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if round == nil {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
            ToolbarItem(placement: .confirmationAction) { Button("Save") { save() }.bold() }
        }
    }

    private func save() {
        let r = round ?? Round()
        if round == nil { context.insert(r) }
        r.date = date
        r.courseName = courseName.trimmingCharacters(in: .whitespaces)
        r.holes = holes
        r.par = par
        r.score = score
        r.putts = putts
        r.fairwaysHit = fairwaysHit
        r.fairwaysPossible = fairwaysPossible
        r.greensInRegulation = gir
        r.upAndDownsMade = udMade
        r.upAndDownAttempts = udAttempts
        r.penalties = penalties
        r.notes = notes
        try? context.save()
        dismiss()
    }
}

struct HandicapEditorView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \HandicapEntry.date, order: .reverse) private var history: [HandicapEntry]
    @State private var index: Double = 18.0
    @State private var isPlus = false
    @State private var date = Date.now

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        Text("Index")
                        Spacer()
                        TextField("0.0", value: $index, format: .number.precision(.fractionLength(1)))
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: 80)
                    }
                    Toggle("Plus handicap", isOn: $isPlus)
                    DatePicker("As of", selection: $date, displayedComponents: .date)
                } footer: {
                    Text("Copy your current index from TheGrint each time it updates, so the Progress tab can chart it.")
                }
                if !history.isEmpty {
                    Section("History") {
                        ForEach(history) { entry in
                            LabeledContent(entry.date.formatted(date: .abbreviated, time: .omitted),
                                           value: formatIndex(entry.index))
                        }
                        .onDelete { offsets in
                            for i in offsets { context.delete(history[i]) }
                        }
                    }
                }
            }
            .navigationTitle("Handicap")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        context.insert(HandicapEntry(date: date, index: isPlus ? -abs(index) : abs(index)))
                        try? context.save()
                        dismiss()
                    }
                }
            }
            .onAppear {
                if let latest = history.first {
                    index = abs(latest.index)
                    isPlus = latest.index < 0
                }
            }
        }
    }
}
