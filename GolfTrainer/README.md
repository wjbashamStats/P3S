# Golf Trainer (iOS)

A SwiftUI and SwiftData iPhone app for logging practice and tracking progress.

- **Range, Short Game and Putting session loggers.** Each has a built-in drill library and supports custom drills. There are large Make / Miss / Undo buttons for logging on the range, a session timer, a rating and notes.
- **Swing analyzer chat workflow.** Bring in videos and screenshots from your video app, mark key positions, then send frames, a one-image key-positions sheet and a context message to your swing-analysis chat. Paste the reply back onto the swing.
- **Swing tracking and coach integration.** Record swings, or import them from Photos or Files. Coaching apps can share videos and links straight into the app. Review swings in slow motion (0.1×–1×) and frame by frame, draw lines with angle readouts, compare two swings side by side, and tag swings by club and camera angle. Log lessons (coach, feedback, assigned drills, next lesson) and attach swings to them. Send a swing to your coach through the share sheet.
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

In Xcode, set your signing Team on **both** the GolfTrainer and GolfTrainerShare targets. Change the bundle IDs and the App Group to your own (see *Swing coach integration* below). Then pick your iPhone and press Run. Tests run with ⌘U.

The extension's bundle ID must start with the app's bundle ID (for example `…app.share`).

## Swing coach integration

As far as I know, the popular coaching apps (V1 Golf, CoachNow, Skillest, Sportsbox AI, Hudl Technique and others) don't offer public APIs. So the integration goes through the iOS **share sheet**, which they all support:

- **Coach app → Golf Trainer.** In your coaching app (or Photos or Files), tap **Share**, then **Golf Trainer**. Golf Trainer may be under *More* the first time. A small form asks for the club, camera angle, source app and a note.
  - A shared **video** is saved with full slow-motion and drawing tools.
  - A shared **link**, or text containing a link (e.g. a lesson or voice-over), is saved as a swing that opens back in the coach app.
  - Items show up in the Swing tab under *New from share sheet* the next time you open Golf Trainer.
- **Golf Trainer → coach.** In any swing, tap *Send to Coach / Share*. This sends the video to your coaching app (if it accepts videos), or to Messages, Mail or AirDrop.
- **Lessons.** On Swing → Lessons, record the coach, format (in person, or the app), feedback, assigned drills (one per line), the lesson link, and the next lesson date. Attach the swings that go with each lesson.

**App Group setup (required for the share extension):** the extension passes files to the app through a shared App Group container. Replace `group.com.example.golftrainer` with your own ID (for example `group.<your bundle id>`) in **both** places, then run `xcodegen` again:
1. `project.yml` (both `entitlements` blocks)
2. `GolfTrainer/Shared/SharedInbox.swift` (`appGroupID`)

With automatic signing, Xcode registers the group for you. Without an App Group, everything else still works, but the share extension shows an error when you save.

**Tip:** for the smoothest slow motion, record in **Slo-mo** (120/240 fps) with the iPhone Camera app and import the clip from Photos. The in-app recorder records at normal frame rate.

## Swing analyzer chat workflow

If you make swing videos and screenshots in another app and send them to a swing-analysis chat, Golf Trainer sits between the two and keeps the history:

1. **Bring it in.** In your video/analysis app, tap Share → **Golf Trainer**. You can share a video, up to 10 screenshots, or both at once; they're saved together as one swing. You can also use *Import Screenshots* or *Import from Photos* on the Swing tab, or add stills to any swing in its *Screenshots* section.
2. **Mark key positions.** In the player, scrub to Address, Takeaway, Top, Transition, Impact and Finish, and tap **Mark** at each one.
3. **Share for Analysis.** Golf Trainer builds:
   - a **key positions sheet**: every marked frame on one labelled image, with your lines drawn on
   - optional individual frames, the current frame, your screenshots and the video
   - a **context message**: club, camera angle, handicap, video frame rate, lesson focus and your notes, plus a request for the biggest issues and drills

   Pick your chat app in the share sheet. If it doesn't pick up the text, use *Copy Context* and paste it.
4. **Save the answer.** Copy the chat's reply and tap **Paste Feedback** on the swing. The feedback stays with the swing, so you can compare it next time.

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
  Models/         SwiftData models (practice, rounds, swings, lessons), drill library
  Shared/         Code shared with the share extension (inbox format, clubs, angles)
  Services/       CSV importer, progress stats, swing storage, frame and sheet export
  Views/
    Practice/     Session lists, live session logger, drill picker, drill library
    Rounds/       Round list and editor, handicap editor, TheGrint import
    Swing/        Swing library, player, line drawing, compare, lessons, capture/import
    Progress/     Overall, category and rounds dashboards (Swift Charts)
    Components/   Shared UI bits
GolfTrainerShare/ Share extension ("Save to Golf Trainer")
GolfTrainerTests/ XCTest unit tests
```

## Ideas for next steps

- Apple Watch companion for tapping Make / Miss without your phone
- High-frame-rate in-app capture (AVCaptureSession at 240 fps) and on-device pose tracking (Vision) for automatic checkpoints
- iCloud sync (SwiftData + CloudKit)
- Practice plans: suggest drills from weak round stats (e.g. low up-and-down % → short game drills)
- Shot-by-shot round entry for strokes-gained style stats
