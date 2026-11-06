import SwiftUI
import SwiftData
import Charts

enum ProgressScope: String, CaseIterable, Identifiable {
    case overall, range, shortGame, putting, rounds
    var id: String { rawValue }
    var title: String {
        switch self {
        case .overall: return "Overall"
        case .range: return "Range"
        case .shortGame: return "Short"
        case .putting: return "Putting"
        case .rounds: return "Rounds"
        }
    }
    var category: PracticeCategory? {
        switch self {
        case .range: return .range
        case .shortGame: return .shortGame
        case .putting: return .putting
        default: return nil
        }
    }
}

struct ProgressDashboardView: View {
    @Query(sort: \PracticeSession.date) private var sessions: [PracticeSession]
    @Query(sort: \Round.date) private var rounds: [Round]
    @Query(sort: \HandicapEntry.date) private var handicaps: [HandicapEntry]
    @State private var scope: ProgressScope = .overall

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Picker("Scope", selection: $scope) {
                        ForEach(ProgressScope.allCases) { Text($0.title).tag($0) }
                    }
                    .pickerStyle(.segmented)

                    switch scope {
                    case .overall:
                        OverallProgressView(sessions: sessions, rounds: rounds, handicaps: handicaps)
                    case .rounds:
                        RoundsProgressView(rounds: rounds, handicaps: handicaps)
                    case .range, .shortGame, .putting:
                        if let category = scope.category {
                            CategoryProgressView(category: category,
                                                 sessions: sessions.filter { $0.category == category })
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Progress")
        }
    }
}

// MARK: - Overall

struct OverallProgressView: View {
    let sessions: [PracticeSession]
    let rounds: [Round]
    let handicaps: [HandicapEntry]

    private var entries: [PracticeEntry] {
        sessions.map { PracticeEntry(date: $0.date, category: $0.category, minutes: $0.durationMinutes) }
    }

    var body: some View {
        let last30 = ProgressStats.minutesByCategory(entries, days: 30)
        let total30 = last30.values.reduce(0, +)
        let streak = ProgressStats.streakDays(sessions.map(\.date))
        let scores18 = rounds.filter { $0.holes == 18 }.map { Double($0.score) }

        VStack(alignment: .leading, spacing: 20) {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                StatTile(title: "Handicap", value: handicaps.last.map { formatIndex($0.index) } ?? "—",
                         caption: handicapCaption)
                StatTile(title: "Practice (30 days)", value: hoursText(total30),
                         caption: "\(sessions.filter { $0.date > .now.addingTimeInterval(-30 * 86_400) }.count) sessions")
                StatTile(title: "Streak", value: "\(streak) day\(streak == 1 ? "" : "s")", tint: .orange)
                StatTile(title: "Scoring avg (last 5)",
                         value: ProgressStats.average(Array(scores18.suffix(5)))
                            .map { $0.formatted(.number.precision(.fractionLength(1))) } ?? "—",
                         caption: "18-hole rounds", tint: .blue)
            }

            ChartCard(title: "Practice minutes per week") {
                Chart(ProgressStats.weeklyMinutes(entries, weeks: 12)) { item in
                    BarMark(x: .value("Week", item.weekStart, unit: .weekOfYear),
                            y: .value("Minutes", item.minutes))
                        .foregroundStyle(by: .value("Type", item.category.title))
                }
                .chartForegroundStyleScale([
                    PracticeCategory.range.title: PracticeCategory.range.color,
                    PracticeCategory.shortGame.title: PracticeCategory.shortGame.color,
                    PracticeCategory.putting.title: PracticeCategory.putting.color,
                ])
                .frame(height: 200)
            }

            ChartCard(title: "Practice mix (30 days)") {
                if total30 == 0 {
                    EmptyChartText("Log a session to see your mix.")
                } else {
                    Chart(PracticeCategory.allCases) { cat in
                        SectorMark(angle: .value("Minutes", last30[cat] ?? 0), innerRadius: .ratio(0.6))
                            .foregroundStyle(cat.color)
                            .annotation(position: .overlay) {
                                if let m = last30[cat], m > 0 {
                                    Text("\(Int((Double(m) / Double(total30) * 100).rounded()))%")
                                        .font(.caption.bold()).foregroundStyle(.white)
                                }
                            }
                    }
                    .frame(height: 180)
                    HStack(spacing: 16) {
                        ForEach(PracticeCategory.allCases) { cat in
                            Label("\(cat.title) \(last30[cat] ?? 0)m", systemImage: "circle.fill")
                                .font(.caption)
                                .foregroundStyle(cat.color)
                        }
                    }
                }
            }

            ChartCard(title: "Skill trends") {
                VStack(spacing: 10) {
                    ForEach(PracticeCategory.allCases) { cat in
                        HStack {
                            Label(cat.title, systemImage: cat.systemImage).foregroundStyle(cat.color)
                            Spacer()
                            TrendBadge(trend: makeRateTrend(for: cat)).font(.subheadline)
                        }
                    }
                    HStack {
                        Label("Scoring", systemImage: "flag.2.crossed").foregroundStyle(.blue)
                        Spacer()
                        TrendBadge(trend: ProgressStats.trend(scores18, higherIsBetter: false)).font(.subheadline)
                    }
                }
                Text("Practice trends compare make % on make/miss drills over your last 5 sessions with the 5 before.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var handicapCaption: String? {
        guard handicaps.count >= 2, let first = handicaps.first, let last = handicaps.last else { return nil }
        let change = last.index - first.index
        let sign = change > 0 ? "+" : ""
        return "\(sign)\(change.formatted(.number.precision(.fractionLength(1)))) since \(first.date.formatted(.dateTime.month(.abbreviated).year()))"
    }

    /// The overall make % per session across all make/miss drills in a category.
    private func makeRateTrend(for category: PracticeCategory) -> Trend {
        let rates: [Double] = sessions.filter { $0.category == category }.compactMap { s in
            let makes = s.drills.filter { $0.metric == .makes }
            let attempts = makes.reduce(0) { $0 + $1.attempts }
            guard attempts > 0 else { return nil }
            return Double(makes.reduce(0) { $0 + $1.successes }) / Double(attempts)
        }
        return ProgressStats.trend(rates, higherIsBetter: true)
    }

    private func hoursText(_ minutes: Int) -> String {
        minutes < 60 ? "\(minutes)m" : "\(minutes / 60)h \(minutes % 60)m"
    }
}

// MARK: - Category

struct CategoryProgressView: View {
    let category: PracticeCategory
    let sessions: [PracticeSession]
    @State private var selectedDrill: String?

    private var drillNames: [String] {
        let used = Set(sessions.flatMap { $0.drills.map(\.drillName) })
        // Library order first, then custom drills alphabetically.
        let library = DrillLibrary.drills(for: category).map(\.name).filter(used.contains)
        let custom = used.subtracting(library).sorted()
        return library + custom
    }

    var body: some View {
        let names = drillNames
        let drill = selectedDrill.flatMap { names.contains($0) ? $0 : nil } ?? names.first

        VStack(alignment: .leading, spacing: 20) {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                StatTile(title: "Sessions", value: "\(sessions.count)", tint: category.color)
                StatTile(title: "Total time",
                         value: "\(sessions.reduce(0) { $0 + $1.durationMinutes } / 60)h",
                         tint: category.color)
                if category == .range {
                    StatTile(title: "Balls hit", value: "\(sessions.compactMap(\.ballsHit).reduce(0, +))",
                             tint: category.color)
                }
                StatTile(title: "Avg. rating",
                         value: ProgressStats.average(sessions.map { Double($0.rating) })
                            .map { $0.formatted(.number.precision(.fractionLength(1))) + "★" } ?? "—",
                         tint: .yellow)
            }

            if names.isEmpty {
                ChartCard(title: "Drills") {
                    EmptyChartText("Log \(category.title.lowercased()) drills to chart your progress.")
                }
            } else if let drill {
                Picker("Drill", selection: Binding(get: { drill }, set: { selectedDrill = $0 })) {
                    ForEach(names, id: \.self) { Text($0).tag($0) }
                }
                .pickerStyle(.menu)

                DrillProgressChart(drillName: drill, sessions: sessions, color: category.color)
            }
        }
    }
}

struct DrillProgressChart: View {
    let drillName: String
    let sessions: [PracticeSession]
    let color: Color

    var body: some View {
        let results: [(Date, DrillResult)] = sessions.flatMap { s in
            s.drills.filter { $0.drillName == drillName }.map { (s.date, $0) }
        }.sorted { $0.0 < $1.0 }
        let metric = results.last?.1.metric ?? .makes
        let points = results.compactMap { pair in pair.1.chartValue.map { DatedValue(date: pair.0, value: $0) } }
        let smoothed = ProgressStats.movingAverage(points, window: 3)
        let goal = DrillLibrary.template(named: drillName)?.goal

        ChartCard(title: "\(drillName): \(metric.shortTitle)") {
            if points.isEmpty {
                EmptyChartText("No scored results yet.")
            } else {
                Chart {
                    ForEach(points) { p in
                        PointMark(x: .value("Date", p.date), y: .value(metric.shortTitle, p.value))
                            .foregroundStyle(color.opacity(0.5))
                    }
                    ForEach(smoothed) { p in
                        LineMark(x: .value("Date", p.date), y: .value(metric.shortTitle, p.value))
                            .foregroundStyle(color)
                            .interpolationMethod(.catmullRom)
                    }
                    if let goal {
                        RuleMark(y: .value("Goal", goal))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                            .foregroundStyle(.secondary)
                            .annotation(position: .top, alignment: .leading) {
                                Text("Goal").font(.caption2).foregroundStyle(.secondary)
                            }
                    }
                }
                .chartYScale(domain: .automatic(includesZero: metric == .makes))
                .frame(height: 220)

                HStack {
                    if let best = metric.higherIsBetter ? points.map(\.value).max() : points.map(\.value).min() {
                        Text("Best: \(format(best, metric))")
                    }
                    Spacer()
                    TrendBadge(trend: ProgressStats.trend(points.map(\.value), higherIsBetter: metric.higherIsBetter))
                }
                .font(.subheadline)
                Text("Dots are single sessions; the line is a 3-session average.")
                    .font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    private func format(_ v: Double, _ metric: DrillMetric) -> String {
        switch metric {
        case .makes: return "\(Int(v.rounded()))%"
        case .points: return "\(v.formatted(.number.precision(.fractionLength(0...1)))) pts"
        case .strokes: return "\(v.formatted(.number.precision(.fractionLength(0...1))))"
        case .proximity: return "\(v.formatted(.number.precision(.fractionLength(0...1)))) ft"
        }
    }
}

// MARK: - Rounds

struct RoundsProgressView: View {
    let rounds: [Round]
    let handicaps: [HandicapEntry]

    var body: some View {
        let eighteen = rounds.filter { $0.holes == 18 }

        VStack(alignment: .leading, spacing: 20) {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                StatTile(title: "Best 18", value: eighteen.map(\.score).min().map { "\($0)" } ?? "—", tint: .blue)
                StatTile(title: "Putts / round",
                         value: avg(eighteen.compactMap(\.putts).map { Double($0) }, digits: 1), tint: .blue)
                StatTile(title: "GIR",
                         value: pct(eighteen.compactMap(\.girPercent)), tint: .blue)
                StatTile(title: "Fairways",
                         value: pct(rounds.compactMap(\.fairwayPercent)), tint: .blue)
                StatTile(title: "Up & down",
                         value: pct(rounds.compactMap(\.upAndDownPercent)), tint: .blue)
                StatTile(title: "Rounds", value: "\(rounds.count)", tint: .blue)
            }

            ChartCard(title: "Score (18 holes)") {
                if eighteen.isEmpty {
                    EmptyChartText("Add or import rounds to see your scoring trend.")
                } else {
                    let pts = eighteen.map { DatedValue(date: $0.date, value: Double($0.score)) }
                    Chart {
                        ForEach(pts) { p in
                            PointMark(x: .value("Date", p.date), y: .value("Score", p.value))
                                .foregroundStyle(Color.blue.opacity(0.5))
                        }
                        ForEach(ProgressStats.movingAverage(pts, window: 5)) { p in
                            LineMark(x: .value("Date", p.date), y: .value("Score", p.value))
                                .foregroundStyle(.blue)
                                .interpolationMethod(.catmullRom)
                        }
                    }
                    .chartYScale(domain: .automatic(includesZero: false))
                    .frame(height: 220)
                    Text("The line is a 5-round average.").font(.caption2).foregroundStyle(.secondary)
                }
            }

            ChartCard(title: "Handicap index") {
                if handicaps.count < 2 {
                    EmptyChartText("Update your index (Rounds tab) or import it from TheGrint to chart it.")
                } else {
                    Chart(handicaps) { h in
                        LineMark(x: .value("Date", h.date), y: .value("Index", h.index))
                            .foregroundStyle(.green)
                        PointMark(x: .value("Date", h.date), y: .value("Index", h.index))
                            .foregroundStyle(.green)
                    }
                    .chartYScale(domain: .automatic(includesZero: false))
                    .frame(height: 180)
                }
            }

            ChartCard(title: "Putts per round") {
                let putts = eighteen.compactMap { r in r.putts.map { DatedValue(date: r.date, value: Double($0)) } }
                if putts.isEmpty {
                    EmptyChartText("Track putts on your rounds to see this.")
                } else {
                    Chart(putts) { p in
                        BarMark(x: .value("Date", p.date, unit: .day), y: .value("Putts", p.value))
                            .foregroundStyle(Color.blue.gradient)
                    }
                    .frame(height: 160)
                }
            }
        }
    }

    private func avg(_ values: [Double], digits: Int) -> String {
        ProgressStats.average(values).map { $0.formatted(.number.precision(.fractionLength(digits))) } ?? "—"
    }

    private func pct(_ values: [Double]) -> String {
        ProgressStats.average(values).map { "\(Int(($0 * 100).rounded()))%" } ?? "—"
    }
}

// MARK: - Shared

struct ChartCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.headline)
            content
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16))
    }
}

struct EmptyChartText: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, minHeight: 80)
    }
}
