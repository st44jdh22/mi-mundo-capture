import SwiftUI

struct PhotoProofScreen: View {
    @StateObject private var camera = MetaPhotoCamera()
    @Environment(\.scenePhase) private var phase
    var refreshOutbox: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("One photo, verified on this iPhone").font(.title2)
                    Text("Synthetic development. Physical glasses testing needs separate approval.")
                    Text(camera.status).font(.headline).accessibilityIdentifier("photoStatus")
                    Button("Save synthetic test photo") { camera.syntheticPhoto(); refreshOutbox() }
                        .buttonStyle(.borderedProminent).disabled(camera.busy || camera.streaming)
                    Button("Connect Meta simulator camera") { camera.connect() }
                        .buttonStyle(.bordered).disabled(camera.busy || camera.streaming)
                    Button("Capture one Meta test photo") { camera.capture() }
                        .buttonStyle(.bordered).disabled(!camera.streaming || camera.busy)
                    Button("Stop camera session") { camera.stop() }
                    if let receipt = camera.receipt {
                        Text("Source: \(receipt.request.source.rawValue)")
                        Text("Capture: \(receipt.request.id.uuidString)").textSelection(.enabled)
                        Text("\(receipt.width) × \(receipt.height) · \(receipt.mime) · \(receipt.bytes) bytes")
                        Text("Received: \(receipt.receivedAt)\nSaved: \(receipt.savedAt)")
                        Text("SHA-256: \(receipt.sha256)").font(.caption.monospaced()).textSelection(.enabled)
                        Button("Reopen and verify saved photo") { camera.verifySaved() }
                    }
                    if let error = camera.error { Text(error).foregroundStyle(.red) }
                    Text("No upload or Sophie connection. These local files are excluded from backup; deleting the app can lose them.")
                        .font(.footnote)
                }.padding()
            }.navigationTitle("Photo test")
        }
        .onOpenURL { camera.handleURL($0) }
        .task {
            camera.restoreLatest()
            #if DEBUG && HS_META_SIMULATOR_CONFIG && targetEnvironment(simulator)
            MetaPhotoCamera.startSimulatorProofIfRequested()
            #endif
        }
        .onChange(of: camera.receipt) { _, _ in refreshOutbox() }
        .onChange(of: phase) { _, state in
            if state == .background { camera.backgrounded() }
            if state == .active { camera.verifySaved() }
        }
        .onDisappear { camera.stop() }
    }
}
