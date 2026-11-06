import SwiftUI
import SwiftData

struct SwingDetailView: View {
    @Bindable var swing: SwingVideo
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \Lesson.date, order: .reverse) private var lessons: [Lesson]
    @Query(sort: \PracticeSession.date, order: .reverse) private var sessions: [PracticeSession]

    @State private var model: SwingPlayerModel?
    @State private var lines: [SwingLine] = []
    @State private var isDrawing = false
    @State private var colorIndex = 0
    @State private var showingComparePicker = false
    @State private var compareWith: SwingVideo?
    @State private var confirmDelete = false
    @State private var showingAnalysisExport = false

    var body: some View {
        List {
            if let model {
                Section {
                    player(model)
                        .listRowInsets(EdgeInsets())
                    PlayerControls(model: model)
                    CheckpointBar(swing: swing, model: model)
                    drawingTools
                }
            } else if swing.videoURL != nil {
                Section { Text("Video file not found.").foregroundStyle(.secondary) }
            }

            Section {
                Button {
                    model?.pause()
                    showingAnalysisExport = true
                } label: {
                    Label("Share for Analysis…", systemImage: "sparkles.rectangle.stack")
                }
                .disabled(!swing.hasMedia)
            } footer: {
                Text("Send key-position frames, screenshots, the video and a context message to your swing-analyzer chat. Then paste its feedback below.")
            }

            Section {
                ScreenshotGallery(swing: swing)
            } header: {
                Text("Screenshots")
            } footer: {
                if swing.imageFileNames.isEmpty {
                    Text("Add stills from your analysis app, or share them to Golf Trainer from that app.")
                }
            }

            AnalysisNotesSection(swing: swing)

            if let link = swing.linkURL {
                Section {
                    Link(destination: link) {
                        Label("Open in \(swing.sourceApp ?? "browser")", systemImage: "arrow.up.forward.app")
                    }
                    Text(link.absoluteString).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
            }

            Section("Details") {
                ClubPicker(club: $swing.club)
                Picker("Camera angle", selection: $swing.angleRaw) {
                    ForEach(CameraAngle.allCases) { Text($0.title).tag($0.rawValue) }
                }
                DatePicker("Date", selection: $swing.date)
                Toggle("Favorite", isOn: $swing.isFavorite)
                LabeledContent("Source", value: swing.sourceApp ?? swing.source.title)
            }

            Section("Links") {
                Picker("Lesson", selection: $swing.lesson) {
                    Text("None").tag(nil as Lesson?)
                    ForEach(lessons) { Text("\($0.title) (\($0.date.formatted(date: .numeric, time: .omitted)))").tag(Optional($0)) }
                }
                Picker("Practice session", selection: $swing.session) {
                    Text("None").tag(nil as PracticeSession?)
                    ForEach(sessions.prefix(40)) { s in
                        Text("\(s.category.title), \(s.date.formatted(date: .abbreviated, time: .omitted))").tag(Optional(s))
                    }
                }
            }

            Section("Notes") {
                TextField("What you were working on, coach feedback…", text: $swing.notes, axis: .vertical)
                    .lineLimit(3...10)
            }

            Section {
                if let url = swing.videoURL, model != nil {
                    ShareLink(item: url, preview: SharePreview(swing.title)) {
                        Label("Send to Coach / Share", systemImage: "square.and.arrow.up")
                    }
                    Button { showingComparePicker = true } label: {
                        Label("Compare Side by Side", systemImage: "rectangle.split.2x1")
                    }
                }
                Button("Delete Swing", role: .destructive) { confirmDelete = true }
            } footer: {
                if model != nil {
                    Text("Share sends the video through the iOS share sheet: your coaching app (if it accepts videos), Messages, Mail or AirDrop.")
                }
            }
        }
        .scrollDisabled(isDrawing)
        .navigationTitle(swing.title)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            lines = swing.lines
            if model == nil, let url = swing.videoURL, FileManager.default.fileExists(atPath: url.path) {
                model = SwingPlayerModel(url: url)
            }
        }
        .onDisappear {
            model?.pause()
            if swing.needsReview { swing.needsReview = false }
        }
        .onChange(of: lines) { _, new in swing.lines = new }
        .sheet(isPresented: $showingAnalysisExport) {
            AnalysisExportView(swing: swing, currentTime: model?.currentTime, frameRate: model?.frameRate)
        }
        .sheet(isPresented: $showingComparePicker) {
            SwingPickerView(excluding: swing) { picked in compareWith = picked }
        }
        .fullScreenCover(item: $compareWith) { other in
            CompareSwingsView(left: swing, right: other)
        }
        .confirmationDialog("Delete this swing?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                model?.pause()
                dismiss()
                SwingStorage.delete(swing, in: context)
            }
        }
    }

    private func player(_ model: SwingPlayerModel) -> some View {
        ZStack {
            Color.black
            PlayerLayerView(player: model.player)
                .overlay {
                    LineOverlay(lines: $lines, isDrawing: isDrawing, colorIndex: colorIndex,
                                aspectRatio: model.aspectRatio)
                }
                .aspectRatio(model.aspectRatio, contentMode: .fit)
        }
        .frame(height: 440)
        .onTapGesture { if !isDrawing { model.togglePlay() } }
    }

    private var drawingTools: some View {
        HStack(spacing: 14) {
            Button {
                isDrawing.toggle()
                if isDrawing { model?.pause() }
            } label: {
                Label(isDrawing ? "Done" : "Draw", systemImage: isDrawing ? "checkmark" : "pencil.line")
            }
            .buttonStyle(.bordered)
            .tint(isDrawing ? .green : .accentColor)

            if isDrawing {
                ForEach(LinePalette.colors.indices, id: \.self) { i in
                    Circle()
                        .fill(LinePalette.colors[i])
                        .frame(width: 22, height: 22)
                        .overlay(Circle().stroke(Color.primary, lineWidth: i == colorIndex ? 2 : 0))
                        .onTapGesture { colorIndex = i }
                }
            }
            Spacer()
            Button { _ = lines.popLast() } label: { Image(systemName: "arrow.uturn.backward") }
                .disabled(lines.isEmpty)
            Button(role: .destructive) { lines.removeAll() } label: { Image(systemName: "trash") }
                .disabled(lines.isEmpty)
        }
        .buttonStyle(.borderless)
    }
}

/// Picks another swing (with a video) to compare against.
struct SwingPickerView: View {
    let excluding: SwingVideo
    let onPick: (SwingVideo) -> Void
    @Environment(\.dismiss) private var dismiss
    @Query(sort: \SwingVideo.date, order: .reverse) private var swings: [SwingVideo]

    var body: some View {
        NavigationStack {
            List {
                let candidates = swings.filter { $0.videoFileName != nil && $0.persistentModelID != excluding.persistentModelID }
                if candidates.isEmpty {
                    Text("No other swing videos yet.").foregroundStyle(.secondary)
                }
                ForEach(candidates) { swing in
                    Button {
                        dismiss()
                        // Let the sheet finish closing before the full-screen cover opens.
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { onPick(swing) }
                    } label: {
                        SwingRow(swing: swing).foregroundStyle(.primary)
                    }
                }
            }
            .navigationTitle("Compare With")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
        }
    }
}

/// Two swings side by side. Line each one up (for example at address or the top) with its own
/// scrubber, then play or step both together.
struct CompareSwingsView: View {
    let left: SwingVideo
    let right: SwingVideo
    @Environment(\.dismiss) private var dismiss
    @State private var leftModel: SwingPlayerModel?
    @State private var rightModel: SwingPlayerModel?
    @State private var rate: Float = 0.5

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                HStack(spacing: 4) {
                    pane(left, leftModel)
                    pane(right, rightModel)
                }
                .frame(maxHeight: .infinity)

                HStack(spacing: 28) {
                    Button { both { $0.step(-1) } } label: { Image(systemName: "backward.frame.fill") }
                    Button {
                        let playing = (leftModel?.isPlaying ?? false) || (rightModel?.isPlaying ?? false)
                        both { playing ? $0.pause() : $0.play() }
                    } label: {
                        Image(systemName: (leftModel?.isPlaying ?? false) ? "pause.fill" : "play.fill").font(.title)
                    }
                    Button { both { $0.step(1) } } label: { Image(systemName: "forward.frame.fill") }
                    RatePicker(rate: Binding(get: { rate }, set: { r in rate = r; both { $0.setRate(r) } }))
                }
                .font(.title2)
                .buttonStyle(.borderless)
                .padding(.bottom)
            }
            .background(Color.black.opacity(0.03))
            .navigationTitle("Compare")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { both { $0.pause() }; dismiss() } }
            }
            .onAppear {
                if leftModel == nil, let u = left.videoURL { leftModel = SwingPlayerModel(url: u) }
                if rightModel == nil, let u = right.videoURL { rightModel = SwingPlayerModel(url: u) }
                both { $0.setRate(rate) }
            }
        }
    }

    private func both(_ action: (SwingPlayerModel) -> Void) {
        [leftModel, rightModel].compactMap { $0 }.forEach(action)
    }

    @ViewBuilder
    private func pane(_ swing: SwingVideo, _ model: SwingPlayerModel?) -> some View {
        VStack(spacing: 6) {
            Text("\(swing.title)\n\(swing.date.formatted(date: .abbreviated, time: .omitted))")
                .font(.caption)
                .multilineTextAlignment(.center)
                .lineLimit(2)
            if let model {
                ZStack {
                    Color.black
                    PlayerLayerView(player: model.player)
                        .overlay {
                            LineOverlay(lines: .constant(swing.lines), isDrawing: false, colorIndex: 0,
                                        aspectRatio: model.aspectRatio, showsAngles: false)
                        }
                        .aspectRatio(model.aspectRatio, contentMode: .fit)
                }
                PlayerControls(model: model, compact: true)
                    .padding(.horizontal, 6)
            } else {
                Spacer()
                Text("Video missing").foregroundStyle(.secondary)
                Spacer()
            }
        }
    }
}
