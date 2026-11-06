import Foundation

/// Key positions you can mark in a swing video, then export as frames.
enum SwingPosition: String, CaseIterable, Identifiable, Codable {
    case address, takeaway, top, transition, impact, finish
    var id: String { rawValue }
    var title: String {
        switch self {
        case .address: return "Address"
        case .takeaway: return "Takeaway"
        case .top: return "Top"
        case .transition: return "Transition"
        case .impact: return "Impact"
        case .finish: return "Finish"
        }
    }
}

struct SwingCheckpoint: Codable, Equatable, Identifiable {
    var position: SwingPosition
    /// Seconds into the video.
    var time: Double
    var id: SwingPosition { position }
}

/// Builds the text sent along with frames to a swing-analysis chat, so it knows
/// what it's looking at and what you're working on.
struct SwingContext {
    var club: String
    var angle: String
    var date: Date
    var handicapIndex: Double?
    var notes: String
    var lessonFocus: String?
    var lessonFeedback: String?
    var checkpoints: [SwingCheckpoint]
    var frameRate: Double?
    var includesKeyPositionSheet: Bool

    func text() -> String {
        var lines: [String] = ["Golf swing for analysis."]
        var details: [String] = []
        if !club.isEmpty { details.append("Club: \(club)") }
        if !angle.isEmpty { details.append("Camera: \(angle)") }
        let df = DateFormatter()
        df.dateStyle = .medium
        df.timeStyle = .none
        df.locale = Locale(identifier: "en_US")
        details.append("Recorded: \(df.string(from: date))")
        if let handicapIndex {
            let s = String(format: "%.1f", abs(handicapIndex))
            details.append("Handicap index: \(handicapIndex < 0 ? "+" + s : s)")
        }
        if let frameRate, frameRate > 0 { details.append("Video: \(Int(frameRate.rounded())) fps") }
        lines.append(details.joined(separator: " · "))

        if includesKeyPositionSheet && !checkpoints.isEmpty {
            let order = checkpoints.sorted { $0.time < $1.time }.map(\.position.title).joined(separator: " → ")
            lines.append("The key positions image shows, left to right and top to bottom: \(order).")
        }
        if let focus = lessonFocus, !focus.isEmpty { lines.append("Current lesson focus: \(focus)") }
        if let fb = lessonFeedback, !fb.isEmpty { lines.append("Coach feedback so far: \(fb)") }
        if !notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            lines.append("What I'm working on / notes: \(notes.trimmingCharacters(in: .whitespacesAndNewlines))")
        }
        lines.append("Please point out the one or two biggest issues, what's causing them, and a drill for each.")
        return lines.joined(separator: "\n")
    }
}

enum FrameGrid {
    /// Columns and rows for a sheet of `count` portrait frames.
    static func layout(count: Int) -> (columns: Int, rows: Int) {
        guard count > 0 else { return (0, 0) }
        let columns = count <= 3 ? count : (count == 4 ? 2 : 3)
        return (columns, Int((Double(count) / Double(columns)).rounded(.up)))
    }
}
