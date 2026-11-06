# Golf Trainer (iOS)

A SwiftUI and SwiftData iPhone app for logging practice and tracking progress.

- **Range, Short Game and Putting session loggers.** Each has a built-in drill library and supports custom drills. There are large Make / Miss / Undo buttons for logging on the range, a session timer, a rating and notes.
- **Rounds and TheGrint.** You can add rounds yourself or import them from a CSV export. Your handicap index is tracked over time.
- **Progress tracking.** There is an Overall view (practice minutes per week, practice mix, streak, handicap, skill trends), one view per category (a chart for each drill against its goal, with a moving average) and a Rounds view (score, handicap, putts, GIR, fairways, up-and-down %).

All data stays on the device (SwiftData). Requires iOS 17 or later.

## Build and run (on a Mac)

```bash
brew install xcodegen
cd GolfTrainer
xcodegen            # creates GolfTrainer.xcodeproj from project.yml
open GolfTrainer.xcodeproj
```

In Xcode, select the **GolfTrainer** target and go to *Signing & Capabilities*. Choose your Team, and change the bundle ID (`com.example.golftrainer.app`) to one of your own. Then pick your iPhone and press Run. Tests run with ⌘U.

## TheGrint integration

TheGrint does **not** publish a public API, so this app can't sync with it live. The integration works through files:

1. **CSV import** (Rounds tab → `+` → *Import from TheGrint (CSV)*). Pick a CSV file from Files or iCloud Drive. Column names are matched loosely and are not case sensitive.
   - Required: `Date`, `Score`
   - Optional: `Course`, `Holes`, `Par`, `Putts`, `Fairways` (`8` or `8/14`), `Fairways Possible`, `GIR`, `Up and Downs` (`3` or `3/9`), `Penalties`, `Handicap Index` (`+1.2` for plus handicaps)
   - Commas or semicolons both work as separators. Rounds that were already imported are skipped, so you can re-import a full history at any time.
   - See `SampleData/sample_grint_export.csv` for an example.
2. **Handicap.** Tap the index card on the Rounds tab to record your current TheGrint index. A `Handicap Index` column in the CSV is imported too.
3. **Open TheGrint.** A shortcut in the Rounds menu opens TheGrint.

If TheGrint's export uses different column names, add them to the `aliases` lists in `GolfTrainer/Services/GrintCSVImporter.swift`. If TheGrint ever publishes an API, a sync service can feed the same `ImportedRound` → `Round` path that the importer uses.

## Project layout

```
GolfTrainer/
  App/            App entry point and tab bar
  Models/         SwiftData models, enums, drill library
  Services/       CSV importer, progress statistics (pure functions, unit tested)
  Views/
    Practice/     Session lists, live session logger, drill picker, drill library
    Rounds/       Round list and editor, handicap editor, TheGrint import
    Progress/     Overall, category and rounds dashboards (Swift Charts)
    Components/   Shared UI bits
GolfTrainerTests/ XCTest unit tests
```

## Ideas for next steps

- Apple Watch companion for tapping Make / Miss without your phone
- iCloud sync (SwiftData + CloudKit)
- Practice plans: suggest drills from weak round stats (e.g. low up-and-down % → short game drills)
- Shot-by-shot round entry for strokes-gained style stats
