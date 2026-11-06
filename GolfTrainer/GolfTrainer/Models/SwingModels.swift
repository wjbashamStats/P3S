import Foundation
import SwiftData
import CoreGraphics

enum SwingSource: String, Codable {
    case camera, photos, files, shared, link

    var title: String {
        switch self {
        case .camera: return "Recorded"
        case .photos: return "Photos"
        case .files: return "Files"
        case .shared: return "Shared"
        case .link: return "Link"
        }
    }
}

/// A straight line drawn over a swing video (shaft plane, head position, spine angle…).
/// Coordinates are normalised (0…1) within the video frame, so they survive resizing.
struct SwingLine: Codable, Equatable, Identifiable {
    var id: UUID = UUID()
    var start: CGPoint
    var end: CGPoint
    var colorIndex: Int = 0

    /// The angle from horizontal in degrees (0…180) in pixel space.
    /// Needs the video's aspect ratio (width / height), since the coordinates are normalised.
    func angleDegrees(aspectRatio: CGFloat) -> Double {
        let dx = Double((end.x - start.x) * aspectRatio)
        let dy = Double(start.y - end.y) // flip y, so "up" is positive
        var deg = atan2(dy, dx) * 180 / .pi
        if deg < 0 { deg += 180 }
        return deg
    }
}

@Model
final class SwingVideo {
    var date: Date = Date.now
    var club: String = ""
    var angleRaw: String = CameraAngle.downTheLine.rawValue
    /// File in Documents/Swings, if the swing has a local video.
    var videoFileName: String?
    /// A link to the swing or lesson in a coaching app, if it has one.
    var externalLink: String?
    var sourceRaw: String = SwingSource.camera.rawValue
    var sourceApp: String?
    var notes: String = ""
    var isFavorite: Bool = false
    /// Set for items that arrived through the share sheet and haven't been reviewed yet.
    var needsReview: Bool = false
    var linesData: Data?

    var lesson: Lesson?
    var session: PracticeSession?

    init(date: Date = .now, club: String = "", angle: CameraAngle = .downTheLine, source: SwingSource) {
        self.date = date
        self.club = club
        self.angleRaw = angle.rawValue
        self.sourceRaw = source.rawValue
    }

    var angle: CameraAngle {
        get { CameraAngle(rawValue: angleRaw) ?? .other }
        set { angleRaw = newValue.rawValue }
    }

    var source: SwingSource {
        get { SwingSource(rawValue: sourceRaw) ?? .camera }
        set { sourceRaw = newValue.rawValue }
    }

    var lines: [SwingLine] {
        get { linesData.flatMap { try? JSONDecoder().decode([SwingLine].self, from: $0) } ?? [] }
        set { linesData = newValue.isEmpty ? nil : try? JSONEncoder().encode(newValue) }
    }

    var videoURL: URL? { videoFileName.map(SwingStorage.videoURL(named:)) }
    var linkURL: URL? { externalLink.flatMap(URL.init(string:)) }

    var title: String {
        let parts = [club.isEmpty ? nil : club, angle == .other ? nil : angle.title].compactMap { $0 }
        return parts.isEmpty ? "Swing" : parts.joined(separator: " · ")
    }
}

@Model
final class Lesson {
    var date: Date = Date.now
    var coachName: String = ""
    /// For example "In person" or the name of the coaching app.
    var format: String = "In person"
    var focus: String = ""
    var feedback: String = ""
    var assignedDrills: String = ""
    var link: String?
    var nextLessonDate: Date?

    @Relationship(deleteRule: .nullify, inverse: \SwingVideo.lesson)
    var swings: [SwingVideo] = []

    init(date: Date = .now, coachName: String = "") {
        self.date = date
        self.coachName = coachName
    }

    var title: String {
        focus.isEmpty ? (coachName.isEmpty ? "Lesson" : "Lesson with \(coachName)") : focus
    }
}
