import XCTest
@testable import HeySophie

final class PhotoCaptureTests: XCTestCase {
    var root: URL!
    var pipeline: PhotoCapturePipeline!
    var jpeg: Data!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        pipeline = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        jpeg = try Data(contentsOf: XCTUnwrap(Bundle.main.url(forResource: "synthetic-photo", withExtension: "jpg")))
    }
    override func tearDownWithError() throws { try? FileManager.default.removeItem(at: root) }

    func testValidPhotoAndExactBytesSurviveReopen() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        let receipt = try pipeline.receive(jpeg, for: request)
        XCTAssertEqual(receipt.width, 32); XCTAssertEqual(receipt.height, 24)
        XCTAssertEqual(receipt.mime, "image/jpeg")
        XCTAssertEqual(receipt.bytes, jpeg.count)
        XCTAssertEqual(receipt.sha256, CaptureDisk.hash(jpeg))
        XCTAssertTrue(receipt.receivedAt.hasSuffix("Z")); XCTAssertTrue(receipt.savedAt.hasSuffix("Z"))
        let reopened = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        XCTAssertEqual(try reopened.verify(request.id), receipt)
        let capture = try XCTUnwrap(reopened.disk.load().captures.first)
        XCTAssertEqual(try reopened.disk.read(capture.attachments[0], in: request.id), jpeg)
    }

    func testDuplicateCallbackAfterReopenDoesNotCreateSecondPhoto() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        let first = try pipeline.receive(jpeg, for: request)
        let reopened = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        XCTAssertEqual(try reopened.receive(jpeg, for: request), first)
        let captures = try reopened.disk.load().captures
        XCTAssertEqual(captures.count, 1); XCTAssertEqual(captures[0].attachments.count, 1)
    }

    func testChangedBytesForSameRequestAreRejected() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        let first = try pipeline.receive(jpeg, for: request)
        // Valid JPEG with an added COM marker, preserving image decode/dimensions.
        var changed = Data([0xff, 0xd8, 0xff, 0xfe, 0x00, 0x04, 0x4f, 0x4b])
        changed.append(jpeg.dropFirst(2))
        XCTAssertThrowsError(try pipeline.receive(changed, for: request))
        XCTAssertEqual(try pipeline.verify(request.id), first)
    }

    func testZeroAndCorruptJPEGNeverProduceReceipt() throws {
        for bytes in [Data(), Data("not jpeg".utf8), Data([0xff, 0xd8, 0xff, 0xd9]), Data(jpeg.dropLast(20))] {
            let request = try pipeline.begin(source: .syntheticFixture)
            XCTAssertThrowsError(try pipeline.receive(bytes, for: request))
            XCTAssertThrowsError(try pipeline.verify(request.id))
            let capture = try XCTUnwrap(pipeline.disk.load().captures.first { $0.id == request.id })
            XCTAssertNil(capture.photoReceipt); XCTAssertTrue(capture.attachments.isEmpty)
        }
    }

    func testUnknownRequestCannotSaveAnything() throws {
        let request = PhotoRequest(id: UUID(), source: .syntheticFixture,
                                   requestedAt: PhotoCapturePipeline.timestamp(), appSessionID: UUID())
        XCTAssertThrowsError(try pipeline.receive(jpeg, for: request))
        XCTAssertTrue(try pipeline.disk.load().captures.isEmpty)
    }

    func testSourceCannotBeRelabelledAsGlasses() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        let forged = PhotoRequest(id: request.id, source: .datCameraStream,
                                  requestedAt: request.requestedAt, appSessionID: request.appSessionID)
        XCTAssertThrowsError(try pipeline.receive(jpeg, for: forged))
        XCTAssertEqual(try pipeline.receive(jpeg, for: request).request.source, .syntheticFixture)
    }

    func testTamperingInvalidatesReadbackButPreservesFile() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        _ = try pipeline.receive(jpeg, for: request)
        let capture = try XCTUnwrap(pipeline.disk.load().captures.first)
        let url = pipeline.disk.folder(request.id).appendingPathComponent(capture.attachments[0].filename)
        try Data("corrupt".utf8).write(to: url)
        XCTAssertThrowsError(try pipeline.verify(request.id))
        XCTAssertThrowsError(try pipeline.receive(jpeg, for: request))
        XCTAssertEqual(try Data(contentsOf: url), Data("corrupt".utf8))
    }

    func testInterruptedSaveRetainsOrphanAndHoldsRetry() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        // Disk-full/process termination after atomic attachment write, before manifest.
        let orphan = pipeline.disk.folder(request.id).appendingPathComponent(UUID().uuidString.lowercased())
        try jpeg.write(to: orphan, options: .atomic)
        XCTAssertThrowsError(try pipeline.receive(jpeg, for: request))
        XCTAssertEqual(try Data(contentsOf: orphan), jpeg)
        XCTAssertFalse(try pipeline.disk.load().warnings.isEmpty)
        XCTAssertThrowsError(try pipeline.verify(request.id))
    }

    func testAttachmentCommittedWithoutReceiptHoldsRecovery() throws {
        let request = try pipeline.begin(source: .syntheticFixture)
        let capture = try XCTUnwrap(pipeline.disk.load().captures.first)
        _ = try pipeline.disk.attach(jpeg, name: "photo.jpg", contentType: "image/jpeg", to: capture)
        XCTAssertThrowsError(try pipeline.receive(jpeg, for: request))
        XCTAssertEqual(try pipeline.disk.load().captures.first?.attachments.count, 1)
    }

    func testOriginalV1ManifestStillDecodesAndFilesRemain() throws {
        var old = LocalCapture(); old.text = "Synthetic legacy draft"
        try pipeline.disk.commit(old)
        let url = pipeline.disk.folder(old.id).appendingPathComponent("capture.json")
        var json = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        json.removeValue(forKey: "photoRequest"); json.removeValue(forKey: "photoReceipt")
        try JSONSerialization.data(withJSONObject: json).write(to: url, options: .atomic)
        let restored = try XCTUnwrap(pipeline.disk.load().captures.first)
        XCTAssertEqual(restored.id, old.id); XCTAssertEqual(restored.text, old.text)
        XCTAssertNil(restored.photoRequest); XCTAssertNil(restored.photoReceipt)
    }
}
