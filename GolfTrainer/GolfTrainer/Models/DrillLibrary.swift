import Foundation

struct DrillTemplate: Identifiable, Hashable {
    let name: String
    let category: PracticeCategory
    let metric: DrillMetric
    let defaultAttempts: Int
    let instructions: String
    /// Optional benchmark to aim for (in the drill's own unit).
    let goal: Double?

    var id: String { "\(category.rawValue).\(name)" }

    init(_ name: String, _ category: PracticeCategory, _ metric: DrillMetric,
         attempts: Int, goal: Double? = nil, _ instructions: String) {
        self.name = name
        self.category = category
        self.metric = metric
        self.defaultAttempts = attempts
        self.goal = goal
        self.instructions = instructions
    }
}

enum DrillLibrary {
    static let all: [DrillTemplate] = range + shortGame + putting

    static func drills(for category: PracticeCategory) -> [DrillTemplate] {
        all.filter { $0.category == category }
    }

    static func template(named name: String) -> DrillTemplate? {
        all.first { $0.name == name }
    }

    static let range: [DrillTemplate] = [
        DrillTemplate("Fairway Finder", .range, .makes, attempts: 14, goal: 60,
                      "Pick two flags about 30 yards apart as your fairway. Hit 14 drives with a full pre-shot routine. A make is a ball that finishes between them."),
        DrillTemplate("Target Window", .range, .makes, attempts: 10, goal: 50,
                      "Choose a mid-iron target. A make is a ball that finishes within 10 yards of it. Change clubs every shot."),
        DrillTemplate("Wedge Ladder", .range, .makes, attempts: 12, goal: 60,
                      "Hit wedges to 50, 60, 70, 80, 90 and 100 yards, then back down. A make is a carry within 5 yards of the number."),
        DrillTemplate("9-Shot Shaping", .range, .makes, attempts: 9, goal: 66,
                      "Hit a draw, a straight ball and a fade, each one low, mid and high. A make is the shape you called."),
        DrillTemplate("Play the Course", .range, .points, attempts: 18, goal: 12,
                      "Play a round you know on the range: driver, then the approach club for each hole. Score 1 point for each fairway or green you would have hit."),
        DrillTemplate("Tempo / Contact", .range, .makes, attempts: 20, goal: 75,
                      "Hit half and three-quarter swings with a 7-iron. A make is centred contact, with ball first and then turf."),
    ]

    static let shortGame: [DrillTemplate] = [
        DrillTemplate("Up & Down Challenge", .shortGame, .makes, attempts: 9, goal: 50,
                      "Drop 9 balls around the green with varied lies. A make is getting down in 2 (chip and putt)."),
        DrillTemplate("Par 18", .shortGame, .strokes, attempts: 9, goal: 18,
                      "Play 9 'holes' from random spots around the green and hole out each one. Par is 2 per hole, so 18 total."),
        DrillTemplate("Landing Spot", .shortGame, .makes, attempts: 10, goal: 60,
                      "Put a towel on the green as your landing spot. A make is a chip that lands on the towel."),
        DrillTemplate("Proximity Chipping", .shortGame, .proximity, attempts: 10, goal: 4,
                      "Hit 10 chips from 10–20 yards and record the average distance from the hole in feet."),
        DrillTemplate("Bunker Escapes", .shortGame, .makes, attempts: 10, goal: 70,
                      "A make is a ball that gets out and stays on the green. A ball inside 10 ft counts as a bonus, so note it."),
        DrillTemplate("Pitch Distance Control", .shortGame, .makes, attempts: 12, goal: 50,
                      "Pitch to 20, 30 and 40 yards, rotating targets. A make is a ball that finishes within 10 ft."),
    ]

    static let putting: [DrillTemplate] = [
        DrillTemplate("Circle Drill (3 ft)", .putting, .makes, attempts: 12, goal: 95,
                      "Put 12 balls in a circle 3 ft from the hole. Go around the circle; a make is a holed putt."),
        DrillTemplate("Clock Drill (6 ft)", .putting, .makes, attempts: 12, goal: 65,
                      "Put 12 balls in a circle 6 ft from the hole, one at each clock position."),
        DrillTemplate("Gate Drill", .putting, .makes, attempts: 20, goal: 85,
                      "Push two tees in just wider than the putter head. A make is a stroke through the gate with no tee touched."),
        DrillTemplate("Lag Putting (30–50 ft)", .putting, .proximity, attempts: 10, goal: 3,
                      "Hit 10 long putts to different holes. Record the average leave in feet."),
        DrillTemplate("Lag Zone (inside 3 ft)", .putting, .makes, attempts: 10, goal: 70,
                      "Hit putts from 30 ft or more. A make is a ball that finishes within 3 ft of the hole, or goes in."),
        DrillTemplate("Putting Par 18", .putting, .strokes, attempts: 9, goal: 18,
                      "Play 9 holes on the practice green from 5 to 40 ft and hole out each one. Par is 18."),
        DrillTemplate("Pressure Streak (3 ft)", .putting, .points, attempts: 1, goal: 25,
                      "Hole as many 3-footers in a row as you can. Your score is the longest streak."),
    ]
}
