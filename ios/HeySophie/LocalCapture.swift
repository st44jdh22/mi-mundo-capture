import Foundation
import CryptoKit

enum CaptureFailure: LocalizedError {
    case empty, tooLarge, textTooLong, integrity, invalidPath
    var errorDescription: String? {
        switch self {
        case .empty: return "Add a message or attachment first."
        case .tooLarge: return "Keep each attachment under 20 MB and each message under 50 MB."
        case .textTooLong: return "This draft is saved. Please split it into notes under 20,000 characters before adding it to the Outbox."
        case .integrity: return "A saved attachment could not be verified. The original files have been kept."
        case .invalidPath: return "The saved file reference is invalid."
        }
    }
}

struct CaptureAttachment: Codable, Identifiable, Equatable {
    var id: UUID
    var name: String
    var contentType: String
    var bytes: Int
    var sha256: String
    var filename: String { id.uuidString.lowercased() }
}

struct LocalCapture: Codable, Identifiable, Equatable {
    enum State: String, Codable { case draft, queued }
    var version = 1
    var id = UUID()
    var createdAt = Date()
    var text = ""
    var attachments: [CaptureAttachment] = []
    var state: State = .draft
    // No uploaded/completed state exists until a reviewed receipt adapter is added.
}

/// A phone-local capture cache, not another institutional task register.
/// Bytes are immutable; the manifest is committed last and independently read back.
final class CaptureDisk {
    static let maxAttachment = 20 * 1024 * 1024
    static let maxMessage = 50 * 1024 * 1024
    let root: URL
    private let fm = FileManager.default

    init(root: URL) throws {
        self.root = root
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        #if os(iOS)
        try fm.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: root.path)
        #endif
        var location = root
        var values = URLResourceValues()
        // No unreviewed iCloud backup of captured private material.
        values.isExcludedFromBackup = true
        try location.setResourceValues(values)
    }

    func folder(_ id: UUID) -> URL { root.appendingPathComponent(id.uuidString.lowercased(), isDirectory: true) }

    private func options() -> Data.WritingOptions {
        #if os(iOS)
        return [.atomic, .completeFileProtection]
        #else
        return [.atomic]
        #endif
    }

    func commit(_ capture: LocalCapture, verifyFiles: Bool = true) throws {
        let location = folder(capture.id)
        try fm.createDirectory(at: location, withIntermediateDirectories: true)
        if verifyFiles { for item in capture.attachments { _ = try read(item, in: capture.id) } }
        let bytes = try JSONEncoder().encode(capture)
        let manifest = location.appendingPathComponent("capture.json")
        try bytes.write(to: manifest, options: options())
        guard try Data(contentsOf: manifest) == bytes else { throw CaptureFailure.integrity }
    }

    /// Read manifests independently: one corrupt job cannot hide other saved work.
    func load() throws -> (captures: [LocalCapture], warnings: [String]) {
        var captures: [LocalCapture] = [], warnings: [String] = []
        for folder in try fm.contentsOfDirectory(at: root, includingPropertiesForKeys: nil) {
            guard UUID(uuidString: folder.lastPathComponent) != nil else { continue }
            do {
                let capture = try JSONDecoder().decode(LocalCapture.self, from: Data(contentsOf: folder.appendingPathComponent("capture.json")))
                guard capture.version == 1, folder.lastPathComponent == capture.id.uuidString.lowercased() else { throw CaptureFailure.integrity }
                captures.append(capture)
                for attachment in capture.attachments {
                    do { _ = try read(attachment, in: capture.id) }
                    catch { warnings.append("Attachment needs recovery in message \(capture.id.uuidString.prefix(8)). Original files retained.") }
                }
                let pending = folder.appendingPathComponent("Incoming")
                if fm.fileExists(atPath: pending.path), !(try fm.contentsOfDirectory(atPath: pending.path)).isEmpty {
                    warnings.append("An interrupted recording is retained in message \(capture.id.uuidString.prefix(8)). Recover it before deleting the app.")
                }
                let expected = Set(capture.attachments.map(\.filename) + ["capture.json", "Incoming"])
                if try fm.contentsOfDirectory(atPath: folder.path).contains(where: { !expected.contains($0) }) {
                    warnings.append("An unlisted file is retained in message \(capture.id.uuidString.prefix(8)). Open recovery files to export it.")
                }
            } catch {
                warnings.append("Message \(folder.lastPathComponent.prefix(8)) could not be opened. Its files have not been replaced or deleted.")
            }
        }
        return (captures.sorted { $0.createdAt < $1.createdAt }, warnings)
    }

    func attach(_ bytes: Data, name: String, contentType: String, to capture: LocalCapture) throws -> LocalCapture {
        guard capture.state == .draft else { throw CaptureFailure.integrity }
        guard !bytes.isEmpty, bytes.count <= Self.maxAttachment,
              capture.attachments.count < 20,
              capture.attachments.reduce(0, { $0 + $1.bytes }) + bytes.count <= Self.maxMessage else { throw CaptureFailure.tooLarge }
        let item = CaptureAttachment(id: UUID(), name: String(name.prefix(200)), contentType: contentType,
                                     bytes: bytes.count, sha256: Self.hash(bytes))
        let location = folder(capture.id)
        try fm.createDirectory(at: location, withIntermediateDirectories: true)
        let destination = location.appendingPathComponent(item.filename)
        try bytes.write(to: destination, options: options())
        guard try read(item, in: capture.id) == bytes else { throw CaptureFailure.integrity }
        var updated = capture
        updated.attachments.append(item)
        // On failure retain bytes for recovery; do not publish a false saved state.
        try commit(updated)
        return updated
    }

    func attachFile(_ url: URL, contentType: String, to capture: LocalCapture) throws -> LocalCapture {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let bytes = try handle.read(upToCount: Self.maxAttachment + 1) ?? Data()
        return try attach(bytes, name: url.lastPathComponent, contentType: contentType, to: capture)
    }

    func read(_ item: CaptureAttachment, in id: UUID) throws -> Data {
        let url = folder(id).appendingPathComponent(item.filename)
        let attrs = try fm.attributesOfItem(atPath: url.path)
        guard attrs[.type] as? FileAttributeType == .typeRegular else { throw CaptureFailure.invalidPath }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: Self.maxAttachment + 1) ?? Data()
        guard data.count == item.bytes, data.count <= Self.maxAttachment, Self.hash(data) == item.sha256 else { throw CaptureFailure.integrity }
        return data
    }

    func queue(_ capture: LocalCapture) throws -> LocalCapture {
        guard capture.state == .draft else { return capture }
        guard capture.text.count <= 20000 else { throw CaptureFailure.textTooLong }
        guard !capture.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !capture.attachments.isEmpty else { throw CaptureFailure.empty }
        var queued = capture
        queued.state = .queued
        try commit(queued)
        return queued
    }

    static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
}
