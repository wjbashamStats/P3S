import SwiftUI
import SwiftData
import UniformTypeIdentifiers

/// Imports round history from a CSV file.
///
/// TheGrint has no public API, so there is no live sync. Get a CSV of your scores
/// from TheGrint's website (or copy them into a spreadsheet), save it to Files or
/// iCloud Drive, and pick it here. Rounds that were already imported are skipped.
struct GrintImportView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @Query private var existingRounds: [Round]
    @Query private var existingHandicaps: [HandicapEntry]

    @State private var showingPicker = false
    @State private var result: CSVImportResult?
    @State private var errorMessage: String?
    @State private var importedCount: Int?

    private var existingKeys: Set<String> { Set(existingRounds.compactMap(\.importKey)) }

    private var newRounds: [ImportedRound] {
        result?.rounds.filter { !existingKeys.contains($0.importKey) } ?? []
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("TheGrint has no public API, so rounds come in from a CSV file: an export from TheGrint, or a spreadsheet you keep yourself.")
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Required columns: **Date**, **Score**")
                        Text("Optional: Course, Holes, Par, Putts, Fairways (e.g. 8 or 8/14), Fairways Possible, GIR, Up and Downs, Penalties, Handicap Index")
                            .foregroundStyle(.secondary)
                    }
                    .font(.footnote)
                    Button {
                        showingPicker = true
                    } label: {
                        Label("Choose CSV File", systemImage: "doc.badge.plus")
                    }
                }

                if let errorMessage {
                    Section { Label(errorMessage, systemImage: "exclamationmark.triangle").foregroundStyle(.red) }
                }

                if let importedCount {
                    Section {
                        Label("Imported \(importedCount) round\(importedCount == 1 ? "" : "s").",
                              systemImage: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                    }
                }

                if let result {
                    Section {
                        LabeledContent("Rounds in file", value: "\(result.rounds.count)")
                        LabeledContent("New", value: "\(newRounds.count)")
                        LabeledContent("Already imported", value: "\(result.rounds.count - newRounds.count)")
                    }
                    if !newRounds.isEmpty {
                        Section("Preview") {
                            ForEach(newRounds.prefix(25)) { r in
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(r.courseName).font(.subheadline.bold())
                                        Text(r.date.formatted(date: .abbreviated, time: .omitted))
                                            .font(.caption).foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text("\(r.score)").monospacedDigit()
                                }
                            }
                            if newRounds.count > 25 {
                                Text("…and \(newRounds.count - 25) more").foregroundStyle(.secondary)
                            }
                        }
                    }
                    if !result.warnings.isEmpty {
                        Section("Skipped rows") {
                            ForEach(result.warnings, id: \.self) { Text($0).font(.caption) }
                        }
                    }
                }
            }
            .navigationTitle("Import from TheGrint")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Import \(newRounds.count)") { importRounds() }
                        .disabled(newRounds.isEmpty)
                }
            }
            .fileImporter(isPresented: $showingPicker,
                          allowedContentTypes: [.commaSeparatedText, .plainText, .text]) { picked in
                load(picked)
            }
        }
    }

    private func load(_ picked: Result<URL, Error>) {
        errorMessage = nil
        importedCount = nil
        result = nil
        do {
            let url = try picked.get()
            let accessed = url.startAccessingSecurityScopedResource()
            defer { if accessed { url.stopAccessingSecurityScopedResource() } }
            let data = try Data(contentsOf: url)
            guard let text = String(data: data, encoding: .utf8) ?? String(data: data, encoding: .isoLatin1) else {
                errorMessage = "Could not read the file as text."
                return
            }
            result = try GrintCSVImporter.parse(text)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func importRounds() {
        let toImport = newRounds
        let handicapDays = Set(existingHandicaps.map { Calendar.current.startOfDay(for: $0.date) })
        var addedHandicapDays = Set<Date>()

        for r in toImport {
            let round = Round(date: r.date, courseName: r.courseName, holes: r.holes, par: r.par, score: r.score)
            round.putts = r.putts
            round.fairwaysHit = r.fairwaysHit
            round.fairwaysPossible = r.fairwaysPossible
            round.greensInRegulation = r.greensInRegulation
            round.upAndDownsMade = r.upAndDownsMade
            round.upAndDownAttempts = r.upAndDownAttempts
            round.penalties = r.penalties
            round.source = .grint
            round.importKey = r.importKey
            context.insert(round)

            if let index = r.handicapIndex {
                let day = Calendar.current.startOfDay(for: r.date)
                if !handicapDays.contains(day) && !addedHandicapDays.contains(day) {
                    context.insert(HandicapEntry(date: r.date, index: index, source: .grint))
                    addedHandicapDays.insert(day)
                }
            }
        }
        try? context.save()
        importedCount = toImport.count
    }
}
