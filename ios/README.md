# Hey Sophie! for iPhone: native capture v0.1

First native SwiftUI milestone in the existing Mi Mundo/HeySophie repository.
The browser capture app, Python intake service and draft Post Office PR stack are
unchanged. This is a phone-local capture client, not a new institutional task system.

## Current behaviour

- Light turquoise conversation-style composer; write a message, choose photos,
  take a camera photo or import documents from Files.
- Record an AAC voice note for up to two minutes. Stop keeps the recording;
  leaving the foreground also stops it. Speech transcription is not connected.
- Save text drafts on change; save attachment bytes with SHA-256 and readback
  before committing their manifest. Stable capture and attachment UUIDs survive
  reopening. Queued messages are immutable.
- Outbox always says **NOT UPLOADED** in red. There is no success state, network
  request, model call, credential field, endpoint or automatic retry promise.
  “Save to Outbox” means saved on this phone only.
- Corrupt manifests do not silently reset other work. Missing/corrupt files,
  unlisted attachment files and interrupted recording files produce warnings.
  The recovery screen can export retained files through the iOS share sheet.
- An empty note cannot queue. Limit: 20 attachments, 20 MiB per attachment,
  50 MiB per message, 20,000 text characters per queued message. Longer drafts
  remain saved intact with an explicit prompt to split them before queuing.

App files use complete iOS file protection, with atomic manifest replacement and
independent readback. Device lock/read errors are surfaced; no background uploader
is claimed. The capture directory is excluded from automatic device/iCloud backup
until a reviewed backup policy exists. **Deleting the app loses its local files.**
Export is not proof of independent backup/restore. Flash power-loss behaviour and
actual iOS data-protection behaviour require device tests.

Photos are the exact representation returned by the system picker, not a guarantee
of original sensor bytes or preserved camera metadata. When the camera supplies
only UIImage, a full-quality JPEG capture representation is created and labelled
as a camera capture. File imports preserve supplied bytes. Video recording,
attachment removal, audio playback and full-message archive export are not in v0.1.

## Open on a Mac

The checked-in `HeySophie.xcodeproj` has an app target, an XCTest target and a
shared `HeySophie` scheme. No package manager or paid SDK is required. iOS 17+;
iPhone only. Open `ios/HeySophie.xcodeproj` in Xcode. Select a simulator and build.
For a physical iPhone, select your own signing team in the app target; the bundle
identifier is a development placeholder and may need changing. No Apple account,
signing certificate, provisioning profile or TestFlight submission was created.

Regenerate the project after changing the source list:

```sh
python3 ios/generate_project.py
```

Build and run tests on an available iPhone simulator on a Mac:

```sh
xcodebuild -list -project ios/HeySophie.xcodeproj
xcodebuild -showdestinations -project ios/HeySophie.xcodeproj -scheme HeySophie
# Replace the placeholder with an available simulator UUID from the preceding command.
xcodebuild -project ios/HeySophie.xcodeproj -scheme HeySophie \
  -destination 'platform=iOS Simulator,id=SIMULATOR_UUID' \
  -derivedDataPath ios/DerivedData CODE_SIGNING_ALLOWED=NO test
```

## Validation evidence

Prepared on 22 October 2026 in Linux. **No Swift compiler, Xcode, iOS SDK or
simulator is installed here. The native app has NOT been compiled or run.**

Executed here:

- Existing Python receiver/boundary regressions: 9 passed.
- Existing JavaScript capture-client regressions: 7 passed.
- Info.plist and shared scheme XML parsing passed.
- Standard-library Xcode project generator executed and regenerated deterministically.
- Git whitespace check passed.

The existing 16 regression passes establish that the unchanged browser/backend
tests still work; they do not validate the new Swift app.

Seven meaningful XCTest cases are supplied but **not executed**: draft/original
restart, stable queue identity/replay, tamper hold, corrupt-job isolation,
oversize rejection without mutation, interrupted-recording retention and empty-job
rejection. A Mac build/test and physical iPhone acceptance are required before
calling this usable or ready to install.

## iPhone acceptance

1. Type a note, close and reopen; exact draft returns.
2. Attach a harmless photo, Files document and recording; compare exported bytes
   and digest with the saved manifest. Confirm camera representation semantics.
3. Deny microphone/camera, cancel Files/Photos, interrupt audio, hit the recording
   limit, lock the device and simulate full disk; never display a false save/upload.
4. Queue two separate messages, force quit and reopen; original IDs/files remain.
5. Inject a corrupt manifest, tampered/missing attachment and unfinished Incoming
   file in the simulator. Keep unaffected work and export recovery files.
6. Test VoiceOver, Dynamic Type, keyboard, safe areas and small-screen layout.
7. Confirm no app-originated network calls and no green uploaded/success state.

## Next integration milestone

Implement a versioned native package/export adapter compatible with the existing
v0.3 ZIP manifest and receiver contract in `integration/validate_job.py`. The
current local JSON is NOT submitted directly to either the ZIP receiver or the
synthetic Chef endpoint. Preserve capture ID and frozen package digest across
retries. Reuse `/v1/jobs/{id}` lookup-before-PUT and independent receipt readback
from `integration/capture-client.mjs`; keep `RECEIVED_TEST_ONLY` separate from
durable original filing and departmental completion. Apply the reviewed
authentication/storage release gates before granting access to real data.

Only then add approved file-backed background transfer, bounded retries and
visible policy/permission holds. The supplied upload-status brief calls for an
obvious failure warning, retry feedback and confirmed success. It does not
justify infinite retry, retrying policy denials or success from a PUT response.

Connect the owned Inbox and authenticated Chef round trip through the existing
PR #11 stack when hosted interfaces and principals are accepted. General AI chat,
transcription, true department replies, notifications, approved cloud backup and
TestFlight remain follow-ups. No deployment, production merge or paid service
activation is part of this source milestone.
