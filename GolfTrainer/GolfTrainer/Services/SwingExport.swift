import UIKit
import AVFoundation
import SwiftUI

/// Builds frames, key-position sheets and files to send to a swing-analysis chat or a coach.
enum SwingExport {
    enum ExportError: LocalizedError {
        case noVideo
        var errorDescription: String? { "This swing has no video to take frames from." }
    }

    /// The exact video frame at `seconds`, rotated upright.
    static func frame(from videoURL: URL, at seconds: Double, maxDimension: CGFloat = 1600) async throws -> UIImage {
        let generator = AVAssetImageGenerator(asset: AVURLAsset(url: videoURL))
        generator.appliesPreferredTrackTransform = true
        generator.requestedTimeToleranceBefore = .zero
        generator.requestedTimeToleranceAfter = .zero
        generator.maximumSize = CGSize(width: maxDimension, height: maxDimension)
        let (cgImage, _) = try await generator.image(at: CMTime(seconds: seconds, preferredTimescale: 600))
        return UIImage(cgImage: cgImage)
    }

    /// Draws lines (and optionally a label banner) on top of a frame.
    static func render(_ image: UIImage, lines: [SwingLine], label: String? = nil, showsAngles: Bool = true) -> UIImage {
        let size = image.size
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            image.draw(in: CGRect(origin: .zero, size: size))
            let cg = ctx.cgContext
            let lineWidth = max(3, size.width / 180)
            let aspect = size.width / max(size.height, 1)
            for line in lines {
                let a = CGPoint(x: line.start.x * size.width, y: line.start.y * size.height)
                let b = CGPoint(x: line.end.x * size.width, y: line.end.y * size.height)
                let color = UIColor(LinePalette.color(line.colorIndex))
                cg.setLineCap(.round)
                cg.setStrokeColor(UIColor.black.withAlphaComponent(0.5).cgColor)
                cg.setLineWidth(lineWidth + 2)
                cg.strokeLineSegments(between: [a, b])
                cg.setStrokeColor(color.cgColor)
                cg.setLineWidth(lineWidth)
                cg.strokeLineSegments(between: [a, b])
                if showsAngles {
                    let text = "\(Int(line.angleDegrees(aspectRatio: aspect).rounded()))°" as NSString
                    text.draw(at: CGPoint(x: (a.x + b.x) / 2 + lineWidth * 3, y: (a.y + b.y) / 2 - lineWidth * 6),
                              withAttributes: [.font: UIFont.boldSystemFont(ofSize: lineWidth * 6),
                                               .foregroundColor: color,
                                               .strokeColor: UIColor.black,
                                               .strokeWidth: -3])
                }
            }
            if let label {
                drawBanner(label, width: size.width, in: cg)
            }
        }
    }

    /// A grid of labelled frames (address → finish) on one image. Chat tools usually read this more reliably than a video.
    static func keyPositionSheet(_ frames: [(label: String, image: UIImage)], title: String?, cellWidth: CGFloat = 600) -> UIImage? {
        let (columns, rows) = FrameGrid.layout(count: frames.count)
        guard columns > 0, let first = frames.first?.image else { return nil }
        let cellHeight = cellWidth * first.size.height / max(first.size.width, 1)
        let gap: CGFloat = 8
        let header: CGFloat = title == nil ? 0 : 56
        let size = CGSize(width: CGFloat(columns) * cellWidth + CGFloat(columns + 1) * gap,
                          height: header + CGFloat(rows) * cellHeight + CGFloat(rows + 1) * gap)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            UIColor.black.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            if let title {
                (title as NSString).draw(at: CGPoint(x: gap * 2, y: 12),
                                         withAttributes: [.font: UIFont.boldSystemFont(ofSize: 30), .foregroundColor: UIColor.white])
            }
            for (i, frame) in frames.enumerated() {
                let col = i % columns, row = i / columns
                let rect = CGRect(x: gap + CGFloat(col) * (cellWidth + gap),
                                  y: header + gap + CGFloat(row) * (cellHeight + gap),
                                  width: cellWidth, height: cellHeight)
                frame.image.draw(in: aspectFit(frame.image.size, in: rect))
                ctx.cgContext.saveGState()
                ctx.cgContext.translateBy(x: rect.minX, y: rect.minY)
                drawBanner("\(i + 1). \(frame.label)", width: rect.width, in: ctx.cgContext)
                ctx.cgContext.restoreGState()
            }
        }
    }

    /// Writes an image to a temporary JPEG with a readable name, so it arrives in the chat with a sensible file name.
    static func temporaryFile(for image: UIImage, named name: String) throws -> URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("Export", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let safe = name.components(separatedBy: CharacterSet(charactersIn: "/\\:?%*|\"<>")).joined(separator: "-")
        let url = dir.appendingPathComponent("\(safe).jpg")
        try image.jpegData(compressionQuality: 0.85)?.write(to: url, options: .atomic)
        return url
    }

    private static func drawBanner(_ text: String, width: CGFloat, in cg: CGContext) {
        let fontSize = max(18, width / 22)
        let height = fontSize * 1.8
        cg.setFillColor(UIColor.black.withAlphaComponent(0.55).cgColor)
        cg.fill(CGRect(x: 0, y: 0, width: width, height: height))
        (text as NSString).draw(at: CGPoint(x: fontSize * 0.6, y: fontSize * 0.35),
                                withAttributes: [.font: UIFont.boldSystemFont(ofSize: fontSize),
                                                 .foregroundColor: UIColor.white])
    }

    private static func aspectFit(_ size: CGSize, in rect: CGRect) -> CGRect {
        let scale = min(rect.width / max(size.width, 1), rect.height / max(size.height, 1))
        let w = size.width * scale, h = size.height * scale
        return CGRect(x: rect.midX - w / 2, y: rect.midY - h / 2, width: w, height: h)
    }
}

/// Presents the system share sheet for arbitrary items (files, images, text).
struct ActivityView: UIViewControllerRepresentable {
    let items: [Any]
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
