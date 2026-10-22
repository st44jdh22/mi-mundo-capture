import XCTest
@testable import HeySophie

final class CaptureDiskTests: XCTestCase {
    var root: URL!
    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    }
    override func tearDownWithError() throws { if FileManager.default.fileExists(atPath: root.path) { try FileManager.default.removeItem(at: root) } }

    func testDraftAndOriginalSurviveReopen() throws {
        let first = try CaptureDisk(root: root)
        var draft = LocalCapture()
        draft.text = "SYNTHETIC: remember this note"
        try first.commit(draft)
        let bytes = Data("SYNTHETIC ORIGINAL".utf8)
        draft = try first.attach(bytes, name: "receipt.txt", contentType: "text/plain", to: draft)
        let reopened = try CaptureDisk(root: root)
        let restored = try XCTUnwrap(reopened.load().captures.first)
        XCTAssertEqual(restored, draft)
        XCTAssertEqual(try reopened.read(restored.attachments[0], in: restored.id), bytes)
        XCTAssertEqual(restored.state, .draft)
    }

    func testOutboxCommitKeepsOriginalIdentityAndCannotImplyUpload() throws {
        let disk = try CaptureDisk(root: root)
        var draft = LocalCapture(); draft.text = "SYNTHETIC: test"
        try disk.commit(draft)
        let queued = try disk.queue(draft)
        let replay = try disk.queue(queued)
        XCTAssertEqual(queued, replay)
        XCTAssertEqual(queued.id, draft.id)
        XCTAssertEqual(queued.state.rawValue, "queued")
        XCTAssertEqual(try disk.load().captures.count, 1)
        XCTAssertThrowsError(try disk.attach(Data([1]), name: "later", contentType: "text/plain", to: queued))
    }

    func testTamperedAttachmentPreventsQueueWithoutDeletingSource() throws {
        let disk = try CaptureDisk(root: root)
        var draft = LocalCapture(); try disk.commit(draft)
        draft = try disk.attach(Data("original".utf8), name: "file", contentType: "text/plain", to: draft)
        let url = disk.folder(draft.id).appendingPathComponent(draft.attachments[0].filename)
        try Data("tampered".utf8).write(to: url)
        XCTAssertThrowsError(try disk.queue(draft))
        XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
        XCTAssertFalse(try disk.load().warnings.isEmpty)
    }

    func testCorruptManifestDoesNotHideHealthyJobOrResetItsFiles() throws {
        let disk = try CaptureDisk(root: root)
        var healthy = LocalCapture(); healthy.text = "SYNTHETIC healthy"; try disk.commit(healthy)
        let corrupt = LocalCapture(); try disk.commit(corrupt)
        let manifest = disk.folder(corrupt.id).appendingPathComponent("capture.json")
        try Data("broken".utf8).write(to: manifest)
        let result = try disk.load()
        XCTAssertEqual(result.captures.map(\.id), [healthy.id])
        XCTAssertEqual(result.warnings.count, 1)
        XCTAssertEqual(try Data(contentsOf: manifest), Data("broken".utf8))
    }

    func testOversizedAttachmentRejectedWithoutManifestChange() throws {
        let disk = try CaptureDisk(root: root)
        let draft = LocalCapture(); try disk.commit(draft)
        XCTAssertThrowsError(try disk.attach(Data(repeating: 1, count: CaptureDisk.maxAttachment + 1), name: "large", contentType: "application/octet-stream", to: draft))
        XCTAssertEqual(try disk.load().captures, [draft])
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: disk.folder(draft.id).path), ["capture.json"])
    }

    func testInterruptedRecordingIsPreservedAndSurfaced() throws {
        let disk = try CaptureDisk(root: root)
        let draft = LocalCapture(); try disk.commit(draft)
        let folder = disk.folder(draft.id).appendingPathComponent("Incoming")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let audio = folder.appendingPathComponent("interrupted.m4a")
        try Data("partial".utf8).write(to: audio)
        XCTAssertEqual(try disk.load().warnings.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: audio.path))
    }

    func testEmptyMessageRejected() throws {
        let disk = try CaptureDisk(root: root)
        var draft = LocalCapture(); draft.text = " \n "
        try disk.commit(draft)
        XCTAssertThrowsError(try disk.queue(draft))
        XCTAssertEqual(try disk.load().captures.first?.state, .draft)
    }
}
