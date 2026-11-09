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
        defer { bridge.stop() }
        let denied = expectation(description: "Camera permission denied")
        bridge.onFailure = { error in
            switch error {
            case PhotoError.permissionDenied: break
            default: XCTFail("Expected camera denial, got: \(error.localizedDescription)")
            }
            denied.fulfill()
        }
        bridge.onReady = { XCTFail("Denied camera reached ready") }
        bridge.onSaved = { _ in XCTFail("Denied camera produced a saved receipt") }
        do { try bridge.connect(mockPermissionGranted: false) }
        catch { denied.fulfill(); throw error }
        await fulfillment(of: [denied], timeout: 30)
        bridge.stop()
        XCTAssertTrue(try pipeline.disk.load().captures.isEmpty)
    }

    func testOfficialMockPhotoReachesRealDiskBoundary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let pipeline = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        let bridge = try DATPhotoBridge(pipeline: pipeline)
        defer { bridge.stop() }
        let saved = expectation(description: "Official DAT mock camera callback")
        var receipt: PhotoReceipt?
        bridge.onReady = { do { try bridge.capture() } catch { XCTFail("Mock request failed"); saved.fulfill() } }
        bridge.onFailure = { error in XCTFail("Mock session failed: \(error.localizedDescription)"); saved.fulfill() }
        bridge.onSaved = { value in receipt = value; saved.fulfill() }
        do { try bridge.connect() }
        catch { saved.fulfill(); throw error }
        await fulfillment(of: [saved], timeout: 30)
        bridge.stop()
        let actual = try XCTUnwrap(receipt)
        XCTAssertEqual(actual.request.source, .datMock)
        let reopened = PhotoCapturePipeline(disk: try CaptureDisk(root: root))
        XCTAssertEqual(try reopened.verify(actual.request.id), actual)
    }
}
#endif
