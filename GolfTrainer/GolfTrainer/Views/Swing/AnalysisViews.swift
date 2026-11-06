import SwiftUI
import SwiftData
import PhotosUI

/// Mark key positions while scrubbing, then tap a chip to jump back to one.
struct CheckpointBar: View {
    @Bindable var swing: SwingVideo
    let model: SwingPlayerModel

    var body: some View {
        let marked = swing.checkpoints
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Menu {
                    ForEach(SwingPosition.allCases) { pos in
                        Button {
                            var cps = swing.checkpoints.filter { $0.position != pos }
                            cps.append(SwingCheckpoint(position: pos, time: model.currentTime))
                            swing.checkpoints = cps
                        } label: {
                            if marked.contains(where: { $0.position == pos }) {
                                Label("\(pos.title) (move here)", systemImage: "checkmark")
                            } else {
                                Text(pos.title)
                            }
                        }
                    }
                } label: {
                    Label("Mark", systemImage: "mappin.and.ellipse")
                        .font(.subheadline.bold())
                        .padding(.horizontal, 10).padding(.vertical, 6)
                        .background(Color.accentColor.opacity(0.15), in: Capsule())
                }
                ForEach(marked) { cp in
                    Button {
                        model.pause()
                        model.seek(to: cp.time)
                    } label: {
                        Text("\(cp.position.title) \(String(format: "%.2f", cp.time))s")
                            .font(.caption.monospacedDigit())
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color.secondary.opacity(0.15), in: Capsule())
                    }
                    .contextMenu {
                        Button("Remove", role: .destructive) {
                            swing.checkpoints = swing.checkpoints.filter { $0.position != cp.position }
                        }
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }
}

/// Screenshots attached to a swing, e.g. annotated stills from your analysis app.
struct ScreenshotGallery: View {
    @Bindable var swing: SwingVideo
    @State private var picks: [PhotosPickerItem] = []
    @State private var viewing: URL?

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 90), spacing: 8)], spacing: 8) {
            ForEach(swing.imageFileNames, id: \.self) { name in
                ScreenshotThumb(name: name)
                    .onTapGesture { viewing = SwingStorage.imageURL(named: name) }
                    .contextMenu {
                        ShareLink(item: SwingStorage.imageURL(named: name))
                        Button("Remove", role: .destructive) {
                            swing.imageFileNames.removeAll { $0 == name }
                            SwingStorage.deleteImage(named: name)
                        }
                    }
            }
            PhotosPicker(selection: $picks, maxSelectionCount: 10, matching: .images) {
                VStack(spacing: 4) {
                    Image(systemName: "plus.viewfinder").font(.title2)
                    Text("Add").font(.caption)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .padding(.vertical, 4)
        .onChange(of: picks) { _, items in
            guard !items.isEmpty else { return }
            Task {
                for item in items {
                    if let data = try? await item.loadTransferable(type: Data.self),
                       let name = try? SwingStorage.store(imageData: data, fileExtension: "jpg") {
                        swing.imageFileNames.append(name)
                    }
                }
                picks = []
            }
        }
        .fullScreenCover(item: Binding(get: { viewing.map(IdentifiedURL.init) }, set: { viewing = $0?.url })) { item in
            ScreenshotViewer(url: item.url)
        }
    }
}

struct IdentifiedURL: Identifiable {
    let url: URL
    var id: URL { url }
}

struct ScreenshotThumb: View {
    let name: String
    @State private var image: UIImage?

    var body: some View {
        ZStack {
            Color.secondary.opacity(0.12)
            if let image { Image(uiImage: image).resizable().scaledToFill() }
        }
        .frame(minHeight: 120)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .task(id: name) { image = await SwingStorage.imageThumbnail(named: name) }
    }
}

struct ScreenshotViewer: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss
    @State private var scale: CGFloat = 1

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()
                if let image = UIImage(contentsOfFile: url.path) {
                    Image(uiImage: image)
                        .resizable()
                        .scaledToFit()
                        .scaleEffect(scale)
                        .gesture(MagnifyGesture().onChanged { scale = max(1, $0.magnification) }
                                                 .onEnded { _ in withAnimation { scale = 1 } })
                }
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) { ShareLink(item: url) }
            }
            .toolbarBackground(.visible, for: .navigationBar)
        }
    }
}

/// Builds a package for the swing-analyzer chat: key-position frames, a one-image sheet,
/// the current frame, screenshots, the video and a context message.
struct AnalysisExportView: View {
    let swing: SwingVideo
    /// Where the player is paused, for "current frame".
    let currentTime: Double?
    var frameRate: Double? = nil

    @Environment(\.dismiss) private var dismiss
    @Query(sort: \HandicapEntry.date, order: .reverse) private var handicaps: [HandicapEntry]

    @State private var includeSheet = true
    @State private var includeFrames = false
    @State private var includeCurrentFrame = false
    @State private var includeScreenshots = true
    @State private var includeVideo = false
    @State private var includeContext = true
    @State private var drawLines = true
    @State private var isBuilding = false
    @State private var shareItems: [Any]?
    @State private var errorMessage: String?

    private var hasVideo: Bool { swing.videoURL != nil }
    private var hasCheckpoints: Bool { hasVideo && !swing.checkpoints.isEmpty }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Key positions sheet (one image)", isOn: $includeSheet).disabled(!hasCheckpoints)
                    Toggle("Each key position as its own image", isOn: $includeFrames).disabled(!hasCheckpoints)
                    if let currentTime, hasVideo {
                        Toggle("Current frame (\(String(format: "%.2f", currentTime))s)", isOn: $includeCurrentFrame)
                    }
                    if hasVideo { Toggle("Video clip", isOn: $includeVideo) }
                    if !swing.imageFileNames.isEmpty {
                        Toggle("Screenshots (\(swing.imageFileNames.count))", isOn: $includeScreenshots)
                    }
                    if hasVideo && !swing.lines.isEmpty { Toggle("Draw my lines on frames", isOn: $drawLines) }
                } header: {
                    Text("Images & video")
                } footer: {
                    if hasVideo && swing.checkpoints.isEmpty {
                        Text("Tip: use **Mark** under the player to tag Address, Top, Impact and so on. Chat tools usually analyse a few sharp still frames better than a whole video.")
                    }
                }
                Section {
                    Toggle("Include context message", isOn: $includeContext)
                    if includeContext {
                        Text(contextText).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                } footer: {
                    Text("Club, camera angle, handicap and your notes, plus a request for the top issues and drills. If the chat app doesn't pick up the text, use Copy Context and paste it.")
                }
                if let errorMessage {
                    Section { Label(errorMessage, systemImage: "exclamationmark.triangle").foregroundStyle(.red) }
                }
                Section {
                    Button {
                        Task { await build() }
                    } label: {
                        HStack {
                            Label("Share to Analyzer Chat…", systemImage: "square.and.arrow.up")
                            if isBuilding { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(isBuilding || !hasSomething)
                    Button {
                        UIPasteboard.general.string = contextText
                    } label: {
                        Label("Copy Context", systemImage: "doc.on.doc")
                    }
                }
            }
            .navigationTitle("Share for Analysis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } } }
            .sheet(isPresented: Binding(get: { shareItems != nil }, set: { if !$0 { shareItems = nil } })) {
                ActivityView(items: shareItems ?? []).presentationDetents([.medium, .large])
            }
            .onAppear {
                includeSheet = hasCheckpoints
                includeCurrentFrame = hasVideo && !hasCheckpoints
            }
        }
    }

    private var hasSomething: Bool {
        (includeSheet && hasCheckpoints) || (includeFrames && hasCheckpoints) || (includeCurrentFrame && hasVideo)
            || (includeVideo && hasVideo) || (includeScreenshots && !swing.imageFileNames.isEmpty) || includeContext
    }

    private var contextText: String {
        SwingContext(club: swing.club,
                     angle: swing.angle == .other ? "" : swing.angle.title,
                     date: swing.date,
                     handicapIndex: handicaps.first?.index,
                     notes: swing.notes,
                     lessonFocus: swing.lesson?.focus,
                     lessonFeedback: swing.lesson?.feedback,
                     checkpoints: swing.checkpoints,
                     frameRate: frameRate,
                     includesKeyPositionSheet: includeSheet && hasCheckpoints).text()
    }

    @MainActor
    private func build() async {
        isBuilding = true
        errorMessage = nil
        defer { isBuilding = false }
        var items: [Any] = []
        let lines = drawLines ? swing.lines : []
        let baseName = [swing.club, swing.date.formatted(.dateTime.month(.abbreviated).day())]
            .filter { !$0.isEmpty }.joined(separator: " ")
        do {
            if let video = swing.videoURL {
                if hasCheckpoints && (includeSheet || includeFrames) {
                    var frames: [(label: String, image: UIImage)] = []
                    for cp in swing.checkpoints.sorted(by: { $0.time < $1.time }) {
                        let raw = try await SwingExport.frame(from: video, at: cp.time)
                        frames.append((label: cp.position.title, image: SwingExport.render(raw, lines: lines)))
                    }
                    if includeSheet, let sheet = SwingExport.keyPositionSheet(frames, title: swing.title) {
                        items.append(try SwingExport.temporaryFile(for: sheet, named: "\(baseName) key positions"))
                    }
                    if includeFrames {
                        for (i, f) in frames.enumerated() {
                            let labelled = SwingExport.render(f.image, lines: [], label: "\(i + 1). \(f.label)")
                            items.append(try SwingExport.temporaryFile(for: labelled, named: "\(baseName) \(i + 1) \(f.label)"))
                        }
                    }
                }
                if includeCurrentFrame, let t = currentTime {
                    let raw = try await SwingExport.frame(from: video, at: t)
                    let img = SwingExport.render(raw, lines: lines, label: String(format: "%.2fs", t))
                    items.append(try SwingExport.temporaryFile(for: img, named: "\(baseName) frame \(String(format: "%.2f", t))s"))
                }
                if includeVideo { items.append(video) }
            }
            if includeScreenshots { items.append(contentsOf: swing.imageURLs) }
            if includeContext { items.append(contextText) }
            shareItems = items
        } catch {
            errorMessage = "Couldn't build the frames: \(error.localizedDescription)"
        }
    }
}

/// Paste the analyzer's (or coach's) response back into the swing.
struct AnalysisNotesSection: View {
    @Bindable var swing: SwingVideo

    var body: some View {
        Section {
            TextField("Paste the analyzer chat's feedback here", text: $swing.analysis, axis: .vertical)
                .lineLimit(3...20)
                .onChange(of: swing.analysis) { _, new in
                    swing.analysisDate = new.isEmpty ? nil : .now
                }
            Button {
                if let text = UIPasteboard.general.string, !text.isEmpty {
                    swing.analysis = swing.analysis.isEmpty ? text : swing.analysis + "\n\n" + text
                }
            } label: {
                Label("Paste Feedback", systemImage: "doc.on.clipboard")
            }
        } header: {
            Text("Analysis feedback")
        } footer: {
            if let d = swing.analysisDate {
                Text("Updated \(d.formatted(date: .abbreviated, time: .shortened))")
            }
        }
    }
}
