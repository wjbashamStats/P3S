import Foundation

/// One item handed to the app by the share extension (a video file, a link, or both).
struct SharedSwingItem: Codable, Equatable, Identifiable {
    var id: UUID = UUID()
    var date: Date = Date()
    /// File name of the video inside the inbox folder, if a video was shared.
    var videoFileName: String?
    /// A link, e.g. to a lesson in a coaching app.
    var link: String?
    var club: String?
    var angle: String?
    var note: String = ""
    var sourceApp: String?
}

/// A folder in the App Group container, used by the share extension and the app.
///
/// The extension copies the video into the folder first and writes `<id>.json` last,
/// so the app only ever sees complete items. The app imports pending items when it
/// becomes active, then removes them.
struct SharedInbox {
    static let appGroupID = "group.com.example.golftrainer"

    /// The folder lives in the App Group container. If App Groups aren't configured, this is nil.
    static var shared: SharedInbox? {
        guard let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupID) else {
            return nil
        }
        return SharedInbox(directory: container.appendingPathComponent("Inbox", isDirectory: true))
    }

    let directory: URL
    private var fm: FileManager { .default }

    init(directory: URL) {
        self.directory = directory
    }

    /// Copies `videoURL` (if any) into the inbox, then writes the manifest.
    @discardableResult
    func add(_ item: SharedSwingItem, copyingVideoFrom videoURL: URL?) throws -> SharedSwingItem {
        try fm.createDirectory(at: directory, withIntermediateDirectories: true)
        var item = item
        if let videoURL {
            let ext = videoURL.pathExtension.isEmpty ? "mov" : videoURL.pathExtension
            let name = "\(item.id.uuidString).\(ext.lowercased())"
            let dest = directory.appendingPathComponent(name)
            if fm.fileExists(atPath: dest.path) { try fm.removeItem(at: dest) }
            try fm.copyItem(at: videoURL, to: dest)
            item.videoFileName = name
        }
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(item)
        try data.write(to: manifestURL(for: item.id), options: .atomic)
        return item
    }

    /// Complete items waiting to be imported, oldest first.
    func pending() -> [SharedSwingItem] {
        guard let files = try? fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) else { return [] }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return files
            .filter { $0.pathExtension == "json" }
            .compactMap { try? decoder.decode(SharedSwingItem.self, from: Data(contentsOf: $0)) }
            .sorted { $0.date < $1.date }
    }

    func videoURL(for item: SharedSwingItem) -> URL? {
        item.videoFileName.map { directory.appendingPathComponent($0) }
    }

    /// Removes the manifest and any video still in the inbox.
    func remove(_ item: SharedSwingItem) {
        if let video = videoURL(for: item) { try? fm.removeItem(at: video) }
        try? fm.removeItem(at: manifestURL(for: item.id))
    }

    private func manifestURL(for id: UUID) -> URL {
        directory.appendingPathComponent("\(id.uuidString).json")
    }
}
