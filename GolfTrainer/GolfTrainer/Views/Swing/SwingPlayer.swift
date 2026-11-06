import SwiftUI
import AVFoundation
import Observation

/// Playback state for one swing video: slow motion, frame stepping and looping.
@Observable
final class SwingPlayerModel {
    let player: AVPlayer
    private(set) var isPlaying = false
    private(set) var currentTime: Double = 0
    private(set) var duration: Double = 0
    /// Video width / height, after rotation is applied.
    private(set) var aspectRatio: CGFloat = 9.0 / 16.0
    /// Frames per second the clip was recorded at (e.g. 240 for Slo-mo).
    private(set) var frameRate: Double?
    var rate: Float = 0.5
    var loops = true

    @ObservationIgnored private var timeObserver: Any?
    @ObservationIgnored private var endObserver: NSObjectProtocol?

    static let rates: [Float] = [0.1, 0.25, 0.5, 1.0]

    init(url: URL) {
        let item = AVPlayerItem(url: url)
        // Lets slow motion play smoothly at low rates.
        item.audioTimePitchAlgorithm = .varispeed
        player = AVPlayer(playerItem: item)
        player.isMuted = true
        player.actionAtItemEnd = .pause

        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 60),
                                                      queue: .main) { [weak self] time in
            self?.currentTime = time.seconds.isFinite ? time.seconds : 0
        }
        endObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime,
                                                             object: item, queue: .main) { [weak self] _ in
            guard let self else { return }
            self.player.seek(to: .zero, toleranceBefore: .zero, toleranceAfter: .zero)
            if self.loops && self.isPlaying {
                self.player.rate = self.rate
            } else {
                self.isPlaying = false
            }
        }
        Task { await loadMetadata(asset: item.asset) }
    }

    deinit {
        if let timeObserver { player.removeTimeObserver(timeObserver) }
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
    }

    @MainActor
    private func loadMetadata(asset: AVAsset) async {
        if let d = try? await asset.load(.duration), d.seconds.isFinite { duration = d.seconds }
        if let track = try? await asset.loadTracks(withMediaType: .video).first,
           let loaded = try? await track.load(.naturalSize, .preferredTransform) {
            let r = loaded.0.applying(loaded.1)
            if abs(r.height) > 0 { aspectRatio = abs(r.width) / abs(r.height) }
            if let fps = try? await track.load(.nominalFrameRate), fps > 0 { frameRate = Double(fps) }
        }
    }

    func togglePlay() { isPlaying ? pause() : play() }

    func play() {
        if duration > 0 && currentTime >= duration - 0.05 { seek(to: 0) }
        player.rate = rate
        isPlaying = true
    }

    func pause() {
        player.pause()
        isPlaying = false
    }

    func setRate(_ newRate: Float) {
        rate = newRate
        if isPlaying { player.rate = newRate }
    }

    /// Steps frame by frame. Pauses playback first.
    func step(_ frames: Int) {
        pause()
        player.currentItem?.step(byCount: frames)
    }

    func seek(to seconds: Double) {
        let t = CMTime(seconds: max(0, min(seconds, duration)), preferredTimescale: 600)
        player.seek(to: t, toleranceBefore: .zero, toleranceAfter: .zero)
        currentTime = t.seconds
    }
}

/// Shows an AVPlayer with no system controls, filling its frame with the video at its own aspect ratio.
struct PlayerLayerView: UIViewRepresentable {
    let player: AVPlayer

    final class PlayerUIView: UIView {
        override static var layerClass: AnyClass { AVPlayerLayer.self }
        var playerLayer: AVPlayerLayer { layer as! AVPlayerLayer }
    }

    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.playerLayer.videoGravity = .resizeAspect
        view.playerLayer.player = player
        view.backgroundColor = .black
        return view
    }

    func updateUIView(_ uiView: PlayerUIView, context: Context) {
        uiView.playerLayer.player = player
    }
}

/// Play/pause, frame step, speed and a scrubber.
struct PlayerControls: View {
    let model: SwingPlayerModel
    var compact = false

    var body: some View {
        VStack(spacing: 8) {
            Slider(value: Binding(get: { model.currentTime }, set: { model.seek(to: $0) }),
                   in: 0...max(model.duration, 0.01))
            HStack {
                Button { model.step(-1) } label: { Image(systemName: "backward.frame.fill") }
                Spacer()
                Button { model.togglePlay() } label: {
                    Image(systemName: model.isPlaying ? "pause.fill" : "play.fill").font(.title2)
                }
                Spacer()
                Button { model.step(1) } label: { Image(systemName: "forward.frame.fill") }
                if !compact {
                    Spacer()
                    RatePicker(rate: Binding(get: { model.rate }, set: { model.setRate($0) }))
                }
            }
            .buttonStyle(.borderless)
            .font(.title3)
            if !compact {
                Text(String(format: "%.2fs / %.2fs", model.currentTime, model.duration))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct RatePicker: View {
    @Binding var rate: Float

    var body: some View {
        Menu {
            ForEach(SwingPlayerModel.rates, id: \.self) { r in
                Button {
                    rate = r
                } label: {
                    if r == rate { Label(label(r), systemImage: "checkmark") } else { Text(label(r)) }
                }
            }
        } label: {
            Text(label(rate))
                .font(.subheadline.monospacedDigit().bold())
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color.secondary.opacity(0.15), in: Capsule())
        }
    }

    private func label(_ r: Float) -> String {
        r == 1 ? "1×" : String(format: "%g×", r)
    }
}
