# Photo capture development checkpoint

Status: Mac compilation verified; final offline XCTest passes (19/19) and DAT simulator camera-to-disk passes (20/20) with the explicit accessory-required simulator profile. Actual normal-process restart is now verified; bounded network observation is recorded, with packet-level attribution blocked by current privileges. Physical acceptance is not claimed. See the latest continuation below.
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
SDK 1.0.1 resolution, linking and simulator initialization were verified on 9 November 2026; mock discovery did not complete.

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
HS_META_SIMULATOR_PROFILE=accessory-required ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

The script prints Xcode/Swift versions and installed simulators, runs xcodebuild
test with local ad-hoc signing (CODE_SIGN_IDENTITY=-, empty DEVELOPMENT_TEAM), and restores the offline project after DAT
runs. It does not install/update Xcode, simulators or developer profiles.

The suite contains the original seven CaptureDisk tests, ten new photo pipeline
tests, basic controller-state tests and two DAT simulator integration tests
(official mock callback and denied permission). There are 19 eligible tests in
the offline variant and 20 in the DAT simulator variant. See the 9 November results below; the two official mock tests fail during discovery.

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
not claimed. SDK/package downloads during a build are not media uploads.

The original Mac-runner dependency is now resolved; see the 9 November results
and remaining configuration gate below. Milestone A is NOT yet accepted.

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


## Verified Mac results, 9 November 2026

PR #17 was checked out at `ebe4e664f0bd48716092686bafcbf16f6a10d4a0` into a new
local directory because the supplied workspace contained only an empty Git repository.
Existing PR #13 work and the dependent branch history were preserved.

Environment: macOS 26.6.2 (25G83), Xcode 27.1 (27A9275), Apple Swift 6.4
(swiftlang-6.4.0.34.1), iPhoneSimulator 27.1 SDK, iPhone 18 Pro / iOS 27.0 runtime.
iOS 27.0 and 27.1 simulator devices were available. No toolchain/runtime installed.

Commands (existing selected simulator UUID was supplied locally):

```sh
HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-deriveddata-offline ios/checks/run_simulator.sh SIMULATOR_UUID
HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-deriveddata ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

| Check | Verified result |
| --- | --- |
| Offline native compile/link | PASS |
| Offline XCTest, final source | PASS: 19 tests, zero failures, exit 0 |
| Original CaptureDisk tests | PASS: all seven, in both variants |
| Photo pipeline tests | PASS: all ten, including exact JPEG bytes/hash after fresh-store reopen |
| DAT 1.0.1 package resolution/compile/link | PASS; pinned revision unchanged |
| DAT final suite | FAILED: 20 tests executed; 18 passed, two failed (three assertions), exit 65 |
| Official mock photo callback | BLOCKED: no active wearable discovered within 20 seconds; no receipt |
| Mock denied permission | BLOCKED at discovery; test now requires actual permissionDenied, not any failure |
| Runner syntax / git whitespace | PASS |
| Actual process restart, runtime network trace, physical glasses, locked phone | NOT RUN |

The initial unsigned DAT run failed with SDK keychain error -34018. Local ad-hoc
simulator signing resolved it without accounts, certificates or provisioning.
Signing inside Documents then failed due to Finder/resource-fork metadata in build
output; a fresh temporary DerivedData directory resolved that failure. Runner now
accepts HS_META_DERIVED_DATA_PATH, disables parallel test clones and verbose failure
diagnostics (the initial diagnostic collection stalled). No source files or existing
build artifacts were deleted to work around metadata.

Mock lifecycle now retains its paired mock, explicitly configures initial permissions
per connection and reports a discovery-specific deadline. Tests clean up on throwing
setup, preserve SDK failure text and reject unrelated errors as proof of denial.
No test was skipped or converted to a pass. Final offline regression passed again.

The saved synthetic fixture is 32x24 JPEG / 742 bytes / SHA-256
`5096cb4a14663a04ce7aa7ad3274b16e40dc305ad51e7e8e7956e81c7667e0c3`.
The passing native pipeline test compares stored bytes against the input, then opens
a fresh CaptureDisk and verifies the receipt/hash. This proves native synthetic
persistence, not a DAT output or an actual process restart.

Local complete final logs: `/private/tmp/hs-meta-001-offline-final.log` and
`/private/tmp/hs-meta-001-dat-final.log`. Result bundles:
`/private/tmp/hs-meta-001-deriveddata-offline/Logs/Test/Test-HeySophie-2026.11.09_15-07-24-+0000.xcresult`
and `/private/tmp/hs-meta-001-deriveddata/Logs/Test/Test-HeySophie-2026.11.09_15-06-17-+0000.xcresult`.
Raw logs, simulator identities and generated SDK/build files are not committed.

### Remaining configuration gate

Observed failure: AutoDeviceSelector never publishes an active mock device under
the restricted Info-Meta.plist. The SDK emits CoreBluetooth connection/state warnings.
The pinned SDK CHANGELOG (0.9.0 Fixed) states mocks enforce the same Info.plist link
availability checks as real devices. Missing transport declarations are therefore a
supported hypothesis, not a proven sole cause. Mock discovery/callback and denied
permission are NOT accepted.

The brief explicitly requires reporting a mock configuration failure before broadening
privileges. Info-Meta.plist remains unchanged: no Bluetooth/local-network usage strings,
Bonjour services, external-accessory protocols or background modes were added. Both
telemetry opt-outs and complete file protection remain unchanged.

Next reviewable action: approve a simulator-only transport configuration experiment
in this same branch, comparing the exact pinned SDK/sample requirements for
NSBluetoothAlwaysUsageDescription, NSLocalNetworkUsageDescription, NSBonjourServices,
UISupportedExternalAccessoryProtocols and UIBackgroundModes. Record each minimum
required key and any runtime prompt before granting it; do not enable the physical
compile flag, enroll accounts, install software or touch the iPhone/glasses. A successful
mock test would still not authorize the physical milestone.

Reference for the unsigned-keychain failure and simulator ad-hoc signing:
https://github.com/meta/meta-wearables-dat-ios/issues/197
(use the issue discussion if the comment anchor changes).


## Verified simulator continuation, 9 November 2026, 15:43 GMT

Stephen supplied Zara's GO instruction for controlled simulator-only configuration
comparisons. The previous discovery blocker is resolved. See
[the complete per-key source table and controlled results](SIMULATOR_TRANSPORT.md).
Earlier failed results above remain historical evidence, not the current result.

Final offline suite: **19/19 PASS**, exit 0. Final DAT suite: **20/20 PASS**, exit 0.
Same SDK 1.0.1 revision, mock lifecycle, fixtures, 20-second bridge deadlines and
30-second XCTest waits. The separate generated simulator plist and compile/platform
guards fail closed for non-simulator builds. Original plists are unchanged.

Minimum successful added declarations: UISupportedExternalAccessoryProtocols
containing com.meta.ar.wearable and UIBackgroundModes containing only
external-accessory. Removing either fails discovery/selection. This mode was tested
only after the pinned binary's explicit validator requirement and unsuccessful
no-background comparisons demonstrated the need; it is not proof of actual
background execution. Bluetooth description/central mode reaches session creation
but fails camera-stream connection. Local-network, Bonjour, processing, audio and
Bluetooth-peripheral declarations are unnecessary for this successful mock path.
No system permission prompt was granted; no permissions were changed automatically.

The callback is actually received through photoDataPublisher. Returned JPEG: 901
bytes, 32x24; stored bytes equal callback bytes. A fresh CaptureDisk verifies the
receipt and an independent CryptoKit SHA-256 readback matches:
4636673a5769f5332119e1ecbb6f75aa3eee6c6d83c5ed9ef392bdff1e674dd3.
The unchanged input fixture is 742 bytes; the SDK mock encodes a different JPEG,
so no fixture-byte preservation claim is made. Denial testing now proves actual
camera permission denial after selection, no session creation, no request/callback
and no saved capture. Tests were strengthened, never skipped or weakened.

Both final log/result-bundle paths and reproduction commands are in the comparison
report. Full process termination/relaunch UI verification and runtime no-egress
tracing remain NOT RUN; native UI control could not bind the Simulator app. No
physical capture, phone installation, account change, software installation,
Railway access, expenditure or production merge/deployment occurred. The requested
compiled simulated camera-to-storage path is demonstrated; broader acceptance and
physical authorisation remain with Zara/Stephen.


## Normal app restart, privacy observation and hardware proposal — 9 November 2026

The app now passes a real termination/relaunch proof, not merely a fresh-store test.
The check exposed and fixed a missing framework runpath that XCTest had masked;
normal launch initially produced the crash dialogs reported by Stephen. No update,
reinstallation or Apple Report action was requested. The actual app process now
captures a DAT mock JPEG, is explicitly terminated and confirmed absent, and a new
process restores the same file, capture ID, source, receipt and hash. File inode,
mtime, bytes and manifest remain unchanged; screenshot confirms honest saved status.

The opt-in Debug/simulator-only process harness uses one process-wide owner, the
normal bridge and normal app store. It is not included in phone/release builds or
activated by ordinary launches. Initial idle/cancelled startup attempts are recorded
failures, not substituted passes. Effective built/installed telemetry opt-outs and
file protection remain unchanged.

Existing nettop/lsof observers recorded app-stopped, normal capture and storage-only
restore windows. No app-owned TCP/UDP flows or sampled sockets were observed;
macOS mDNSResponder/nsurlsessiond activity was distinguished by process executable
paths. Delegated/encrypted traffic cannot be conclusively attributed from these
counters. Packet capture failed at the OS privilege boundary; no sudo, permission
change, proxy/certificate/VPN or monitoring installation was attempted. This is
bounded observation, not zero-egress certification.

Final regressions after the app changes: offline **19/19 PASS**, DAT **20/20 PASS**.
Commands, private evidence locations, failures and exact observation limits:
[restart/network verification](RESTART_NETWORK_VERIFICATION.md).
First real photo [requirements and rollback proposal](PHYSICAL_PHOTO_PROPOSAL.md)
is prepared only. Actual phone identity/signing team and final physical transport
plist are explicit pre-install review inputs; no installation, account or Meta
setting change, physical grant/test, expenditure or production deployment occurred.
