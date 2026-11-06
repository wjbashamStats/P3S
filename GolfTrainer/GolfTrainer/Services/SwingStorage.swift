import Foundation
import SwiftData
import AVFoundation
import UIKit

/// Handles swing video files in Documents/Swings and their cached thumbnails.
enum SwingStorage {
    static var directory: URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("Swings", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static var thumbnailDirectory: URL {
        let dir = directory.appendingPathComponent("Thumbnails", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    static func videoURL(named name: String) -> URL {
        directory.appendingPathComponent(name)
    }

    /// Copies (or moves) a video into app storage and returns its new file name.
    static func store(videoAt source: URL, move: Bool = false) throws -> String {
        let ext = source.pathExtension.isEmpty ? "mov" : source.pathExtension.lowercased()
        let name = "\(UUID().uuidString).\(ext)"
        let dest = videoURL(named: name)
        if move {
            try FileManager.default.moveItem(at: source, to: dest)
        } else {
            try FileManager.default.copyItem(at: source, to: dest)
        }
        return name
    }

    /// Deletes the swing's video and thumbnail, then the record itself.
    static func delete(_ swing: SwingVideo, in context: ModelContext) {
        if let name = swing.videoFileName {
            try? FileManager.default.removeItem(at: videoURL(named: name))
            try? FileManager.default.removeItem(at: thumbnailURL(for: name))
        }
        context.delete(swing)
    }

    static func thumbnailURL(for videoName: String) -> URL {
        thumbnailDirectory.appendingPathComponent((videoName as NSString).deletingPathExtension + ".jpg")
    }

    /// Returns a cached thumbnail, making one from the video first if needed.
    static func thumbnail(for videoName: String) async -> UIImage? {
        let cached = thumbnailURL(for: videoName)
        if let data = try? Data(contentsOf: cached), let image = UIImage(data: data) { return image }

        let asset = AVURLAsset(url: videoURL(named: videoName))
        let generator = AVAssetImageGenerator(asset: asset)
        generator.appliesPreferredTrackTransform = true
        generator.maximumSize = CGSize(width: 400, height: 400)
        do {
            let (cgImage, _) = try await generator.image(at: CMTime(seconds: 0.5, preferredTimescale: 600))
            let image = UIImage(cgImage: cgImage)
            if let jpeg = image.jpegData(compressionQuality: 0.7) { try? jpeg.write(to: cached) }
            return image
        } catch {
            return nil
        }
    }

    /// Moves everything waiting in the share extension's inbox into SwiftData.
    /// Returns how many swings were added.
    @discardableResult
    static func importSharedInbox(into context: ModelContext, inbox: SharedInbox? = SharedInbox.shared) -> Int {
        guard let inbox else { return 0 }
        var count = 0
        for item in inbox.pending() {
            let swing = SwingVideo(date: item.date, club: item.club ?? "",
                                   angle: item.angle.flatMap(CameraAngle.init(rawValue:)) ?? .downTheLine,
                                   source: .shared)
            if let video = inbox.videoURL(for: item), FileManager.default.fileExists(atPath: video.path) {
                guard let name = try? store(videoAt: video, move: true) else { continue }
                swing.videoFileName = name
            } else if item.link == nil {
                inbox.remove(item) // nothing usable
                continue
            }
            swing.externalLink = item.link
            if item.videoFileName == nil { swing.source = .link }
            swing.sourceApp = item.sourceApp
            swing.notes = item.note
            swing.needsReview = true
            context.insert(swing)
            inbox.remove(item)
            count += 1
        }
        if count > 0 { try? context.save() }
        return count
    }
}
