import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

@MainActor
final class CaptureModel: ObservableObject {
    @Published var draft: LocalCapture?
    @Published var saved: [LocalCapture] = []
    @Published var error: String?
    @Published var recovery: [String] = []
    private(set) var disk: CaptureDisk?

    init() { reload() }

    func reload() {
        do {
            if disk == nil {
                let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
                disk = try CaptureDisk(root: support.appendingPathComponent("HeySophieCaptures", isDirectory: true))
            }
            guard let disk else { return }
            let result = try disk.load()
            recovery = result.warnings
            saved = result.captures.filter { $0.state == .queued }
            // Keep any extra interrupted drafts visible in the Outbox too.
            let drafts = result.captures.filter { $0.state == .draft }
            draft = drafts.last
            saved += drafts.dropLast()
            if draft == nil { let item = LocalCapture(); try disk.commit(item); draft = item }
        } catch { self.error = "Phone storage could not be opened. \(error.localizedDescription)" }
    }

    func updateText(_ text: String) {
        guard var item = draft, let disk else { return }
        item.text = text
        draft = item
        do { try disk.commit(item, verifyFiles: false) }
        catch { self.error = "Changes are not yet saved. \(error.localizedDescription)" }
    }

    func add(_ data: Data, name: String, type: String) {
        guard let draft, let disk else { return }
        do { self.draft = try disk.attach(data, name: name, contentType: type, to: draft) }
        catch { self.error = error.localizedDescription }
    }

    func addFile(_ url: URL) {
        guard let draft, let disk else { return }
        let scope = url.startAccessingSecurityScopedResource()
        defer { if scope { url.stopAccessingSecurityScopedResource() } }
        do {
            self.draft = try disk.attachFile(url, contentType: UTType(filenameExtension: url.pathExtension)?.preferredMIMEType ?? "application/octet-stream", to: draft)
        } catch { self.error = error.localizedDescription }
    }

    @discardableResult func save() -> Bool {
        guard let draft, let disk else { return false }
        do {
            let queued = try disk.queue(draft)
            saved.append(queued)
            self.draft = nil
            let next = LocalCapture()
            try disk.commit(next)
            self.draft = next
            return true
        } catch { self.error = error.localizedDescription; return false }
    }
}

@main
struct HeySophieApp: App {
    @StateObject private var model = CaptureModel()
    var body: some Scene { WindowGroup { SophieHome().environmentObject(model).privacySensitive() } }
}

struct SophieHome: View {
    @EnvironmentObject private var model: CaptureModel
    @Environment(\.scenePhase) private var phase
    @StateObject private var voice = VoiceCapture()
    @State private var photo: PhotosPickerItem?
    @State private var importing = false
    @State private var camera = false
    @State private var busy = false
    @State private var selectedTab = 0
    private let accent = Color(red: 0.02, green: 0.48, blue: 0.49)

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 24) {
                        HStack {
                            Image(systemName: "sparkles").font(.title).foregroundStyle(accent)
                            VStack(alignment: .leading) {
                                Text("Hey Sophie!").font(.largeTitle.bold())
                                Text("A little space for everything on your mind.").font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.top, 12)
                        VStack(alignment: .leading, spacing: 12) {
                            Text("What’s on your mind?").font(.title2.bold())
                            Text("Write a note, record your voice, or add a photo. Your draft stays here when you come back.")
                                .foregroundStyle(.secondary)
                            TextEditor(text: Binding(get: { model.draft?.text ?? "" }, set: { model.updateText($0) }))
                                .frame(minHeight: 150).scrollContentBackground(.hidden)
                                .accessibilityLabel("Message to Sophie")
                                .disabled(model.draft == nil || voice.isRecording || busy)
                            if let count = model.draft?.text.count, count > 20000 {
                                Text("Draft saved. Split into notes under 20,000 characters before queuing.")
                                    .font(.caption).foregroundStyle(.red)
                            }
                        }
                        .padding(20).background(.white, in: RoundedRectangle(cornerRadius: 24))
                        HStack(spacing: 16) {
                            PhotosPicker(selection: $photo, matching: .images) { Label("Photos", systemImage: "photo") }
                            Button { camera = true } label: { Image(systemName: "camera") }.accessibilityLabel("Take photo")
                            Button { importing = true } label: { Label("Files", systemImage: "paperclip") }
                        }.font(.subheadline.weight(.semibold)).disabled(voice.isRecording || busy || model.draft == nil)
                        if let item = model.draft {
                            ForEach(item.attachments) { attachment in
                                Label("\(attachment.name) · \(ByteCountFormatter.string(fromByteCount: Int64(attachment.bytes), countStyle: .file))", systemImage: attachment.contentType.hasPrefix("audio") ? "waveform" : "doc")
                                    .font(.footnote).lineLimit(2)
                            }
                        }
                        VStack(spacing: 12) {
                            Button { toggleVoice() } label: {
                                Label(voice.isRecording ? "Stop and keep recording" : "Record a voice note", systemImage: voice.isRecording ? "stop.fill" : "mic.fill")
                                    .frame(maxWidth: .infinity).padding(18)
                            }.buttonStyle(.borderedProminent).tint(voice.isRecording ? .red : accent)
                                .disabled(busy || model.draft == nil)
                            if voice.isRecording {
                                Text("Recording… \(Int(voice.seconds))s").monospacedDigit().foregroundStyle(.red)
                                Text("Stops at two minutes. Audio stays on your iPhone; transcription is not connected yet.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Button { if model.save() { selectedTab = 1 } } label: {
                                Label("Save to Outbox", systemImage: "tray.and.arrow.down").frame(maxWidth: .infinity).padding(14)
                            }.buttonStyle(.bordered).disabled(voice.isRecording || busy || model.draft == nil)
                        }
                        Label("Local capture build. Sophie’s replies and upload connection are coming next.", systemImage: "iphone")
                            .font(.footnote).foregroundStyle(.secondary)
                        if !model.recovery.isEmpty {
                            VStack(alignment: .leading) {
                                Label("Saved files need attention", systemImage: "exclamationmark.triangle.fill").font(.headline)
                                ForEach(model.recovery, id: \.self) { Text($0).font(.caption) }
                            }.padding().background(.orange.opacity(0.13), in: RoundedRectangle(cornerRadius: 16))
                        }
                    }.padding(22)
                }.background(Color(red: 0.94, green: 0.97, blue: 0.96))
                .toolbar { ToolbarItem(placement: .topBarTrailing) { Text("ON YOUR IPHONE").font(.caption2.bold()).foregroundStyle(accent) } }
            }.tabItem { Label("Sophie", systemImage: "bubble.left.and.bubble.right") }.tag(0)
            NavigationStack {
                List {
                    Section {
                        Label("NOT UPLOADED", systemImage: "exclamationmark.triangle.fill").font(.headline).foregroundStyle(.red)
                        Text("Messages below are saved on this iPhone only. Uploading is not connected. Keep the app installed until an independent backup is available.").font(.subheadline)
                        NavigationLink("Recovery files") { RecoveryFiles() }
                    }
                    if model.saved.isEmpty { Text("Your saved messages will appear here.").foregroundStyle(.secondary) }
                    ForEach(model.saved.sorted { $0.createdAt > $1.createdAt }) { item in
                        NavigationLink {
                            ScrollView {
                                VStack(alignment: .leading, spacing: 20) {
                                    Label("NOT UPLOADED", systemImage: "exclamationmark.triangle.fill").font(.headline).foregroundStyle(.red)
                                    Text(item.text.isEmpty ? "Attachments only" : item.text)
                                    Text(item.createdAt, style: .date).foregroundStyle(.secondary)
                                    ForEach(item.attachments) { attachment in
                                        AttachmentRow(attachment: attachment, captureID: item.id)
                                    }
                                    Text("Saved on iPhone. Server receipt: none. Department completion: none.").font(.footnote).foregroundStyle(.secondary)
                                }.padding()
                            }.navigationTitle("Saved message")
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item.text.isEmpty ? "\(item.attachments.count) attachment(s)" : item.text).lineLimit(2)
                                Text(item.createdAt, style: .time).font(.caption).foregroundStyle(.secondary)
                                Label("Not uploaded", systemImage: "exclamationmark.circle.fill").font(.caption.bold()).foregroundStyle(.red)
                            }.padding(.vertical, 6)
                        }
                    }
                }.navigationTitle("Outbox")
            }.tabItem { Label("Outbox", systemImage: "tray") }.badge(model.saved.count).tag(1)
        }.tint(accent)
        .fileImporter(isPresented: $importing, allowedContentTypes: [.item], allowsMultipleSelection: true) { result in
            do { for url in try result.get() { model.addFile(url) } }
            catch { model.error = error.localizedDescription }
        }
        .onChange(of: photo) { _, item in
            guard let item else { return }
            busy = true
            Task {
                defer { busy = false; photo = nil }
                do {
                    guard let data = try await item.loadTransferable(type: Data.self) else { throw CaptureFailure.empty }
                    let type = item.supportedContentTypes.first ?? .image
                    model.add(data, name: "Photo.\(type.preferredFilenameExtension ?? "img")", type: type.preferredMIMEType ?? "application/octet-stream")
                } catch { model.error = error.localizedDescription }
            }
        }
        .sheet(isPresented: $camera) {
            CameraCapture(picked: { url in model.addFile(url) }, failed: { model.error = $0 })
        }
        .onChange(of: phase) { _, value in
            if value != .active && voice.isRecording { finishVoice() }
        }
        .onReceive(voice.$reachedLimit) { hit in if hit { finishVoice() } }
        .alert("Please check", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
    }

    private func toggleVoice() {
        if voice.isRecording { finishVoice(); return }
        guard let id = model.draft?.id, let disk = model.disk else { return }
        busy = true
        Task {
            defer { busy = false }
            do { try await voice.start(in: disk.folder(id).appendingPathComponent("Incoming", isDirectory: true)) }
            catch { model.error = error.localizedDescription }
        }
    }

    private func finishVoice() {
        guard let url = voice.stop(), let disk = model.disk, let draft = model.draft else { return }
        do {
            let updated = try disk.attachFile(url, contentType: "audio/mp4", to: draft)
            model.draft = updated
            try FileManager.default.removeItem(at: url)
        } catch { model.error = "Recording retained for recovery. \(error.localizedDescription)" }
    }
}

struct AttachmentRow: View {
    @EnvironmentObject private var model: CaptureModel
    let attachment: CaptureAttachment
    let captureID: UUID
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(attachment.name, systemImage: "paperclip")
            if let disk = model.disk, (try? disk.read(attachment, in: captureID)) != nil {
                ShareLink("Export this attachment", item: disk.folder(captureID).appendingPathComponent(attachment.filename))
                    .font(.caption)
            } else { Text("File needs recovery").foregroundStyle(.red) }
        }
    }
}

struct RecoveryFiles: View {
    @EnvironmentObject private var model: CaptureModel
    @State private var files: [URL] = []
    @State private var problem: String?
    var body: some View {
        List {
            Text("Files retained by this app, including interrupted recordings. Export does not upload them or confirm a backup.").font(.footnote)
            if let problem { Text(problem).foregroundStyle(.red) }
            ForEach(files, id: \.self) { url in
                ShareLink(item: url) { Label(url.lastPathComponent, systemImage: "square.and.arrow.up").lineLimit(2) }
            }
        }.navigationTitle("Recovery files")
        .task {
            guard let root = model.disk?.root else { return }
            guard let enumerator = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey]) else { return }
            var result: [URL] = []
            for case let url as URL in enumerator {
                do {
                    let properties = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
                    if properties.isRegularFile == true && properties.isSymbolicLink != true { result.append(url) }
                } catch { problem = "Some files could not be listed. They have been retained." }
            }
            files = result.sorted { $0.path < $1.path }
        }
    }
}
