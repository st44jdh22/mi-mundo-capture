import Foundation
import ImageIO
import UniformTypeIdentifiers

enum PhotoSource: String, Codable { case syntheticFixture, datMock, datCameraStream, localPhoneImport }

struct PhotoRequest: Codable, Equatable {
    let id: UUID
    let source: PhotoSource
    let requestedAt: String
    // App correlation only. Never presented as SDK device/session identity.
    let appSessionID: UUID
    let sdkDeviceID: String?

    init(id: UUID, source: PhotoSource, requestedAt: String, appSessionID: UUID, sdkDeviceID: String? = nil) {
        self.id = id; self.source = source; self.requestedAt = requestedAt
        self.appSessionID = appSessionID; self.sdkDeviceID = sdkDeviceID
    }
}

struct PhotoReceipt: Codable, Equatable {
    let request: PhotoRequest
    let receivedAt: String
    let savedAt: String
    let mime: String
    let width: Int
    let height: Int
    let bytes: Int
    let sha256: String
}

enum PhotoError: LocalizedError {
    case invalidJPEG, unknownRequest, conflictingCallback, incomplete, permissionDenied, interrupted
    var errorDescription: String? {
        switch self {
        case .invalidJPEG: return "The camera returned an incomplete or invalid JPEG. Nothing verified saved."
        case .unknownRequest: return "No matching photo request. Nothing verified saved."
        case .conflictingCallback: return "Different photo bytes arrived for the same request. Original retained."
        case .incomplete: return "Photo save needs recovery. Original files retained; no automatic recapture."
        case .permissionDenied: return "Camera permission denied. No photograph was saved."
        case .interrupted: return "Camera session interrupted. Check local files before requesting another photo."
        }
    }
}

/// One photo request owns one existing CaptureDisk job. No network dependency.
/// Caller serializes access (the UI/SDK adapter uses MainActor).
final class PhotoCapturePipeline {
    let disk: CaptureDisk
    init(disk: CaptureDisk) { self.disk = disk }

    static func timestamp(_ date: Date = Date()) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date) // explicit Z; receive/save, not a fabricated camera time
    }

    static func dimensions(_ data: Data) throws -> (Int, Int) {
        guard !data.isEmpty, data.count <= CaptureDisk.maxAttachment,
              data.starts(with: [0xff, 0xd8]), data.suffix(2) == Data([0xff, 0xd9]),
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetType(source) as String? == UTType.jpeg.identifier,
              CGImageSourceGetStatus(source) == .statusComplete,
              let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = props[kCGImagePropertyPixelWidth] as? Int,
              let height = props[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0, width <= 16384, height <= 16384,
              Int64(width) * Int64(height) <= 40_000_000,
              let image = CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary),
              image.width == width, image.height == height else { throw PhotoError.invalidJPEG }
        return (width, height)
    }

    func begin(source: PhotoSource, session: UUID = UUID(), sdkDeviceID: String? = nil) throws -> PhotoRequest {
        let request = PhotoRequest(id: UUID(), source: source, requestedAt: Self.timestamp(), appSessionID: session, sdkDeviceID: sdkDeviceID)
        var capture = LocalCapture()
        capture.id = request.id
        capture.photoRequest = request
        try disk.commit(capture)
        return request
    }

    /// Explicit request association prevents a callback being attributed to a new job.
    /// No UIImage round trip: exactly the delivered SDK data is attached.
    func receive(_ data: Data, for request: PhotoRequest) throws -> PhotoReceipt {
        let receivedAt = Self.timestamp()
        let (width, height) = try Self.dimensions(data)
        guard var capture = try disk.load().captures.first(where: { $0.id == request.id }),
              capture.photoRequest == request else { throw PhotoError.unknownRequest }
        if let receipt = capture.photoReceipt {
            guard receipt.sha256 == CaptureDisk.hash(data), receipt.bytes == data.count else { throw PhotoError.conflictingCallback }
            return try verify(request.id) // duplicate, including across store reopen
        }
        // A prior interrupted commit must be reconciled, not attached a second time.
        guard capture.attachments.isEmpty else { throw PhotoError.incomplete }
        let files = try FileManager.default.contentsOfDirectory(atPath: disk.folder(request.id).path)
        guard files.allSatisfy({ $0 == "capture.json" }) else { throw PhotoError.incomplete }
        capture = try disk.attach(data, name: "photo.jpg", contentType: "image/jpeg", to: capture, source: request.source)
        let receipt = PhotoReceipt(request: request, receivedAt: receivedAt, savedAt: Self.timestamp(),
                                   mime: "image/jpeg", width: width, height: height,
                                   bytes: data.count, sha256: CaptureDisk.hash(data))
        capture.photoReceipt = receipt
        capture = try disk.queue(capture)
        return try verify(capture.id)
    }

    /// Fresh manifest + fresh file read, also used after reopening the app/store.
    func verify(_ id: UUID) throws -> PhotoReceipt {
        guard let capture = try disk.load().captures.first(where: { $0.id == id }),
              capture.state == .queued, let receipt = capture.photoReceipt,
              capture.photoRequest == receipt.request, receipt.request.id == id,
              capture.attachments.count == 1, let file = capture.attachments.first else { throw PhotoError.incomplete }
        let data = try disk.read(file, in: id)
        let (width, height) = try Self.dimensions(data)
        guard receipt.mime == "image/jpeg", file.contentType == receipt.mime,
              file.source == receipt.request.source,
              receipt.bytes == data.count, receipt.sha256 == CaptureDisk.hash(data),
              receipt.width == width, receipt.height == height else { throw CaptureFailure.integrity }
        return receipt
    }
}
