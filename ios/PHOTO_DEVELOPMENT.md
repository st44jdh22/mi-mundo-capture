# Photo capture development checkpoint

Status: source prepared, host checks passed; native build and simulator acceptance blocked.
Based on PR #13 at `405c8495169b4738d0b9d2ab46e60159ca868077`.
This is a dependent draft, not an installable application or a physical-glasses proof.

## Changes

The existing SwiftUI app and CaptureDisk are reused. The Photo test screen saves
one generated JPEG, reopens a new store and displays a local receipt with source,
request UUID, receive/save timestamps in UTC, dimensions, MIME, byte count and SHA-256.
After app reopening it reads and verifies the latest photo request again. Failed
or incomplete requests remain available for recovery; they are not silently retried.

The photo pipeline decodes JPEG content, bounds image dimensions and file size,
preserves delivered bytes, uses the existing atomic/complete-protection writes and
commits a receipt through the existing queued capture. A duplicate callback for
the same request returns the existing verified receipt; conflicting bytes, unknown
requests, corrupt images and interrupted saves are held. A fresh DAT stream is
required for each request, since PhotoData does not carry an app request UUID.
Teardown cancels listeners/deadlines and ignores late callbacks. Source kinds are
syntheticFixture, datMock, datCameraStream and localPhoneImport. Old v1 manifests
remain readable; missing legacy source is unknown, not retrospectively inferred.
SDK device identity, when exposed, stays in the local manifest only. appSessionID
is an app correlation UUID, not an SDK session identity or device capture time.

The offline build has no SDK package dependency. `generate_project.py --dat`
regenerates the SAME Xcode project with HS_META_DAT and exact Meta DAT 1.0.1
Core/Camera/MockDevice products. Package.resolved pins release commit
`0bd369298eef6a980ad0bdb6c8a5502f2c02a08c`, independently checked against the official tag.
The 1.0.1 Core/Camera Swift interfaces were inspected for the actual session,
permission, listener and PhotoData APIs. Sample/reference source was inspected at
`bbae597cd1c748cd29b9375a1624a8d75b1c9e14`; this is distinct from the binary release tag.
No SDK resolution, download, linking or execution has been validated here.

In the DAT simulator variant, Connect configures the official mock Display glasses
with the fabricated JPEG and a silent preview video. It then uses device discovery,
permission check, DeviceSession, addCamera, stream.capturePhoto(.jpeg) and
photoDataPublisher. The callback's data is persisted directly, without UIImage
re-encoding. No separate glasses UI, display SDK, audio or upload adapter is added.

Physical operation is blocked in the checked-in configurations. Registration,
permission and connection source is prepared behind the undefined
HS_META_PHYSICAL_APPROVED flag; do not enable it as a workaround. No device
installation, account change or physical permission grant has occurred.

## Run on an authorised Mac

The current official CameraAccess sample specifies Xcode 26.4+, Swift 6.3+ and
iOS 17.2+. Both generated variants target iOS 17.2; Swift language mode remains 5
for the original app. That language mode is distinct from the required compiler
version. Verify the actual compiler/SDK compatibility when resolving 1.0.1.

Use an existing available simulator UUID (no signing or device installation):

```sh
xcodebuild -showdestinations -project ios/HeySophie.xcodeproj -scheme HeySophie
ios/checks/run_simulator.sh SIMULATOR_UUID
ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

The script prints Xcode/Swift versions and installed simulators, runs xcodebuild
test with CODE_SIGNING_ALLOWED=NO, and restores the offline project after DAT
runs. It does not install/update Xcode, simulators or developer profiles.

The suite contains the original seven CaptureDisk tests, ten new photo pipeline
tests, basic controller-state tests and two DAT simulator integration tests
(official mock callback and denied permission). There are 19 eligible tests in
the offline variant and 20 in the DAT simulator variant. NONE have run here.
The official mock tests are prepared, not an independently validated mock workflow.

Host-only checks (Python with Pillow and ffprobe already available):

```sh
python3 ios/checks/verify_artifacts.py
python3 -m unittest discover -s integration -v
node --test integration/test_capture_client.mjs
```

## Verified results, 8 November 2026

| Check | Result | Limit |
| --- | --- | --- |
| JPEG decode/content/dimensions/byte length/hash | PASS | Pillow host read, not Swift file readback |
| Preview video | PASS | Generated silent 32x24 video, no audio track |
| Both plist privacy settings, project graphs/resources/scheme | PASS | Static checks, not Xcode parsing/compilation |
| Project generation (offline and DAT) | PASS | Deterministic in isolated temporary copies |
| Existing Python regression suite | PASS, 9 tests | Unchanged receiver/validator, not native app |
| Existing JS regression suite | PASS, 7 tests | Unchanged transport client, not native app |
| xcodebuild project inspection | BLOCKED, exit 127 | Linux: xcodebuild: command not found |
| Simulator runner preflight | BLOCKED, exit 2 | Neither Xcode nor xcrun installed |
| Swift/XCTest and actual app restart | NOT RUN | No macOS/iOS runner |
| Official SDK mock, denied permission, no-egress observation | NOT RUN | Requires native execution |
| Physical glasses photo and locked-phone operation | NOT RUN | Separate approval and witnessed test required |

Fixture: 32x24 JPEG, 742 bytes, SHA-256
`5096cb4a14663a04ce7aa7ad3274b16e40dc305ad51e7e8e7956e81c7667e0c3`.
This is a host-verified input, NOT proof of output from the iPhone app.

## Privacy and next hold point

Both plists explicitly opt out of SDK Analytics and CrashReporting. The offline
variant retains the original phone capture purpose strings. The DAT variant
shows only the photo test screen and removes phone camera/mic/library strings;
it declares no Bluetooth/local-network/background modes. Official mock operation
under these restricted settings still requires the simulator check. If DAT
requires further transport settings even for mocks, report the exact failure;
do not broaden privileges silently. The synthetic persistence boundary contains
no upload path. No network trace was captured, so zero SDK/system telemetry is
not claimed. SDK/package downloads during a future build are not media uploads.

Next: run the offline simulator suite on a suitable existing Mac, then resolve
and run the DAT mock variant. Fix any native/compiler/mock failures before
seeking a physical installation decision. Milestone A is NOT yet accepted.

Before a physical test, review the exact app ID `app.heysophie.capture.photodev`,
Mac/Xcode/iPhone/glasses versions, existing pairing state, signing route, Meta
Developer Mode and registration/permission redirects. Document the minimum
DAT transport plist requirements with platform security review and explicit
owner approval; no background entitlement or file-protection change is assumed.
Enable the held source path only within that approved revision. The first live
photo must be foregrounded, non-sensitive, visibly checked and independently
reopened/hashed. Test locked-phone operation later as a separate gate.
Rollback is to stop the session and, only as approved, remove the development
app/new grants while verifying existing pairing and capture still work. Retain
unsent files first. No app uninstall, unpairing or device reset is part of this PR.

Official references:
- https://github.com/meta/meta-wearables-dat-ios/blob/1.0.1/Package.swift
- https://github.com/meta/meta-wearables-dat-ios/blob/main/samples/CameraAccess/README.md
- https://github.com/meta/meta-wearables-dat-ios/blob/main/samples/CameraAccess/CameraAccess/ViewModels/CameraViewModel.swift
