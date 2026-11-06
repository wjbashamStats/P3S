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
