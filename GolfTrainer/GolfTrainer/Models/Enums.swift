import SwiftUI

enum PracticeCategory: String, CaseIterable, Identifiable, Codable {
    case range
    case shortGame
    case putting

    var id: String { rawValue }

    var title: String {
        switch self {
        case .range: return "Range"
        case .shortGame: return "Short Game"
        case .putting: return "Putting"
        }
    }

    var systemImage: String {
        switch self {
        case .range: return "figure.golf"
        case .shortGame: return "flag.fill"
        case .putting: return "target"
        }
    }

    var color: Color {
        switch self {
        case .range: return .green
        case .shortGame: return .orange
        case .putting: return .blue
        }
    }
}

/// How a drill is scored.
enum DrillMetric: String, CaseIterable, Identifiable, Codable {
    /// Successes out of attempts (e.g. 8 of 12 putts holed).
    case makes
    /// A points score where higher is better.
    case points
    /// A stroke count where lower is better (e.g. "Par 18").
    case strokes
    /// Average distance from the target in feet, where lower is better.
    case proximity

    var id: String { rawValue }

    var title: String {
        switch self {
        case .makes: return "Makes / Attempts"
        case .points: return "Points (higher is better)"
        case .strokes: return "Strokes (lower is better)"
        case .proximity: return "Avg. proximity in ft (lower is better)"
        }
    }

    var shortTitle: String {
        switch self {
        case .makes: return "Make %"
        case .points: return "Points"
        case .strokes: return "Strokes"
        case .proximity: return "Avg ft"
        }
    }

    var higherIsBetter: Bool {
        switch self {
        case .makes, .points: return true
        case .strokes, .proximity: return false
        }
    }
}

enum RoundSource: String, Codable {
    case manual
    case grint

    var title: String {
        switch self {
        case .manual: return "Manual"
        case .grint: return "TheGrint"
        }
    }
}
