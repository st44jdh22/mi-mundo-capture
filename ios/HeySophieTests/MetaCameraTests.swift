import XCTest
@testable import HeySophie

@MainActor
final class MetaCameraTests: XCTestCase {
    func testInitialStateCannotClaimPhotoOrUpload() {
        let model = MetaPhotoCamera()
        XCTAssertEqual(model.status, "READY")
        XCTAssertNil(model.receipt); XCTAssertFalse(model.busy); XCTAssertFalse(model.streaming)
        model.capture()
        XCTAssertNil(model.receipt)
    }

    #if !HS_META_DAT
    func testDisabledSDKCannotStartCameraOrClaimSave() {
        let model = MetaPhotoCamera()
        model.connect()
        XCTAssertEqual(model.status, "FAILED")
        XCTAssertNil(model.receipt); XCTAssertFalse(model.busy); XCTAssertFalse(model.streaming)
    }
    #endif
}

#if HS_META_DAT && targetEnvironment(simulator)
@MainActor
final class DATMockCameraTests: XCTestCase {
    func testDeniedMockCameraPermissionNeverStartsOrSaves() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let pipeline = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        let bridge = try DATPhotoBridge(pipeline: pipeline)
        let denied = expectation(description: "Camera permission denied")
        bridge.onFailure = { _ in denied.fulfill() }
        bridge.onReady = { XCTFail("Denied camera reached ready") }
        bridge.onSaved = { _ in XCTFail("Denied camera produced a saved receipt") }
        try bridge.connect(mockPermissionGranted: false)
        await fulfillment(of: [denied], timeout: 5)
        bridge.stop()
        XCTAssertTrue(try pipeline.disk.load().captures.isEmpty)
    }

    func testOfficialMockPhotoReachesRealDiskBoundary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let pipeline = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        let bridge = try DATPhotoBridge(pipeline: pipeline)
        let saved = expectation(description: "Official DAT mock camera callback")
        var receipt: PhotoReceipt?
        bridge.onReady = { do { try bridge.capture() } catch { XCTFail("Mock request failed"); saved.fulfill() } }
        bridge.onFailure = { _ in XCTFail("Mock session failed"); saved.fulfill() }
        bridge.onSaved = { value in receipt = value; saved.fulfill() }
        try bridge.connect()
        await fulfillment(of: [saved], timeout: 15)
        bridge.stop()
        let actual = try XCTUnwrap(receipt)
        XCTAssertEqual(actual.request.source, .datMock)
        let reopened = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        XCTAssertEqual(try reopened.verify(actual.request.id), actual)
    }
}
#endif
