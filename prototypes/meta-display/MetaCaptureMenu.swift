// HS-META-001 native Display UI spike. PREPARED; not compiled in this Linux environment.
// Requires Meta DAT MWDATDisplay in an approved iOS host. No permissions,
// connection, capture, upload or credential changes occur in this file.
import MWDATDisplay

enum MetaCaptureMenu {
    /// Call only after the existing host observes DisplayState.started.
    /// The host supplies real capture lifecycle handlers; these are not fake SDK APIs.
    static func capture(
        photo: @escaping @Sendable () -> Void,
        video: @escaping @Sendable () -> Void,
        audio: @escaping @Sendable () -> Void
    ) -> FlexBox {
        FlexBox(direction: .column, spacing: 12) {
            Text("Hey Sophie", style: .heading)
            Text("Choose a capture", style: .meta, color: .secondary)
            ButtonGroup {
                Button(label: "Photo", onClick: photo).actionRole(.primary)
                Button(label: "Video", onClick: video)
                Button(label: "Audio", onClick: audio)
            }
        }.padding(24).background(.card)
    }

    /// Reach this screen only after the host independently reads its local media.
    static func readyToSend(send: @escaping @Sendable () -> Void) -> FlexBox {
        FlexBox(direction: .column, spacing: 12) {
            Text("Saved on your phone", style: .heading)
            Text("Not uploaded", style: .meta, color: .secondary)
            ButtonGroup {
                Button(label: "Send", onClick: send).actionRole(.primary)
            }
        }.padding(24).background(.card)
    }

    /// The host must provide state-grounded wording, never infer success from a click.
    static func status(_ message: String) -> FlexBox {
        FlexBox(direction: .column, spacing: 12) {
            Text("Hey Sophie", style: .heading)
            Text(message, style: .meta, color: .secondary)
        }.padding(24).background(.card)
    }
}
