import SwiftUI
import SwiftData
import PhotosUI
import UniformTypeIdentifiers

struct SwingHomeView: View {
    enum Mode: String, CaseIterable, Identifiable {
        case swings = "Swings", lessons = "Lessons"
        var id: String { rawValue }
    }

    @State private var mode: Mode = .swings

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("View", selection: $mode) {
                    ForEach(Mode.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .padding([.horizontal, .top])

                switch mode {
                case .swings: SwingLibraryView()
                case .lessons: LessonListView()
                }
            }
            .navigationTitle("Swing")
        }
    }
}

struct SwingLibraryView: View {
    @Environment(\.modelContext) private var context
    @Query(sort: \SwingVideo.date, order: .reverse) private var swings: [SwingVideo]

    @State private var clubFilter = ""
    @State private var favoritesOnly = false
    @State private var showingCamera = false
    @State private var showingPhotos = false
    @State private var showingFiles = false
    @State private var showingLink = false
    @State private var photoItem: PhotosPickerItem?
    @State private var showingScreenshots = false
    @State private var screenshotItems: [PhotosPickerItem] = []
    @State private var openSwing: SwingVideo?
    @State private var isImporting = false
    @State private var errorMessage: String?

    private var filtered: [SwingVideo] {
        swings.filter { s in
            (clubFilter.isEmpty || s.club == clubFilter) && (!favoritesOnly || s.isFavorite) && !s.needsReview
        }
    }

    private var toReview: [SwingVideo] { swings.filter(\.needsReview) }

    var body: some View {
        List {
            if !toReview.isEmpty {
                Section {
                    ForEach(toReview) { swing in
                        NavigationLink(value: swing) { SwingRow(swing: swing) }
                    }
                } header: {
                    Label("New from share sheet", systemImage: "tray.and.arrow.down.fill")
                } footer: {
                    Text("Open each one to add the club and camera angle.")
                }
            }

            Section {
                if swings.isEmpty {
                    ContentUnavailableView {
                        Label("No swings yet", systemImage: "video")
                    } description: {
                        Text("Record a swing, import one from Photos or Files, or share a video to Golf Trainer from your coaching app.")
                    }
                } else if filtered.isEmpty && toReview.isEmpty {
                    Text("No swings match the filter.").foregroundStyle(.secondary)
                }
                ForEach(filtered) { swing in
                    NavigationLink(value: swing) { SwingRow(swing: swing) }
                }
                .onDelete { offsets in
                    let items = offsets.map { filtered[$0] }
                    for s in items { SwingStorage.delete(s, in: context) }
                }
            }
        }
        .overlay {
            if isImporting { ProgressView("Importing…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) }
        }
        .navigationDestination(for: SwingVideo.self) { SwingDetailView(swing: $0) }
        .navigationDestination(item: $openSwing) { SwingDetailView(swing: $0) }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Menu {
                    Toggle(isOn: $favoritesOnly) { Label("Favorites only", systemImage: "star") }
                    Picker("Club", selection: $clubFilter) {
                        Text("All clubs").tag("")
                        ForEach(Clubs.all, id: \.self) { Text($0).tag($0) }
                    }
                } label: {
                    Image(systemName: clubFilter.isEmpty && !favoritesOnly
                          ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
                }
            }
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    if CameraRecorder.isAvailable {
                        Button { showingCamera = true } label: { Label("Record Swing", systemImage: "video.fill") }
                    }
                    Button { showingPhotos = true } label: { Label("Import from Photos", systemImage: "photo.on.rectangle") }
                    Button { showingScreenshots = true } label: { Label("Import Screenshots", systemImage: "photo.stack") }
                    Button { showingFiles = true } label: { Label("Import from Files", systemImage: "folder") }
                    Button { showingLink = true } label: { Label("Add Coach App Link", systemImage: "link") }
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .fullScreenCover(isPresented: $showingCamera) {
            CameraRecorder { url in
                showingCamera = false
                if let url { addVideo(from: url, source: .camera, move: true) }
            }
            .ignoresSafeArea()
        }
        .photosPicker(isPresented: $showingPhotos, selection: $photoItem, matching: .videos)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            isImporting = true
            Task {
                defer { isImporting = false; photoItem = nil }
                do {
                    if let movie = try await item.loadTransferable(type: PickedMovie.self) {
                        addVideo(from: movie.url, source: .photos, move: true)
                    }
                } catch {
                    errorMessage = "Couldn't load that video: \(error.localizedDescription)"
                }
            }
        }
        .photosPicker(isPresented: $showingScreenshots, selection: $screenshotItems, maxSelectionCount: 10, matching: .images)
        .onChange(of: screenshotItems) { _, items in
            guard !items.isEmpty else { return }
            isImporting = true
            Task {
                defer { isImporting = false; screenshotItems = [] }
                var names: [String] = []
                for item in items {
                    if let data = try? await item.loadTransferable(type: Data.self),
                       let name = try? SwingStorage.store(imageData: data) {
                        names.append(name)
                    }
                }
                guard !names.isEmpty else { errorMessage = "Couldn't load those screenshots."; return }
                let swing = SwingVideo(source: .photos)
                swing.imageFileNames = names
                context.insert(swing)
                try? context.save()
                openSwing = swing
            }
        }
        .fileImporter(isPresented: $showingFiles, allowedContentTypes: [.movie]) { result in
            do {
                let url = try result.get()
                let accessed = url.startAccessingSecurityScopedResource()
                defer { if accessed { url.stopAccessingSecurityScopedResource() } }
                addVideo(from: url, source: .files, move: false)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
        .sheet(isPresented: $showingLink) { AddSwingLinkView() }
        .alert("Import failed", isPresented: Binding(get: { errorMessage != nil }, set: { if !$0 { errorMessage = nil } })) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(errorMessage ?? "")
        }
    }

    private func addVideo(from url: URL, source: SwingSource, move: Bool) {
        do {
            let name = try SwingStorage.store(videoAt: url, move: move)
            let swing = SwingVideo(source: source)
            swing.videoFileName = name
            context.insert(swing)
            try? context.save()
            openSwing = swing
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct SwingRow: View {
    let swing: SwingVideo

    var body: some View {
        HStack(spacing: 12) {
            SwingThumbnail(swing: swing)
                .frame(width: 56, height: 72)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    Text(swing.title).font(.headline)
                    if swing.isFavorite { Image(systemName: "star.fill").foregroundStyle(.yellow).font(.caption) }
                }
                Text(swing.date.formatted(date: .abbreviated, time: .shortened))
                    .font(.caption).foregroundStyle(.secondary)
                HStack(spacing: 6) {
                    Text(swing.sourceApp ?? swing.source.title)
                    if !swing.imageFileNames.isEmpty { Text("· \(swing.imageFileNames.count) still\(swing.imageFileNames.count == 1 ? "" : "s")") }
                    if !swing.analysis.isEmpty { Text("· analysed") }
                    if let lesson = swing.lesson { Text("· \(lesson.title)") }
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
        }
    }
}

struct SwingThumbnail: View {
    let swing: SwingVideo
    @State private var image: UIImage?

    var body: some View {
        ZStack {
            Color.secondary.opacity(0.15)
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image(systemName: swing.hasMedia ? "video" : "link")
                    .foregroundStyle(.secondary)
            }
        }
        .task(id: swing.videoFileName ?? swing.imageFileNames.first) {
            if let name = swing.videoFileName {
                image = await SwingStorage.thumbnail(for: name)
            } else if let first = swing.imageFileNames.first {
                image = await SwingStorage.imageThumbnail(named: first)
            }
        }
    }
}
