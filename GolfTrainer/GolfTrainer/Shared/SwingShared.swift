import Foundation

// Shared by the app and the share extension.

enum CameraAngle: String, CaseIterable, Identifiable, Codable {
    case downTheLine, faceOn, other
    var id: String { rawValue }
    var title: String {
        switch self {
        case .downTheLine: return "Down the line"
        case .faceOn: return "Face on"
        case .other: return "Other"
        }
    }
    var shortTitle: String {
        switch self {
        case .downTheLine: return "DTL"
        case .faceOn: return "FO"
        case .other: return "—"
        }
    }
}

enum Clubs {
    static let all = ["Driver", "3 Wood", "5 Wood", "Hybrid", "3 Iron", "4 Iron", "5 Iron", "6 Iron",
                      "7 Iron", "8 Iron", "9 Iron", "PW", "GW", "SW", "LW", "Putter"]
}

/// Coaching apps people commonly share from. These are suggestions only; any name can be typed in.
enum CoachApps {
    static let suggestions = ["V1 Golf", "CoachNow", "Skillest", "Sportsbox AI", "Hudl Technique", "Other"]
}
