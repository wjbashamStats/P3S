import Foundation

/// A round parsed out of a CSV file, before it is saved to SwiftData.
struct ImportedRound: Equatable, Identifiable {
    var date: Date
    var courseName: String
    var holes: Int
    var par: Int
    var score: Int
    var putts: Int?
    var fairwaysHit: Int?
    var fairwaysPossible: Int?
    var greensInRegulation: Int?
    var upAndDownsMade: Int?
    var upAndDownAttempts: Int?
    var penalties: Int?
    var handicapIndex: Double?

    var id: String { importKey }

    /// Stable key used to skip rounds that were already imported.
    var importKey: String {
        let day = ISO8601DateFormatter.string(from: date, timeZone: .current, formatOptions: [.withFullDate])
        return "grint|\(day)|\(courseName.lowercased())|\(score)"
    }
}

struct CSVImportResult {
    var rounds: [ImportedRound]
    /// Human-readable problems, e.g. "Row 4: missing score".
    var warnings: [String]
}

enum CSVImportError: LocalizedError, Equatable {
    case empty
    case missingColumns([String])

    var errorDescription: String? {
        switch self {
        case .empty:
            return "The file is empty."
        case .missingColumns(let cols):
            return "Could not find the required column(s): \(cols.joined(separator: ", ")). Make sure the first row holds column headers."
        }
    }
}

/// Imports rounds from a CSV export (from TheGrint, or any spreadsheet).
///
/// TheGrint has no public API, so the import works from a file instead of a live
/// sync. Column names are matched loosely and are not case sensitive, so exports
/// with slightly different headers still work. Only Date and Score are required.
enum GrintCSVImporter {
    enum Field: CaseIterable {
        case date, course, holes, par, score, putts, fairways, fairwaysPossible,
             gir, upAndDowns, upAndDownAttempts, penalties, handicap

        var aliases: [String] {
            switch self {
            case .date: return ["date", "date played", "played", "round date", "played on"]
            case .course: return ["course", "course name", "club", "golf course"]
            case .holes: return ["holes", "holes played", "# holes"]
            case .par: return ["par", "course par"]
            case .score: return ["score", "gross", "gross score", "total", "total score", "strokes"]
            case .putts: return ["putts", "total putts", "# putts"]
            case .fairways: return ["fairways", "fir", "fairways hit", "fairways in regulation", "fw hit"]
            case .fairwaysPossible: return ["fairways possible", "fairway attempts", "fir possible", "fw possible"]
            case .gir: return ["gir", "greens", "greens in regulation", "greens hit"]
            case .upAndDowns: return ["up and downs", "up & downs", "up&down", "scrambling", "up and down made"]
            case .upAndDownAttempts: return ["up and down attempts", "scrambling attempts", "up & down attempts"]
            case .penalties: return ["penalties", "penalty strokes", "penalty"]
            case .handicap: return ["handicap", "handicap index", "hcp", "hcp index", "index", "grint handicap"]
            }
        }
    }

    static func parse(_ text: String) throws -> CSVImportResult {
        let rows = parseCSV(text).filter { !$0.allSatisfy { $0.trimmingCharacters(in: .whitespaces).isEmpty } }
        guard let header = rows.first else { throw CSVImportError.empty }

        let normalizedHeader = header.map(normalize)
        var columns: [Field: Int] = [:]
        for field in Field.allCases {
            if let idx = normalizedHeader.firstIndex(where: { field.aliases.contains($0) }) {
                columns[field] = idx
            }
        }

        let missing = [(Field.date, "Date"), (Field.score, "Score")]
            .filter { columns[$0.0] == nil }
            .map(\.1)
        guard missing.isEmpty else { throw CSVImportError.missingColumns(missing) }

        var rounds: [ImportedRound] = []
        var warnings: [String] = []

        for (offset, row) in rows.dropFirst().enumerated() {
            let rowNumber = offset + 2 // 1-based, including the header row
            func cell(_ f: Field) -> String? {
                guard let i = columns[f], i < row.count else { return nil }
                let v = row[i].trimmingCharacters(in: .whitespacesAndNewlines)
                return v.isEmpty ? nil : v
            }
            func int(_ f: Field) -> Int? { cell(f).flatMap(parseInt) }

            guard let dateText = cell(.date), let date = parseDate(dateText) else {
                warnings.append("Row \(rowNumber): could not read the date, so the row was skipped.")
                continue
            }
            guard let score = int(.score), score > 0 else {
                warnings.append("Row \(rowNumber): missing score, so the row was skipped.")
                continue
            }

            let holes = int(.holes) ?? (score < 60 ? 9 : 18)
            let par = int(.par) ?? (holes == 9 ? 36 : 72)

            // Fairways can come as "8/14" in one column.
            var fairwaysHit = int(.fairways)
            var fairwaysPossible = int(.fairwaysPossible)
            if let raw = cell(.fairways), let frac = parseFraction(raw) {
                fairwaysHit = frac.0
                fairwaysPossible = fairwaysPossible ?? frac.1
            }
            var udMade = int(.upAndDowns)
            var udAttempts = int(.upAndDownAttempts)
            if let raw = cell(.upAndDowns), let frac = parseFraction(raw) {
                udMade = frac.0
                udAttempts = udAttempts ?? frac.1
            }
            var gir = int(.gir)
            if let raw = cell(.gir), let frac = parseFraction(raw) { gir = frac.0 }

            rounds.append(ImportedRound(
                date: date,
                courseName: cell(.course) ?? "Unknown course",
                holes: holes,
                par: par,
                score: score,
                putts: int(.putts),
                fairwaysHit: fairwaysHit,
                fairwaysPossible: fairwaysPossible,
                greensInRegulation: gir,
                upAndDownsMade: udMade,
                upAndDownAttempts: udAttempts,
                penalties: int(.penalties),
                handicapIndex: cell(.handicap).flatMap(parseHandicap)
            ))
        }

        return CSVImportResult(rounds: rounds.sorted { $0.date > $1.date }, warnings: warnings)
    }

    // MARK: - Helpers

    static func normalize(_ header: String) -> String {
        header
            .trimmingCharacters(in: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: "\u{FEFF}")))
            .lowercased()
            .replacingOccurrences(of: "_", with: " ")
            .split(separator: " ", omittingEmptySubsequences: true)
            .joined(separator: " ")
    }

    static func parseInt(_ s: String) -> Int? {
        if let i = Int(s) { return i }
        if let d = Double(s) { return Int(d.rounded()) }
        return nil
    }

    /// "8/14" -> (8, 14)
    static func parseFraction(_ s: String) -> (Int, Int)? {
        let parts = s.split(separator: "/").map { $0.trimmingCharacters(in: .whitespaces) }
        guard parts.count == 2, let a = Int(parts[0]), let b = Int(parts[1]) else { return nil }
        return (a, b)
    }

    /// Handles "12.4", and "+1.2" for plus handicaps (stored as a negative index).
    static func parseHandicap(_ s: String) -> Double? {
        let trimmed = s.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("+"), let v = Double(trimmed.dropFirst()) { return -v }
        return Double(trimmed)
    }

    private static let dateFormats = [
        "yyyy-MM-dd", "MM/dd/yyyy", "M/d/yyyy", "M/d/yy", "MM/dd/yy",
        "yyyy/MM/dd", "MMM d, yyyy", "MMMM d, yyyy", "d MMM yyyy", "dd-MM-yyyy",
        "yyyy-MM-dd HH:mm:ss", "MM/dd/yyyy HH:mm", "yyyy-MM-dd'T'HH:mm:ss",
    ]

    static func parseDate(_ s: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        for format in dateFormats {
            formatter.dateFormat = format
            if let d = formatter.date(from: s) { return d }
        }
        let iso = ISO8601DateFormatter()
        return iso.date(from: s)
    }

    /// Minimal RFC 4180 CSV parser: handles quoted fields, escaped quotes and newlines inside quotes.
    static func parseCSV(_ text: String) -> [[String]] {
        var rows: [[String]] = []
        var row: [String] = []
        var field = ""
        var inQuotes = false
        let chars = Array(text.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n"))
        var i = 0
        // Auto-detect semicolon-delimited exports (common in some locales).
        let firstLine = chars.prefix { $0 != "\n" }
        let delimiter: Character = firstLine.filter { $0 == ";" }.count > firstLine.filter { $0 == "," }.count ? ";" : ","

        while i < chars.count {
            let c = chars[i]
            if inQuotes {
                if c == "\"" {
                    if i + 1 < chars.count && chars[i + 1] == "\"" {
                        field.append("\"")
                        i += 1
                    } else {
                        inQuotes = false
                    }
                } else {
                    field.append(c)
                }
            } else if c == "\"" {
                inQuotes = true
            } else if c == delimiter {
                row.append(field)
                field = ""
            } else if c == "\n" {
                row.append(field)
                rows.append(row)
                row = []
                field = ""
            } else {
                field.append(c)
            }
            i += 1
        }
        if !field.isEmpty || !row.isEmpty {
            row.append(field)
            rows.append(row)
        }
        return rows
    }
}
