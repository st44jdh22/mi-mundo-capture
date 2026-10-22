import SwiftUI
import UIKit
import AVFoundation
import UniformTypeIdentifiers

@MainActor
final class VoiceCapture: ObservableObject {
    @Published var isRecording = false
    @Published var seconds: TimeInterval = 0
    @Published var reachedLimit = false
    private var recorder: AVAudioRecorder?
    private var timer: Timer?

    func start(in folder: URL) async throws {
        let allowed = await withCheckedContinuation { continuation in
            AVAudioApplication.requestRecordPermission { granted in continuation.resume(returning: granted) }
        }
        guard allowed else { throw NSError(domain: "HeySophie", code: 1, userInfo: [NSLocalizedDescriptionKey: "Microphone access is off. Enable it in iPhone Settings to record a note."]) }
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                                               attributes: [.protectionKey: FileProtectionType.complete])
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .default)
        try session.setActive(true)
        let url = folder.appendingPathComponent("Voice-\(UUID().uuidString).m4a")
        let audio = try AVAudioRecorder(url: url, settings: [
            AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 44100,
            AVNumberOfChannelsKey: 1, AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ])
        guard audio.record(forDuration: 120) else { throw NSError(domain: "HeySophie", code: 2, userInfo: [NSLocalizedDescriptionKey: "Recording could not start. Your message is still here."]) }
        recorder = audio
        seconds = 0
        reachedLimit = false
        isRecording = true
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self, let recorder = self.recorder else { return }
                self.seconds = recorder.currentTime
                if !recorder.isRecording { self.reachedLimit = true }
            }
        }
    }

    func stop() -> URL? {
        guard let recorder else { return nil }
        let url = recorder.url
        recorder.stop()
        timer?.invalidate()
        timer = nil
        self.recorder = nil
        isRecording = false
        reachedLimit = false
        try? AVAudioSession.sharedInstance().setActive(false)
        return url
    }
}

/// Preserve the exact file representation supplied by the picker when available.
struct CameraCapture: UIViewControllerRepresentable {
    @Environment(\.dismiss) private var dismiss
    let picked: (URL) -> Void
    let failed: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = UIImagePickerController.isSourceTypeAvailable(.camera) ? .camera : .photoLibrary
        picker.mediaTypes = [UTType.image.identifier]
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let parent: CameraCapture
        init(_ parent: CameraCapture) { self.parent = parent }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let url = info[.imageURL] as? URL { parent.picked(url) }
            else if let image = info[.originalImage] as? UIImage, let bytes = image.jpegData(compressionQuality: 1) {
                // Camera often returns UIImage, not original sensor-file bytes. Explicitly a capture representation.
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("Camera-capture-\(UUID().uuidString).jpg")
                do { try bytes.write(to: url, options: [.atomic, .completeFileProtection]); parent.picked(url); try? FileManager.default.removeItem(at: url) }
                catch { parent.failed("Camera capture could not be saved. Please keep the photo in Photos and try importing it.") }
            }
            else { parent.failed("The camera returned no image. Nothing was saved.") }
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}
