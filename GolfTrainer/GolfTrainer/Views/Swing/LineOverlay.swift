import SwiftUI

enum LinePalette {
    static let colors: [Color] = [.yellow, .red, .cyan, .white]
    static func color(_ index: Int) -> Color { colors[((index % colors.count) + colors.count) % colors.count] }
}

/// Draws saved lines over the video. While `isDrawing` is on, dragging adds a new line.
struct LineOverlay: View {
    @Binding var lines: [SwingLine]
    let isDrawing: Bool
    let colorIndex: Int
    let aspectRatio: CGFloat
    var showsAngles = true

    @State private var draft: SwingLine?

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            Canvas { ctx, _ in
                for line in lines + (draft.map { [$0] } ?? []) {
                    let a = CGPoint(x: line.start.x * size.width, y: line.start.y * size.height)
                    let b = CGPoint(x: line.end.x * size.width, y: line.end.y * size.height)
                    var path = Path()
                    path.move(to: a)
                    path.addLine(to: b)
                    let color = LinePalette.color(line.colorIndex)
                    ctx.stroke(path, with: .color(.black.opacity(0.5)), lineWidth: 5)
                    ctx.stroke(path, with: .color(color), lineWidth: 3)
                    for p in [a, b] {
                        ctx.fill(Path(ellipseIn: CGRect(x: p.x - 4, y: p.y - 4, width: 8, height: 8)), with: .color(color))
                    }
                    if showsAngles {
                        let text = Text("\(Int(line.angleDegrees(aspectRatio: aspectRatio).rounded()))°")
                            .font(.caption.bold())
                            .foregroundColor(color)
                        ctx.draw(text, at: CGPoint(x: (a.x + b.x) / 2 + 14, y: (a.y + b.y) / 2 - 10))
                    }
                }
            }
            .contentShape(Rectangle())
            .gesture(drawGesture(in: size), including: isDrawing ? .all : .none)
            .allowsHitTesting(isDrawing)
        }
    }

    private func drawGesture(in size: CGSize) -> some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                let start = normalize(value.startLocation, size)
                let end = normalize(value.location, size)
                if draft == nil {
                    draft = SwingLine(start: start, end: end, colorIndex: colorIndex)
                } else {
                    draft?.end = end
                }
            }
            .onEnded { _ in
                if let draft { lines.append(draft) }
                draft = nil
            }
    }

    private func normalize(_ p: CGPoint, _ size: CGSize) -> CGPoint {
        CGPoint(x: min(max(p.x / max(size.width, 1), 0), 1),
                y: min(max(p.y / max(size.height, 1), 0), 1))
    }
}
