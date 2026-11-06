import XCTest
@testable import GolfTrainer

final class GrintCSVImporterTests: XCTestCase {
    func testParsesBasicExport() throws {
        let csv = """
        Date,Course,Score,Par,Putts,Fairways,GIR,Handicap Index
        2026-10-01,Pebble Creek,84,72,31,8/14,7,12.4
        10/15/2026,"Oak Hills, North",79,71,29,9,10,11.9
        """
        let result = try GrintCSVImporter.parse(csv)
        XCTAssertEqual(result.rounds.count, 2)
        XCTAssertTrue(result.warnings.isEmpty)

        // Sorted newest first.
        let oak = result.rounds[0]
        XCTAssertEqual(oak.courseName, "Oak Hills, North")
        XCTAssertEqual(oak.score, 79)
        XCTAssertEqual(oak.par, 71)
        XCTAssertEqual(oak.fairwaysHit, 9)
        XCTAssertEqual(oak.handicapIndex, 11.9)

        let pebble = result.rounds[1]
        XCTAssertEqual(pebble.fairwaysHit, 8)
        XCTAssertEqual(pebble.fairwaysPossible, 14)
        XCTAssertEqual(pebble.greensInRegulation, 7)
        XCTAssertEqual(pebble.putts, 31)
        XCTAssertEqual(pebble.holes, 18)
    }

    func testHeaderAliasesAndCaseInsensitivity() throws {
        let csv = "DATE PLAYED;Course Name;Gross Score;Total Putts\n2026-09-01;Muni;45;16\n"
        let result = try GrintCSVImporter.parse(csv)
        XCTAssertEqual(result.rounds.count, 1)
        XCTAssertEqual(result.rounds[0].score, 45)
        XCTAssertEqual(result.rounds[0].holes, 9, "A score under 60 with no Holes column is treated as 9 holes")
        XCTAssertEqual(result.rounds[0].par, 36)
        XCTAssertEqual(result.rounds[0].putts, 16)
    }

    func testMissingRequiredColumnsThrows() {
        XCTAssertThrowsError(try GrintCSVImporter.parse("Course,Putts\nA,30")) { error in
            XCTAssertEqual(error as? CSVImportError, .missingColumns(["Date", "Score"]))
        }
        XCTAssertThrowsError(try GrintCSVImporter.parse("   \n")) { error in
            XCTAssertEqual(error as? CSVImportError, .empty)
        }
    }

    func testBadRowsBecomeWarnings() throws {
        let csv = "Date,Score\nnot a date,80\n2026-01-02,\n2026-01-03,88\n"
        let result = try GrintCSVImporter.parse(csv)
        XCTAssertEqual(result.rounds.count, 1)
        XCTAssertEqual(result.warnings.count, 2)
    }

    func testImportKeyIsStableForDuplicates() throws {
        let csv = "Date,Course,Score\n2026-05-05,Muni,90\n2026-05-05,MUNI,90\n"
        let result = try GrintCSVImporter.parse(csv)
        XCTAssertEqual(result.rounds[0].importKey, result.rounds[1].importKey)
    }

    func testPlusHandicap() {
        XCTAssertEqual(GrintCSVImporter.parseHandicap("+1.5"), -1.5)
        XCTAssertEqual(GrintCSVImporter.parseHandicap("7.2"), 7.2)
    }

    func testCSVQuotedFields() {
        let rows = GrintCSVImporter.parseCSV("a,\"b, c\",\"say \"\"hi\"\"\"\r\n1,2,3")
        XCTAssertEqual(rows, [["a", "b, c", "say \"hi\""], ["1", "2", "3"]])
    }
}

final class ProgressStatsTests: XCTestCase {
    var calendar: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        c.firstWeekday = 1
        return c
    }()

    func date(_ y: Int, _ m: Int, _ d: Int) -> Date {
        calendar.date(from: DateComponents(year: y, month: m, day: d, hour: 12))!
    }

    func testStreak() {
        let now = date(2026, 11, 6)
        let dates = [date(2026, 11, 6), date(2026, 11, 5), date(2026, 11, 4), date(2026, 11, 1)]
        XCTAssertEqual(ProgressStats.streakDays(dates, now: now, calendar: calendar), 3)
        // A streak still counts if your last practice was yesterday.
        XCTAssertEqual(ProgressStats.streakDays([date(2026, 11, 5)], now: now, calendar: calendar), 1)
        XCTAssertEqual(ProgressStats.streakDays([date(2026, 11, 3)], now: now, calendar: calendar), 0)
    }

    func testWeeklyMinutesFillsEmptyWeeks() {
        let now = date(2026, 11, 6)
        let entries = [
            PracticeEntry(date: date(2026, 11, 5), category: .putting, minutes: 30),
            PracticeEntry(date: date(2026, 11, 4), category: .putting, minutes: 15),
            PracticeEntry(date: date(2026, 10, 20), category: .range, minutes: 60),
        ]
        let weeks = ProgressStats.weeklyMinutes(entries, weeks: 4, now: now, calendar: calendar)
        XCTAssertEqual(weeks.count, 4 * PracticeCategory.allCases.count)
        let thisWeekPutting = weeks.last { $0.category == .putting }
        XCTAssertEqual(thisWeekPutting?.minutes, 45)
        XCTAssertEqual(weeks.filter { $0.category == .range }.map(\.minutes).reduce(0, +), 60)
    }

    func testTrend() {
        XCTAssertEqual(ProgressStats.trend([50, 52, 51, 60, 65, 70], window: 3, higherIsBetter: true), .improving)
        XCTAssertEqual(ProgressStats.trend([90, 91, 92, 84, 83, 82], window: 3, higherIsBetter: false), .improving)
        XCTAssertEqual(ProgressStats.trend([80, 80, 80, 80], window: 2, higherIsBetter: false), .flat)
        XCTAssertEqual(ProgressStats.trend([80], higherIsBetter: false), .insufficientData)
    }

    func testMovingAverage() {
        let pts = [10.0, 20, 30].enumerated().map { DatedValue(date: date(2026, 1, $0.offset + 1), value: $0.element) }
        XCTAssertEqual(ProgressStats.movingAverage(pts, window: 2).map(\.value), [10, 15, 25])
    }

    func testDrillScoring() {
        XCTAssertEqual(DrillScoring.chartValue(metric: .makes, attempts: 8, successes: 6, value: 0), 75)
        XCTAssertNil(DrillScoring.chartValue(metric: .makes, attempts: 0, successes: 0, value: 0))
        XCTAssertEqual(DrillScoring.chartValue(metric: .proximity, attempts: 10, successes: 0, value: 4.5), 4.5)
        XCTAssertEqual(DrillScoring.summary(metric: .makes, attempts: 12, successes: 9, value: 0), "9/12 (75%)")
    }

    func testDraftDrillUndo() {
        var d = DraftDrill(template: DrillLibrary.putting[0])
        d.record(make: true)
        d.record(make: false)
        d.undo()
        XCTAssertEqual(d.attempts, 1)
        XCTAssertEqual(d.successes, 1)
        d.undo()
        XCTAssertEqual(d.attempts, 0)
        XCTAssertEqual(d.successes, 0)
    }
}

final class SharedInboxTests: XCTestCase {
    var dir: URL!

    override func setUpWithError() throws {
        dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    func testRoundTripWithVideo() throws {
        let inbox = SharedInbox(directory: dir)
        let src = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID().uuidString).MOV")
        try Data("fake video".utf8).write(to: src)
        defer { try? FileManager.default.removeItem(at: src) }

        let saved = try inbox.add(SharedSwingItem(club: "7 Iron", angle: "faceOn", note: "Coach: shallow it", sourceApp: "V1 Golf"),
                                  copyingVideoFrom: src)
        XCTAssertEqual(saved.videoFileName, "\(saved.id.uuidString).mov")

        let pending = inbox.pending()
        XCTAssertEqual(pending.count, 1)
        XCTAssertEqual(pending[0].club, "7 Iron")
        XCTAssertEqual(pending[0].sourceApp, "V1 Golf")
        let video = try XCTUnwrap(inbox.videoURL(for: pending[0]))
        XCTAssertEqual(try Data(contentsOf: video), Data("fake video".utf8))

        inbox.remove(pending[0])
        XCTAssertTrue(inbox.pending().isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: video.path))
    }

    func testLinkOnlyAndOrdering() throws {
        let inbox = SharedInbox(directory: dir)
        try inbox.add(SharedSwingItem(date: Date(timeIntervalSince1970: 200), link: "https://example.com/b"), copyingVideoFrom: nil)
        try inbox.add(SharedSwingItem(date: Date(timeIntervalSince1970: 100), link: "https://example.com/a"), copyingVideoFrom: nil)
        XCTAssertEqual(inbox.pending().map(\.link), ["https://example.com/a", "https://example.com/b"])
        XCTAssertNil(inbox.pending()[0].videoFileName)
    }

    func testEmptyWhenFolderMissing() {
        XCTAssertTrue(SharedInbox(directory: dir).pending().isEmpty)
    }
}

final class SwingLineTests: XCTestCase {
    func testAngles() {
        // Horizontal
        XCTAssertEqual(SwingLine(start: CGPoint(x: 0.1, y: 0.5), end: CGPoint(x: 0.9, y: 0.5)).angleDegrees(aspectRatio: 1), 0, accuracy: 0.001)
        // Vertical
        XCTAssertEqual(SwingLine(start: CGPoint(x: 0.5, y: 0.9), end: CGPoint(x: 0.5, y: 0.1)).angleDegrees(aspectRatio: 1), 90, accuracy: 0.001)
        // 45° up and to the right on a square frame
        XCTAssertEqual(SwingLine(start: CGPoint(x: 0.2, y: 0.8), end: CGPoint(x: 0.8, y: 0.2)).angleDegrees(aspectRatio: 1), 45, accuracy: 0.001)
        // The same normalised line on a portrait (9:16) video is steeper in real pixels.
        XCTAssertEqual(SwingLine(start: CGPoint(x: 0.2, y: 0.8), end: CGPoint(x: 0.8, y: 0.2)).angleDegrees(aspectRatio: 9.0 / 16.0),
                       atan2(0.6, 0.6 * 9.0 / 16.0) * 180 / .pi, accuracy: 0.001)
        // The direction drawn doesn't matter.
        XCTAssertEqual(SwingLine(start: CGPoint(x: 0.8, y: 0.2), end: CGPoint(x: 0.2, y: 0.8)).angleDegrees(aspectRatio: 1), 45, accuracy: 0.001)
    }
}

final class SwingAnalysisTests: XCTestCase {
    func testFrameGrid() {
        XCTAssertEqual(FrameGrid.layout(count: 0).columns, 0)
        XCTAssertTrue(FrameGrid.layout(count: 1) == (1, 1))
        XCTAssertTrue(FrameGrid.layout(count: 3) == (3, 1))
        XCTAssertTrue(FrameGrid.layout(count: 4) == (2, 2))
        XCTAssertTrue(FrameGrid.layout(count: 5) == (3, 2))
        XCTAssertTrue(FrameGrid.layout(count: 6) == (3, 2))
    }

    func testContextText() {
        let ctx = SwingContext(club: "7 Iron", angle: "Down the line",
                               date: Date(timeIntervalSince1970: 1_780_000_000),
                               handicapIndex: -1.2, notes: "  Working on shallowing  ",
                               lessonFocus: "Transition", lessonFeedback: nil,
                               checkpoints: [SwingCheckpoint(position: .impact, time: 1.2),
                                             SwingCheckpoint(position: .address, time: 0.1),
                                             SwingCheckpoint(position: .top, time: 0.8)],
                               frameRate: 240, includesKeyPositionSheet: true)
        let text = ctx.text()
        XCTAssertTrue(text.contains("Club: 7 Iron · Camera: Down the line"))
        XCTAssertTrue(text.contains("Handicap index: +1.2"))
        XCTAssertTrue(text.contains("240 fps"))
        XCTAssertTrue(text.contains("Address → Top → Impact"))
        XCTAssertTrue(text.contains("Current lesson focus: Transition"))
        XCTAssertTrue(text.contains("What I'm working on / notes: Working on shallowing\n"))
        XCTAssertFalse(text.contains("Coach feedback"))
    }

    func testInboxWithScreenshots() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let inbox = SharedInbox(directory: dir)
        let imgs = try (0..<2).map { i -> URL in
            let u = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID().uuidString).PNG")
            try Data("img\(i)".utf8).write(to: u)
            return u
        }
        let saved = try inbox.add(SharedSwingItem(note: "from analyzer"), copyingVideoFrom: nil, images: imgs)
        XCTAssertEqual(saved.imageFileNames?.count, 2)
        let pending = try XCTUnwrap(inbox.pending().first)
        let urls = inbox.imageURLs(for: pending)
        XCTAssertEqual(try Data(contentsOf: urls[1]), Data("img1".utf8))
        XCTAssertTrue(urls[0].lastPathComponent.hasSuffix("-0.png"))
        inbox.remove(pending)
        XCTAssertFalse(FileManager.default.fileExists(atPath: urls[0].path))
    }
}
