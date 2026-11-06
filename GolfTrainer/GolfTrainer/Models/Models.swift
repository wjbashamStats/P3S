import Foundation
import SwiftData

@Model
final class PracticeSession {
    var date: Date = Date.now
    var categoryRaw: String = PracticeCategory.range.rawValue
    var durationMinutes: Int = 0
    /// Range sessions only (optional).
    var ballsHit: Int?
    var location: String = ""
    var notes: String = ""
    /// 1–5: how well the session went, in your own judgment.
    var rating: Int = 3

    @Relationship(deleteRule: .cascade, inverse: \DrillResult.session)
    var drills: [DrillResult] = []

    @Relationship(deleteRule: .nullify, inverse: \SwingVideo.session)
    var swings: [SwingVideo] = []

    init(date: Date = .now, category: PracticeCategory) {
        self.date = date
        self.categoryRaw = category.rawValue
    }

    var category: PracticeCategory {
        get { PracticeCategory(rawValue: categoryRaw) ?? .range }
        set { categoryRaw = newValue.rawValue }
    }

    var sortedDrills: [DrillResult] {
        drills.sorted { $0.order < $1.order }
    }
}

@Model
final class DrillResult {
    var drillName: String = ""
    var metricRaw: String = DrillMetric.makes.rawValue
    var attempts: Int = 0
    var successes: Int = 0
    /// Used for points / strokes / proximity drills.
    var value: Double = 0
    var notes: String = ""
    var order: Int = 0
    var session: PracticeSession?

    init(drillName: String, metric: DrillMetric, attempts: Int, successes: Int,
         value: Double, notes: String = "", order: Int = 0) {
        self.drillName = drillName
        self.metricRaw = metric.rawValue
        self.attempts = attempts
        self.successes = successes
        self.value = value
        self.notes = notes
        self.order = order
    }

    var metric: DrillMetric {
        get { DrillMetric(rawValue: metricRaw) ?? .makes }
        set { metricRaw = newValue.rawValue }
    }

    /// The number that gets charted: make % for `makes`, otherwise `value`.
    var chartValue: Double? {
        DrillScoring.chartValue(metric: metric, attempts: attempts, successes: successes, value: value)
    }

    var summary: String {
        DrillScoring.summary(metric: metric, attempts: attempts, successes: successes, value: value)
    }
}

@Model
final class Round {
    var date: Date = Date.now
    var courseName: String = ""
    var holes: Int = 18
    var par: Int = 72
    var score: Int = 0
    var putts: Int?
    var fairwaysHit: Int?
    var fairwaysPossible: Int?
    var greensInRegulation: Int?
    var upAndDownsMade: Int?
    var upAndDownAttempts: Int?
    var penalties: Int?
    var notes: String = ""
    var sourceRaw: String = RoundSource.manual.rawValue
    /// Used to avoid importing the same round from TheGrint twice.
    var importKey: String?

    init(date: Date = .now, courseName: String = "", holes: Int = 18, par: Int = 72, score: Int = 0) {
        self.date = date
        self.courseName = courseName
        self.holes = holes
        self.par = par
        self.score = score
    }

    var source: RoundSource {
        get { RoundSource(rawValue: sourceRaw) ?? .manual }
        set { sourceRaw = newValue.rawValue }
    }

    var toPar: Int { score - par }

    var toParText: String {
        toPar == 0 ? "E" : (toPar > 0 ? "+\(toPar)" : "\(toPar)")
    }

    var girPercent: Double? {
        guard let g = greensInRegulation, holes > 0 else { return nil }
        return Double(g) / Double(holes)
    }

    var fairwayPercent: Double? {
        guard let hit = fairwaysHit, let possible = fairwaysPossible, possible > 0 else { return nil }
        return Double(hit) / Double(possible)
    }

    var upAndDownPercent: Double? {
        guard let made = upAndDownsMade, let att = upAndDownAttempts, att > 0 else { return nil }
        return Double(made) / Double(att)
    }
}

@Model
final class HandicapEntry {
    var date: Date = Date.now
    var index: Double = 0
    var sourceRaw: String = RoundSource.manual.rawValue

    init(date: Date = .now, index: Double, source: RoundSource = .manual) {
        self.date = date
        self.index = index
        self.sourceRaw = source.rawValue
    }
}

/// Pure scoring helpers, so they can be unit tested without SwiftData.
enum DrillScoring {
    static func chartValue(metric: DrillMetric, attempts: Int, successes: Int, value: Double) -> Double? {
        switch metric {
        case .makes:
            guard attempts > 0 else { return nil }
            return Double(successes) / Double(attempts) * 100
        case .points, .strokes, .proximity:
            return value
        }
    }

    static func summary(metric: DrillMetric, attempts: Int, successes: Int, value: Double) -> String {
        switch metric {
        case .makes:
            guard attempts > 0 else { return "0/0" }
            let pct = Int((Double(successes) / Double(attempts) * 100).rounded())
            return "\(successes)/\(attempts) (\(pct)%)"
        case .points:
            return "\(value.formatted(.number.precision(.fractionLength(0...1)))) pts"
        case .strokes:
            return "\(value.formatted(.number.precision(.fractionLength(0...1)))) strokes"
        case .proximity:
            return "\(value.formatted(.number.precision(.fractionLength(0...1)))) ft avg"
        }
    }
}
