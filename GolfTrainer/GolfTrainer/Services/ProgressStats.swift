import Foundation

struct PracticeEntry {
    var date: Date
    var category: PracticeCategory
    var minutes: Int
}

struct WeeklyMinutes: Identifiable, Equatable {
    var weekStart: Date
    var category: PracticeCategory
    var minutes: Int
    var id: String { "\(weekStart.timeIntervalSince1970)-\(category.rawValue)" }
}

struct DatedValue: Identifiable, Equatable {
    var date: Date
    var value: Double
    var id: Double { date.timeIntervalSince1970 + value / 1_000_000 }
}

enum Trend: Equatable {
    case improving, declining, flat, insufficientData
}

/// Pure functions behind the Progress tab. They take plain values, so they are easy to test.
enum ProgressStats {
    /// Practice minutes per week and category for the last `weeks` weeks (oldest first).
    /// Weeks with no practice get zero-minute entries, so charts keep a steady x-axis.
    static func weeklyMinutes(_ entries: [PracticeEntry], weeks: Int, now: Date = .now,
                              calendar: Calendar = .current) -> [WeeklyMinutes] {
        guard weeks > 0, let thisWeek = calendar.dateInterval(of: .weekOfYear, for: now)?.start else { return [] }
        let starts: [Date] = (0..<weeks).reversed().compactMap {
            calendar.date(byAdding: .weekOfYear, value: -$0, to: thisWeek)
        }
        var totals: [Date: [PracticeCategory: Int]] = [:]
        for e in entries {
            guard let start = calendar.dateInterval(of: .weekOfYear, for: e.date)?.start else { continue }
            totals[start, default: [:]][e.category, default: 0] += e.minutes
        }
        return starts.flatMap { start in
            PracticeCategory.allCases.map { cat in
                WeeklyMinutes(weekStart: start, category: cat, minutes: totals[start]?[cat] ?? 0)
            }
        }
    }

    /// The number of consecutive days with practice, ending today (or yesterday, if you haven't practiced yet today).
    static func streakDays(_ dates: [Date], now: Date = .now, calendar: Calendar = .current) -> Int {
        let days = Set(dates.map { calendar.startOfDay(for: $0) })
        var cursor = calendar.startOfDay(for: now)
        if !days.contains(cursor) {
            guard let yesterday = calendar.date(byAdding: .day, value: -1, to: cursor), days.contains(yesterday) else { return 0 }
            cursor = yesterday
        }
        var count = 0
        while days.contains(cursor) {
            count += 1
            guard let prev = calendar.date(byAdding: .day, value: -1, to: cursor) else { break }
            cursor = prev
        }
        return count
    }

    static func average(_ values: [Double]) -> Double? {
        values.isEmpty ? nil : values.reduce(0, +) / Double(values.count)
    }

    /// Compares the average of the most recent `window` values with the `window` before that.
    /// `values` must be in chronological order (oldest first).
    static func trend(_ values: [Double], window: Int = 5, higherIsBetter: Bool,
                      tolerance: Double = 0.02) -> Trend {
        guard window > 0, values.count >= 2 else { return .insufficientData }
        let w = min(window, values.count / 2)
        guard w > 0,
              let recent = average(Array(values.suffix(w))),
              let previous = average(Array(values.dropLast(w).suffix(w))) else { return .insufficientData }
        let scale = max(abs(previous), 1)
        let delta = (recent - previous) / scale
        if abs(delta) <= tolerance { return .flat }
        return (delta > 0) == higherIsBetter ? .improving : .declining
    }

    /// Simple moving average, used to smooth chart lines.
    static func movingAverage(_ points: [DatedValue], window: Int) -> [DatedValue] {
        guard window > 1 else { return points }
        return points.indices.map { i in
            let slice = points[max(0, i - window + 1)...i].map(\.value)
            return DatedValue(date: points[i].date, value: slice.reduce(0, +) / Double(slice.count))
        }
    }

    /// Practice minutes per category within the last `days` days.
    static func minutesByCategory(_ entries: [PracticeEntry], days: Int, now: Date = .now,
                                  calendar: Calendar = .current) -> [PracticeCategory: Int] {
        guard let cutoff = calendar.date(byAdding: .day, value: -days, to: now) else { return [:] }
        var out: [PracticeCategory: Int] = [:]
        for e in entries where e.date >= cutoff { out[e.category, default: 0] += e.minutes }
        return out
    }
}
