import SwiftUI
import SwiftData

struct LessonListView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \Lesson.date, order: .reverse) private var lessons: [Lesson]
    @State private var showingNew = false

    var body: some View {
        List {
            if let next = lessons.compactMap(\.nextLessonDate).filter({ $0 >= Calendar.current.startOfDay(for: .now) }).min() {
                Section {
                    Label("Next lesson \(next.formatted(date: .complete, time: .shortened))", systemImage: "calendar")
                }
            }
            if lessons.isEmpty {
                ContentUnavailableView {
                    Label("No lessons yet", systemImage: "person.crop.circle.badge.checkmark")
                } description: {
                    Text("Log in-person or online lessons: what your coach saw, the drills they gave you, and the swings that go with them.")
                }
            }
            ForEach(lessons) { lesson in
                NavigationLink {
                    LessonDetailView(lesson: lesson)
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(lesson.title).font(.headline)
                        Text([lesson.coachName, lesson.format, lesson.date.formatted(date: .abbreviated, time: .omitted)]
                                .filter { !$0.isEmpty }.joined(separator: " · "))
                            .font(.caption).foregroundStyle(.secondary)
                        if !lesson.swings.isEmpty {
                            Label("\(lesson.swings.count) swing\(lesson.swings.count == 1 ? "" : "s")", systemImage: "video")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .onDelete { offsets in
                for i in offsets { context.delete(lessons[i]) }
            }
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showingNew = true } label: { Image(systemName: "plus") }
            }
        }
        .sheet(isPresented: $showingNew) { LessonEditorView(lesson: nil) }
    }
}

struct LessonDetailView: View {
    @Bindable var lesson: Lesson
    @State private var editing = false
    @State private var attaching = false

    var body: some View {
        List {
            Section {
                LabeledContent("Coach", value: lesson.coachName.isEmpty ? "—" : lesson.coachName)
                LabeledContent("Format", value: lesson.format)
                LabeledContent("Date", value: lesson.date.formatted(date: .long, time: .shortened))
                if let next = lesson.nextLessonDate {
                    LabeledContent("Next lesson", value: next.formatted(date: .abbreviated, time: .shortened))
                }
                if let link = lesson.link.flatMap(URL.init(string:)) {
                    Link(destination: link) { Label("Open lesson in coach app", systemImage: "arrow.up.forward.app") }
                }
            }
            if !lesson.feedback.isEmpty {
                Section("Coach feedback") { Text(lesson.feedback) }
            }
            if !lesson.assignedDrills.isEmpty {
                Section("Assigned drills") {
                    ForEach(lesson.assignedDrills.split(separator: "\n").map(String.init), id: \.self) { line in
                        Label(line, systemImage: "checklist")
                    }
                }
            }
            Section {
                ForEach(lesson.swings.sorted { $0.date > $1.date }) { swing in
                    NavigationLink {
                        SwingDetailView(swing: swing)
                    } label: {
                        SwingRow(swing: swing)
                    }
                }
                Button { attaching = true } label: { Label("Attach Swings", systemImage: "paperclip") }
            } header: {
                Text("Swings")
            } footer: {
                Text("Record or import swings on the Swings tab, or share them from your coaching app, then attach them here.")
            }
        }
        .navigationTitle(lesson.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Edit") { editing = true } }
        .sheet(isPresented: $editing) { LessonEditorView(lesson: lesson) }
        .sheet(isPresented: $attaching) { AttachSwingsView(lesson: lesson) }
    }
}

struct AttachSwingsView: View {
    let lesson: Lesson
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \SwingVideo.date, order: .reverse) private var swings: [SwingVideo]

    var body: some View {
        NavigationStack {
            List(swings) { swing in
                Button {
                    swing.lesson = swing.lesson?.persistentModelID == lesson.persistentModelID ? nil : lesson
                } label: {
                    HStack {
                        SwingRow(swing: swing).foregroundStyle(.primary)
                        Spacer()
                        if swing.lesson?.persistentModelID == lesson.persistentModelID {
                            Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                        }
                    }
                }
            }
            .overlay {
                if swings.isEmpty { ContentUnavailableView("No swings yet", systemImage: "video") }
            }
            .navigationTitle("Attach Swings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }
}

struct LessonEditorView: View {
    let lesson: Lesson?
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss

    @State private var date: Date
    @State private var coachName: String
    @State private var format: String
    @State private var focus: String
    @State private var feedback: String
    @State private var assignedDrills: String
    @State private var link: String
    @State private var hasNext: Bool
    @State private var nextDate: Date

    private static let formats = ["In person"] + CoachApps.suggestions.filter { $0 != "Other" } + ["Video call", "Other"]

    init(lesson: Lesson?) {
        self.lesson = lesson
        _date = State(initialValue: lesson?.date ?? .now)
        _coachName = State(initialValue: lesson?.coachName ?? (UserDefaults.standard.string(forKey: "lastCoach") ?? ""))
        _format = State(initialValue: lesson?.format ?? "In person")
        _focus = State(initialValue: lesson?.focus ?? "")
        _feedback = State(initialValue: lesson?.feedback ?? "")
        _assignedDrills = State(initialValue: lesson?.assignedDrills ?? "")
        _link = State(initialValue: lesson?.link ?? "")
        _hasNext = State(initialValue: lesson?.nextLessonDate != nil)
        _nextDate = State(initialValue: lesson?.nextLessonDate ?? Calendar.current.date(byAdding: .day, value: 14, to: .now) ?? .now)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Coach", text: $coachName)
                    Picker("Format", selection: $format) {
                        ForEach(Self.formats, id: \.self) { Text($0) }
                    }
                    DatePicker("Date", selection: $date)
                    TextField("Focus (e.g. takeaway, low point)", text: $focus)
                }
                Section("Coach feedback") {
                    TextField("Key points, swing thoughts, feels", text: $feedback, axis: .vertical).lineLimit(3...12)
                }
                Section {
                    TextField("One drill per line", text: $assignedDrills, axis: .vertical).lineLimit(2...10)
                } header: {
                    Text("Assigned drills")
                } footer: {
                    Text("Tip: add these as custom drills in your practice sessions, so you can track them.")
                }
                Section("Coach app link (optional)") {
                    TextField("https://…", text: $link)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Toggle("Next lesson booked", isOn: $hasNext)
                    if hasNext { DatePicker("Next lesson", selection: $nextDate) }
                }
            }
            .navigationTitle(lesson == nil ? "New Lesson" : "Edit Lesson")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save() }.bold() }
            }
        }
    }

    private func save() {
        let l = lesson ?? Lesson()
        if lesson == nil { context.insert(l) }
        l.date = date
        l.coachName = coachName.trimmingCharacters(in: .whitespaces)
        l.format = format
        l.focus = focus.trimmingCharacters(in: .whitespaces)
        l.feedback = feedback
        l.assignedDrills = assignedDrills.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedLink = link.trimmingCharacters(in: .whitespacesAndNewlines)
        l.link = trimmedLink.isEmpty ? nil : trimmedLink
        l.nextLessonDate = hasNext ? nextDate : nil
        if !l.coachName.isEmpty { UserDefaults.standard.set(l.coachName, forKey: "lastCoach") }
        try? context.save()
        dismiss()
    }
}
