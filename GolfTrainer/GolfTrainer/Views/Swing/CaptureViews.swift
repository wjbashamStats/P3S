import SwiftUI
import UIKit
import UniformTypeIdentifiers
import CoreTransferable

/// A video loaded from the Photos picker, copied to a temporary file.
struct PickedMovie: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let ext = received.file.pathExtension.isEmpty ? "mov" : received.file.pathExtension
            let copy = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(UUID().uuidString).\(ext)")
            try FileManager.default.copyItem(at: received.file, to: copy)
            return PickedMovie(url: copy)
        }
    }
}

/// Records a video with the system camera.
///
/// For the smoothest slow motion, record in Slo-mo (120/240 fps) in the Camera app,
/// then import the clip from Photos.
struct CameraRecorder: UIViewControllerRepresentable {
    let onFinish: (URL?) -> Void

    static var isAvailable: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.mediaTypes = [UTType.movie.identifier]
        picker.cameraCaptureMode = .video
        picker.videoQuality = .typeHigh
        picker.videoMaximumDuration = 30
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(onFinish: onFinish) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let onFinish: (URL?) -> Void
        init(onFinish: @escaping (URL?) -> Void) { self.onFinish = onFinish }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            onFinish(info[.mediaURL] as? URL)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onFinish(nil)
        }
    }
}

/// Saves a link to a swing or lesson in a coaching app.
struct AddSwingLinkView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @State private var link = ""
    @State private var sourceApp = CoachApps.suggestions[0]
    @State private var club = ""
    @State private var angle: CameraAngle = .downTheLine
    @State private var notes = ""

    private var url: URL? {
        let trimmed = link.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let u = URL(string: trimmed), u.scheme != nil else { return nil }
        return u
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("https://…", text: $link)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Paste") { link = UIPasteboard.general.string ?? link }
                } header: {
                    Text("Link")
                } footer: {
                    Text("Paste a share link to a swing, lesson or voice-over from your coaching app. Tip: if the app can save the video itself, share it to Golf Trainer instead, so you get slow motion and drawing tools.")
                }
                Section {
                    Picker("From", selection: $sourceApp) {
                        ForEach(CoachApps.suggestions, id: \.self) { Text($0) }
                    }
                    ClubPicker(club: $club)
                    Picker("Camera angle", selection: $angle) {
                        ForEach(CameraAngle.allCases) { Text($0.title).tag($0) }
                    }
                    TextField("Notes", text: $notes, axis: .vertical)
                }
            }
            .navigationTitle("Add Coach Link")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let swing = SwingVideo(club: club, angle: angle, source: .link)
                        swing.externalLink = url?.absoluteString
                        swing.sourceApp = sourceApp
                        swing.notes = notes
                        context.insert(swing)
                        try? context.save()
                        dismiss()
                    }
                    .disabled(url == nil)
                }
            }
        }
    }
}

struct ClubPicker: View {
    @Binding var club: String
    var body: some View {
        Picker("Club", selection: $club) {
            Text("None").tag("")
            ForEach(Clubs.all, id: \.self) { Text($0).tag($0) }
        }
    }
}
