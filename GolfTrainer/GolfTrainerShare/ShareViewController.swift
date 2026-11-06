import UIKit
import SwiftUI
import UniformTypeIdentifiers
import Observation

/// The share extension's entry point. It shows a small form, then drops the video
/// or link into the shared inbox for the app to pick up the next time it opens.
@objc(ShareViewController)
final class ShareViewController: UIViewController {
    private let model = ShareModel()

    override func viewDidLoad() {
        super.viewDidLoad()
        model.onFinish = { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        }
        model.onCancel = { [weak self] in
            self?.extensionContext?.cancelRequest(withError: NSError(domain: NSCocoaErrorDomain,
                                                                      code: NSUserCancelledError))
        }
        let host = UIHostingController(rootView: ShareFormView(model: model))
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)

        model.load(from: extensionContext?.inputItems as? [NSExtensionItem] ?? [])
    }
}

@Observable
final class ShareModel {
    enum State: Equatable { case loading, ready, nothingUsable, failed(String) }

    var state: State = .loading
    var videoURL: URL?
    var link: URL?
    var club = ""
    var angle: CameraAngle = .downTheLine
    var sourceApp = ""
    var note = ""
    var isSaving = false

    @ObservationIgnored var onFinish: () -> Void = {}
    @ObservationIgnored var onCancel: () -> Void = {}

    func load(from items: [NSExtensionItem]) {
        let providers = items.flatMap { $0.attachments ?? [] }
        let group = DispatchGroup()

        if let movie = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.movie.identifier) }) {
            group.enter()
            movie.loadFileRepresentation(forTypeIdentifier: UTType.movie.identifier) { url, _ in
                defer { group.leave() }
                // The file is only valid inside this callback, so copy it now.
                guard let url else { return }
                let ext = url.pathExtension.isEmpty ? "mov" : url.pathExtension
                let copy = FileManager.default.temporaryDirectory
                    .appendingPathComponent(UUID().uuidString).appendingPathExtension(ext)
                if (try? FileManager.default.copyItem(at: url, to: copy)) != nil {
                    DispatchQueue.main.async { self.videoURL = copy }
                }
            }
        }

        if let urlProvider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.url.identifier) }) {
            group.enter()
            urlProvider.loadItem(forTypeIdentifier: UTType.url.identifier) { item, _ in
                defer { group.leave() }
                if let url = item as? URL, !url.isFileURL {
                    DispatchQueue.main.async { self.link = url }
                }
            }
        } else if let textProvider = providers.first(where: { $0.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) }) {
            // Many apps share "Check out my lesson: https://…" as plain text.
            group.enter()
            textProvider.loadItem(forTypeIdentifier: UTType.plainText.identifier) { item, _ in
                defer { group.leave() }
                if let text = item as? String, let url = Self.firstLink(in: text) {
                    DispatchQueue.main.async { self.link = url }
                }
            }
        }

        group.notify(queue: .main) {
            self.state = (self.videoURL == nil && self.link == nil) ? .nothingUsable : .ready
        }
    }

    static func firstLink(in text: String) -> URL? {
        let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue)
        let range = NSRange(text.startIndex..., in: text)
        return detector?.firstMatch(in: text, options: [], range: range)?.url
    }

    func save() {
        guard let inbox = SharedInbox.shared else {
            state = .failed("Golf Trainer's App Group isn't set up, so the extension can't hand files to the app. See the README.")
            return
        }
        isSaving = true
        let item = SharedSwingItem(link: link?.absoluteString,
                                   club: club.isEmpty ? nil : club,
                                   angle: angle.rawValue,
                                   note: note,
                                   sourceApp: sourceApp.isEmpty ? nil : sourceApp)
        let video = videoURL
        DispatchQueue.global(qos: .userInitiated).async {
            do {
                try inbox.add(item, copyingVideoFrom: video)
                if let video { try? FileManager.default.removeItem(at: video) }
                DispatchQueue.main.async { self.onFinish() }
            } catch {
                DispatchQueue.main.async {
                    self.isSaving = false
                    self.state = .failed(error.localizedDescription)
                }
            }
        }
    }
}

struct ShareFormView: View {
    @Bindable var model: ShareModel

    var body: some View {
        NavigationStack {
            Form {
                switch model.state {
                case .loading:
                    HStack { ProgressView(); Text("Preparing…") }
                case .nothingUsable:
                    Text("There's no video or link here that Golf Trainer can save.")
                case .failed(let message):
                    Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.red)
                case .ready:
                    Section {
                        if model.videoURL != nil { Label("Swing video", systemImage: "video.fill") }
                        if let link = model.link {
                            Label(link.absoluteString, systemImage: "link").lineLimit(2)
                        }
                    }
                    Section {
                        Picker("From", selection: $model.sourceApp) {
                            Text("Not set").tag("")
                            ForEach(CoachApps.suggestions, id: \.self) { Text($0).tag($0) }
                        }
                        Picker("Club", selection: $model.club) {
                            Text("None").tag("")
                            ForEach(Clubs.all, id: \.self) { Text($0).tag($0) }
                        }
                        Picker("Camera angle", selection: $model.angle) {
                            ForEach(CameraAngle.allCases) { Text($0.title).tag($0) }
                        }
                        TextField("Note (e.g. coach feedback)", text: $model.note, axis: .vertical)
                    }
                }
            }
            .navigationTitle("Save to Golf Trainer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { model.onCancel() } }
                ToolbarItem(placement: .confirmationAction) {
                    if model.isSaving {
                        ProgressView()
                    } else {
                        Button("Save") { model.save() }
                            .disabled(model.state != .ready)
                    }
                }
            }
        }
    }
}
