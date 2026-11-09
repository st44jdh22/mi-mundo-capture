#if HS_META_SIMULATOR_CONFIG && !targetEnvironment(simulator)
#error("Transport experiment configuration is simulator-only")
#endif
import Foundation
import Combine

/// SDK-free build uses the identical photo persistence boundary with a fixture.
/// DAT linkage is an explicit generator option; no SDK config at app launch.
@MainActor
final class MetaPhotoCamera: ObservableObject {
    @Published private(set) var status = "READY"
    @Published private(set) var receipt: PhotoReceipt?
    @Published private(set) var error: String?
    @Published private(set) var streaming = false
    @Published private(set) var busy = false
    private var pipeline: PhotoCapturePipeline?
    private var bridge: DATPhotoBridge?
    #if DEBUG && HS_META_SIMULATOR_CONFIG && targetEnvironment(simulator)
    private var simulatorConnectionRequested = false
    private var simulatorFailureEvents: [String] = []
    private static var simulatorProofTask: Task<Void, Never>?
    #endif

    private func store() throws -> PhotoCapturePipeline {
        if let pipeline { return pipeline }
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                   appropriateFor: nil, create: true)
        let result = PhotoCapturePipeline(disk: try CaptureDisk(root: support.appendingPathComponent("HeySophieCaptures", isDirectory: true)))
        pipeline = result
        return result
    }

    func syntheticPhoto() {
        guard !busy, bridge == nil else { return }
        busy = true; receipt = nil; error = nil; status = "CAPTURING"
        defer { busy = false }
        do {
            guard let url = Bundle.main.url(forResource: "synthetic-photo", withExtension: "jpg") else { throw PhotoError.invalidJPEG }
            let pipeline = try store()
            let request = try pipeline.begin(source: .syntheticFixture)
            status = "SAVING"
            _ = try pipeline.receive(Data(contentsOf: url), for: request)
            // Construct a new store to verify persistence, not in-memory receipt state.
            let reopened = PhotoCapturePipeline(disk: try CaptureDisk(root: pipeline.disk.root))
            receipt = try reopened.verify(request.id)
            status = Self.savedStatus
        } catch { fail(error) }
    }

    func verifySaved() {
        guard let id = receipt?.request.id else { return }
        do { receipt = try store().verify(id); error = nil; status = Self.savedStatus }
        catch { fail(error) }
    }

    func restoreLatest() {
        guard !busy, bridge == nil else { return }
        do {
            let pipeline = try store()
            if let capture = try pipeline.disk.load().captures.last(where: { $0.photoRequest != nil }) {
                receipt = try pipeline.verify(capture.id)
                error = nil
                status = Self.savedStatus
            }
        } catch { fail(error) }
    }

    func connect() {
        guard !busy, bridge == nil else { return }
        #if DEBUG && HS_META_SIMULATOR_CONFIG && targetEnvironment(simulator)
        simulatorConnectionRequested = true
        #endif
        error = nil; receipt = nil; busy = true; status = "CONNECTING"
        do {
            let driver = try DATPhotoBridge(pipeline: store())
            driver.onReady = { [weak self] in
                self?.busy = false; self?.streaming = true; self?.status = "READY"
            }
            driver.onSaving = { [weak self] in self?.status = "SAVING" }
            driver.onSaved = { [weak self] receipt in
                self?.receipt = receipt; self?.busy = false; self?.status = Self.savedStatus
                self?.streaming = false
                self?.bridge?.stop(); self?.bridge = nil
            }
            driver.onFailure = { [weak self] error in self?.fail(error) }
            bridge = driver
            try driver.connect()
        } catch { stop(); fail(error) }
    }

    func capture() {
        guard streaming, !busy else { return }
        busy = true; receipt = nil; error = nil; status = "CAPTURING"
        do { try bridge?.capture() }
        catch { fail(error) }
    }

    func stop() {
        bridge?.stop(); bridge = nil; busy = false; streaming = false
        if receipt == nil { status = "READY" }
    }

    func backgrounded() {
        let interrupted = bridge != nil
        stop()
        if interrupted, receipt == nil { fail(PhotoError.interrupted) }
    }

    func handleURL(_ url: URL) {
        bridge?.handleURL(url)
    }

    private func fail(_ error: Error) {
        #if DEBUG && HS_META_SIMULATOR_CONFIG && targetEnvironment(simulator)
        simulatorFailureEvents = bridge?.diagnosticEvents ?? []
        #endif
        bridge?.stop(); bridge = nil
        busy = false; streaming = false; receipt = nil
        self.error = error.localizedDescription; status = "FAILED"
    }

    #if DEBUG && HS_META_SIMULATOR_CONFIG && targetEnvironment(simulator)
    /// Explicit CLI-only normal-process proof. Never compiled for a phone build.
    /// Does not configure the SDK in restore mode and never grants permissions.
    static func startSimulatorProofIfRequested() {
        guard simulatorProofTask == nil,
              let mode = ProcessInfo.processInfo.environment["HS_META_PROOF_MODE"],
              ["capture", "restore"].contains(mode) else { return }
        // One process-wide owner, independent of SwiftUI view reconciliation.
        // Uses the normal bridge and app store, not XCTest or a replacement fixture.
        simulatorProofTask = Task { @MainActor in
            let camera = MetaPhotoCamera()
            camera.restoreLatest()
            await camera.runSimulatorProofIfRequested()
        }
    }

    private func runSimulatorProofIfRequested() async {
        guard let mode = ProcessInfo.processInfo.environment["HS_META_PROOF_MODE"],
              ["capture", "restore"].contains(mode) else { return }
        do {
            if mode == "capture" {
                connect()
                for _ in 0..<300 {
                    if status == "FAILED" { throw PhotoError.interrupted }
                    if receipt != nil { break }
                    if streaming && !busy { capture() }
                    try await Task.sleep(for: .milliseconds(100))
                }
            }
            let current = try verifiedCurrentReceipt()
            let pipeline = try store()
            guard let capture = try pipeline.disk.load().captures.first(where: { $0.id == current.request.id }),
                  let attachment = capture.attachments.first else { throw PhotoError.incomplete }
            struct Snapshot: Encodable {
                let processID: Int32
                let mode: String
                let sdkConnectionRequested: Bool
                let receipt: PhotoReceipt
                let relativeFile: String
                let verifiedAt: String
            }
            let snapshot = Snapshot(processID: ProcessInfo.processInfo.processIdentifier, mode: mode,
                                    sdkConnectionRequested: simulatorConnectionRequested, receipt: current,
                                    relativeFile: pipeline.disk.folder(current.request.id).lastPathComponent + "/" + attachment.filename,
                                    verifiedAt: PhotoCapturePipeline.timestamp())
            try writeSimulatorProof(JSONEncoder().encode(snapshot), name: mode)
            print("[DATProof] process-proof mode=\(mode) verified=true bytes=\(current.bytes) sha256=\(current.sha256)")
        } catch {
            // Failure is a report, never a fabricated receipt or automatic recapture.
            let report: [String: Any] = ["mode": mode, "failed": "true", "reason": self.error ?? error.localizedDescription,
                                         "events": simulatorFailureEvents]
            if let bytes = try? JSONSerialization.data(withJSONObject: report) { try? writeSimulatorProof(bytes, name: mode) }
        }
    }

    private func verifiedCurrentReceipt() throws -> PhotoReceipt {
        guard let receipt else { throw PhotoError.incomplete }
        return try store().verify(receipt.request.id)
    }

    private func writeSimulatorProof(_ bytes: Data, name: String) throws {
        let support = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                   appropriateFor: nil, create: true)
        var folder = support.appendingPathComponent("HSPhotoProof", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try folder.setResourceValues(values)
        try bytes.write(to: folder.appendingPathComponent(name + ".json"), options: [.atomic, .completeFileProtection])
    }
    #endif

    static let savedStatus = "SAVED LOCALLY · NOT BACKED UP · NOT UPLOADED"
}

#if HS_META_DAT
import MWDATCore
import MWDATCamera
#if targetEnvironment(simulator)
import MWDATMockDevice
#endif

/// Built against official 1.0.1. Physical operation remains approval-gated.
/// One request per stream lifetime prevents late duplicate data being attributed
/// to another request (PhotoData has no app request UUID).
@MainActor
final class DATPhotoBridge {
    var onReady: (() -> Void)?
    var onSaving: (() -> Void)?
    var onSaved: ((PhotoReceipt) -> Void)?
    var onFailure: ((Error) -> Void)?
    private let pipeline: PhotoCapturePipeline
    private var selector: AutoDeviceSelector?
    private var session: DeviceSession?
    private var camera: Camera?
    private var request: PhotoRequest?
    private let tokens = ListenerTokenBag()
    private var discovery: Task<Void, Never>?
    private var deadline: Task<Void, Never>?
    private var stopped = false
    private var configured = false
    private var streamHasStarted = false
    #if targetEnvironment(simulator)
    private var mockActivation: Task<Void, Never>?
    private var mockGlasses: (any MockGlasses)?
    private(set) var lastPhotoCallbackData: Data?
    #endif

    private var observedDevices = Set<DeviceIdentifier>()
    private(set) var diagnosticEvents: [String] = []
    private func trace(_ event: String) {
        #if targetEnvironment(simulator)
        diagnosticEvents.append(event)
        print("[DATProof] \(event)") // stages/counts only: never device IDs or media
        #endif
    }

    init(pipeline: PhotoCapturePipeline) throws { self.pipeline = pipeline }

    func connect(mockPermissionGranted: Bool = true) throws {
        #if targetEnvironment(simulator)
        do { try Wearables.configure() }
        catch WearablesError.alreadyConfigured { /* same process, another mock test/session */ }
        configured = true
        trace("configured")
        MockDeviceKit.shared.enable(config: MockDeviceKitConfig(initialPermissionsGranted: mockPermissionGranted))
        let mock = try MockDeviceKit.shared.pairGlasses(model: .metaRayBanDisplay)
        mockGlasses = mock
        trace("mock-paired count=\(MockDeviceKit.shared.pairedDevices.count)")
        Wearables.shared.addDevicesListener { [weak self] devices in
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                self.trace("sdk-devices count=\(devices.count)")
                for id in devices {
                    if let device = Wearables.shared.deviceForIdentifier(id) {
                        self.trace("device link=\(device.linkState) don=\(device.donState) hinge=\(device.hingeState) compatibility=\(device.compatibility())")
                        if self.observedDevices.insert(id).inserted {
                            device.addDeviceStateListener { [weak self] state in
                                Task { @MainActor in
                                    guard let self, !self.stopped else { return }
                                    self.trace("device-state link=\(state.linkState) don=\(state.donState) hinge=\(state.hingeState) compatibility=\(state.compatibility)")
                                }
                            }.store(in: self.tokens)
                        }
                    }
                }
            }
        }.store(in: tokens)
        guard let image = Bundle.main.url(forResource: "synthetic-photo", withExtension: "jpg"),
              let video = Bundle.main.url(forResource: "synthetic-preview", withExtension: "mp4") else { throw PhotoError.invalidJPEG }
        mock.services.camera.setCapturedImage(fileURL: image)
        mock.services.camera.setCameraFeed(fileURL: video)
        selector = AutoDeviceSelector(wearables: Wearables.shared)
        #if HS_META_DEFER_MOCK_ACTIVATION
        // Separate ordering control; the transport comparisons use the original order.
        mockActivation = Task { [weak self] in
            for await devices in Wearables.shared.devicesStream() {
                guard !Task.isCancelled, let self, !self.stopped else { return }
                if devices.contains(mock.deviceIdentifier) {
                    self.trace("activation-after-sdk-discovery")
                    mock.powerOn(); mock.unfold(); mock.don()
                    self.trace("mock-powered-unfolded-donned")
                    return
                }
            }
        }
        #else
        mock.powerOn(); mock.unfold(); mock.don()
        trace("mock-powered-unfolded-donned")
        #endif
        #elseif HS_META_PHYSICAL_APPROVED
        // Prepared only. The checked-in generator never defines this flag.
        do { try Wearables.configure() }
        catch WearablesError.alreadyConfigured {}
        configured = true
        guard Wearables.shared.registrationState == .registered else { throw DATBuildError.hardwareHold }
        selector = AutoDeviceSelector(wearables: Wearables.shared)
        #else
        throw DATBuildError.hardwareHold
        #endif
        discovery = Task { [weak self] in
            guard let self, let selector = self.selector else { return }
            for await device in selector.activeDeviceStream() {
                guard !Task.isCancelled, !self.stopped else { return }
                self.trace("selector active=\(device != nil)")
                if device != nil {
                    do { try await self.startSession() }
                    catch { self.onFailure?(error) }
                    return
                }
            }
        }
        startDeadline()
    }

    /// Prepared for a separately approved physical configuration; never called
    /// by connect() in this build. No automatic permission redirect.
    func registerAfterPhysicalApproval() async throws {
        #if HS_META_PHYSICAL_APPROVED && !targetEnvironment(simulator)
        do { try Wearables.configure() }
        catch WearablesError.alreadyConfigured {}
        configured = true
        try await Wearables.shared.startRegistration()
        #else
        throw DATBuildError.hardwareHold
        #endif
    }

    func requestCameraPermissionAfterPhysicalApproval() async throws {
        #if HS_META_PHYSICAL_APPROVED && !targetEnvironment(simulator)
        guard try await Wearables.shared.requestPermission(.camera) == .granted else { throw PhotoError.permissionDenied }
        #else
        throw DATBuildError.hardwareHold
        #endif
    }

    func handleURL(_ url: URL) {
        guard configured, url.scheme == "heysophie-meta-dev",
              let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              parts.queryItems?.contains(where: { $0.name == "metaWearablesAction" }) == true else { return }
        Task { [weak self] in
            do { _ = try await Wearables.shared.handleUrl(url) }
            catch { self?.onFailure?(error) }
        }
    }

    private func startSession() async throws {
        guard let selector, !stopped else { return }
        let permission = try await Wearables.shared.checkPermissionStatus(.camera)
        trace("camera-permission granted=\(permission == .granted)")
        guard permission == .granted else { throw PhotoError.permissionDenied }
        let session = try Wearables.shared.createSession(deviceSelector: selector)
        self.session = session
        trace("session-created")
        session.errorPublisher.listen { [weak self] error in
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                self.onFailure?(error)
            }
        }.store(in: tokens)
        session.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                self.trace("session-state \(state)")
                if state == .started {
                    do { try self.startCamera() } catch { self.onFailure?(error) }
                } else if state == .stopped || state == .paused {
                    self.onFailure?(PhotoError.interrupted)
                }
            }
        }.store(in: tokens)
        try session.start()
    }

    private func startCamera() throws {
        guard camera == nil, let session, session.state == .started else { return }
        guard let camera = try session.addCamera(config: StreamConfiguration(videoCodec: .raw, resolution: .low, frameRate: 24)) else { throw PhotoError.interrupted }
        self.camera = camera
        trace("camera-added")
        camera.stream.errorPublisher.listen { [weak self] error in
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                self.onFailure?(error)
            }
        }.store(in: tokens)
        camera.stream.statePublisher.listen { [weak self] state in
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                self.trace("stream-state \(state)")
                if state == .streaming {
                    self.streamHasStarted = true
                    self.deadline?.cancel(); self.onReady?()
                } else if self.streamHasStarted && (state == .paused || state == .stopped) {
                    self.onFailure?(PhotoError.interrupted)
                }
            }
        }.store(in: tokens)
        camera.stream.start()
    }

    func capture() throws {
        guard request == nil, let camera, !stopped else { throw PhotoError.incomplete }
        #if targetEnvironment(simulator)
        let origin = PhotoSource.datMock
        #else
        let origin = PhotoSource.datCameraStream
        #endif
        let request = try pipeline.begin(source: origin, sdkDeviceID: session?.deviceId)
        self.request = request
        trace("capture-requested")
        camera.stream.photoDataPublisher.listen { [weak self] photo in
            let bytes = photo.data
            Task { @MainActor in
                guard let self, !self.stopped else { return }
                do {
                    #if targetEnvironment(simulator)
                    self.lastPhotoCallbackData = bytes
                    #endif
                    self.trace("photo-callback bytes=\(bytes.count)")
                    self.onSaving?()
                    let receipt = try self.pipeline.receive(bytes, for: request)
                    self.deadline?.cancel()
                    self.trace("saved-verified bytes=\(receipt.bytes)")
                    self.onSaved?(receipt)
                    self.stop()
                } catch { self.onFailure?(error); self.stop() }
            }
        }.store(in: tokens)
        guard camera.stream.capturePhoto(format: .jpeg) else { throw PhotoError.interrupted }
        startDeadline()
    }

    private func startDeadline() {
        deadline?.cancel()
        deadline = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(20)) } catch { return }
            guard let self, !self.stopped else { return }
            self.trace("deadline sdk-devices=\(Wearables.shared.devices.count) selected=\(self.selector?.activeDevice != nil) session=\(self.session != nil) camera=\(self.camera != nil)")
            self.onFailure?(self.session == nil ? DATBuildError.discoveryTimedOut : PhotoError.interrupted)
            self.stop()
        }
    }

    func stop() {
        guard !stopped else { return }
        stopped = true; deadline?.cancel(); discovery?.cancel()
        tokens.clear(); camera?.stop(); session?.stop()
        camera = nil; session = nil; selector = nil
        #if targetEnvironment(simulator)
        mockActivation?.cancel(); mockActivation = nil
        mockGlasses = nil
        if configured { MockDeviceKit.shared.disable() }
        #endif
    }
}
#else
@MainActor
final class DATPhotoBridge {
    var onReady: (() -> Void)?
    var onSaving: (() -> Void)?
    var onSaved: ((PhotoReceipt) -> Void)?
    var onFailure: ((Error) -> Void)?
    init(pipeline: PhotoCapturePipeline) throws {}
    func connect() throws { throw DATBuildError.notLinked }
    func capture() throws { throw DATBuildError.notLinked }
    func stop() {}
    func handleURL(_ url: URL) {}
}
#endif

enum DATBuildError: LocalizedError {
    case notLinked, hardwareHold, discoveryTimedOut
    var errorDescription: String? {
        switch self {
        case .discoveryTimedOut: return "No active wearable was discovered before the 20-second deadline. Check the approved DAT transport configuration; no photo was captured or saved."
        case .notLinked: return "Meta SDK is disabled in this offline build. Use the synthetic photo test."
        case .hardwareHold: return "Physical glasses testing is held for separate installation and permission approval."
        }
    }
}
