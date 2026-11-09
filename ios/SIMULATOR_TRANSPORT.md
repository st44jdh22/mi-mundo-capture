# DAT 1.0.1 simulator transport comparison

Authorised 9 November 2026 by Stephen's Zara-to-Codex continuation.
This experiment does not authorise physical activity or system permission grants.

## Fixed evidence

- Binary package: official DAT 1.0.1, revision `0bd369298eef6a980ad0bdb6c8a5502f2c02a08c`; no SDK upgrade.
- [Pinned changelog](https://github.com/meta/meta-wearables-dat-ios/blob/0bd369298eef6a980ad0bdb6c8a5502f2c02a08c/CHANGELOG.md): mocks enforce the same plist-based Bluetooth/Wi-Fi link availability checks as hardware.
- [Fixed official CameraAccess plist](https://github.com/meta/meta-wearables-dat-ios/blob/bbae597cd1c748cd29b9375a1624a8d75b1c9e14/samples/CameraAccess/CameraAccess/Info.plist). This is the separately identified sample-source commit, not the binary release revision. The release checkout distributes frameworks and does not include this sample.
- Exact pinned Core simulator binary inspected read-only with `strings`; validation strings name the keys below. These strings establish checks exist, but do not prove which link is sufficient at runtime.

| Declaration | Exact value tested | Source and reason | Permission/prompt boundary |
| --- | --- | --- | --- |
| NSBluetoothAlwaysUsageDescription | Nonempty simulator-experiment explanation | Fixed sample; pinned binary checks nonempty text for BLE link availability | Declaration permits a description to appear if Bluetooth authorization is requested; it grants nothing. Stop at a prompt. |
| NSLocalNetworkUsageDescription | Nonempty simulator-experiment explanation | Fixed sample; pinned binary checks nonempty text for Wi-Fi link availability | May accompany a local-network prompt; no automatic grant. |
| NSBonjourServices | `_bonjour._tcp` | Exact fixed sample value; pinned binary checks nonempty services for Wi-Fi availability | Service declaration, not a permission grant; no preview/test server is started. |
| UISupportedExternalAccessoryProtocols | `com.meta.ar.wearable` | Exact pinned binary validation names the protocol for the accessory link. Fixed CameraAccess plist lacks it, so sample copying alone is insufficient evidence. | Declaration only; no physical accessory connected. |
| UIBackgroundModes | Only `external-accessory` in the successful profile; `bluetooth-central` in a separate BLE comparison | Pinned binary names `bluetooth-central` for BLE and `external-accessory` for accessory availability. The fixed sample also lists processing/audio/peripheral modes; those are not evidence of a foreground requirement. | Latest direct continuation permits a mode with demonstrated requirement. Only the exact modes named by the pinned validator were compared after no-background controls failed; none enabled physical builds. |

Background comparisons were introduced only after explicit pinned validator requirements and failed no-background controls established a concrete reason under the latest direct continuation. No audio/processing/peripheral mode was copied from the sample.

The separate generated plist is `ios/Generated/Info-Meta-Simulator.plist` and is
ignored by Git. The original offline and restricted DAT plists remain unchanged.
Generator profiles support only `iphonesimulator`; `HS_META_SIMULATOR_CONFIG` also
produces a compile error for any non-simulator destination. Neither generator nor
runner defines `HS_META_PHYSICAL_APPROVED`. Both telemetry opt-outs and complete
file protection remain unchanged.

## Controlled execution

```sh
HS_META_SIMULATOR_PROFILE=baseline HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-compare ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

Profiles: baseline (no added declarations), bluetooth, local-network, bonjour,
accessory, wifi (local-network + Bonjour), all-no-background (all four descriptions/protocols),
ble-required (Bluetooth description + central mode), accessory-mode-only (negative control),
accessory-required (Meta accessory protocol + external-accessory mode).
Transport comparisons use the same existing simulator, ad-hoc signing, SDK pin, mock lifecycle,
JPEG and video fixtures, 20-second bridge deadline and 30-second XCTest waits.
No simulator permission command, UI approval, device installation or account change
is part of the runner. Comparisons are serial; an early overlapped launch was
cancelled before comparison and excluded from evidence.

Sanitized `[DATProof]` events distinguish mock pairing, SDK device-list counts,
link/don/hinge/compatibility state, selector availability, permission result,
session creation/state, stream state, capture request, actual callback and saved
readback. Device identifiers and media contents are not logged. Synthetic callback
byte count/hash may be reported only after an actual callback.

Assertions remain strict: a discovery failure is not camera denial. A successful
photo must be `.datMock`, persist the callback bytes exactly, decode as JPEG at the
known dimensions, and match an independently computed CryptoKit SHA-256 after a
fresh store read. Actual process restart and runtime network tracing are separate
checks; neither can be inferred from this test.

## Results

The minimum successful added declaration set is:

```xml
<key>UISupportedExternalAccessoryProtocols</key>
<array><string>com.meta.ar.wearable</string></array>
<key>UIBackgroundModes</key>
<array><string>external-accessory</string></array>
```

It does **not** include Bluetooth usage descriptions, local-network/Bonjour,
`bluetooth-central`, audio, processing or peripheral background modes. The plist
mode satisfies the SDK's foreground transport validator; this test does not prove
background/locked-phone operation or authorize the mode on a physical device.

| Comparison | Result |
| --- | --- |
| Baseline, no added declarations | SDK device appears; disconnected/unknown state; no active selection |
| Bluetooth description alone | Same discovery/selection failure |
| Local-network description alone | Same failure |
| Bonjour service alone | Same failure |
| Accessory protocol alone, no mode | Same failure |
| Local-network + Bonjour | Same failure |
| All four descriptions/protocols, no modes | Same failure |
| Separate activation-after-SDK-discovery control, all declarations/no modes | Same failure; not promoted to default lifecycle |
| Bluetooth description + bluetooth-central | Discovery succeeds; genuine denied-camera test passes; session starts, camera stream fails with device-not-connected error |
| Meta accessory protocol + external-accessory | PASS: all 20 tests; actual JPEG callback and independent saved readback |
| External-accessory mode without protocol | Fails at disconnected link/selection; both minimum declarations necessary |

All no-background comparisons and the ordering control remain recorded failures,
not skipped tests. No deadline increased. The SDK's camera-permission mock was set
inside MockDeviceKit; it is not a new OS permission grant.

Successful callback: 901-byte JPEG, 32x24 pixels; independent saved SHA-256
`4636673a5769f5332119e1ecbb6f75aa3eee6c6d83c5ed9ef392bdff1e674dd3`.
The source JPEG fixture remains 742 bytes with its original digest. SDK mock JPEG
encoding changes the input; tests compare destination with the actual callback,
not with assumed unchanged fixture bytes. These are simulated glasses bytes.

No new permission prompt observed in checked simulator screens; no grant automation
or prompt approval executed. No runtime zero-egress claim is made.

Final verification (same Mac/Xcode/Swift/runtime as the 15:10 checkpoint):

- Offline: **19 tests, zero failures**, exit 0.
- DAT `accessory-required`: **20 tests, zero failures**, exit 0; repeated successful callback digest matches the first pass.
- Static validation: all ten profiles deterministic, exact added-key/mode sets verified, original values/telemetry opt-outs retained, simulator-only target/compile guard present, invalid option combinations rejected.
- Shell syntax and git whitespace checks pass. The original seven CaptureDisk and ten PhotoCapture tests remain intact.
- SDK emits duplicate Objective-C class warnings from its Camera/Mock binaries; these do not fail this suite, and vendor binaries were not patched.
- At this transport checkpoint, actual process-restart UI test and runtime no-egress trace were NOT RUN. The subsequent [restart/network report](RESTART_NETWORK_VERIFICATION.md) now verifies normal-process relaunch and bounded traffic observation, with packet-level attribution still blocked. Native UI automation was unavailable at that earlier checkpoint; the later supported simctl process-lifecycle proof closes the restart gap without a new permission.
- Physical glasses, locked phone, signing/installation to a phone, account changes and cloud delivery remain NOT RUN / outside authority.

Reproduce the successful path:

```sh
HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-continuation-offline ios/checks/run_simulator.sh SIMULATOR_UUID
HS_META_SIMULATOR_PROFILE=accessory-required HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-compare ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

The original `--dat` command without a simulator profile intentionally retains the
restricted baseline; it is not the successful transport configuration. The optional
`HS_META_DEFER_MOCK_ACTIVATION=1` reproduces the separate failed ordering control;
it is not enabled for the successful path. SDK, fixtures and timeouts remain fixed.

Final local logs:
`/private/tmp/hs-meta-001-continuation-offline.log` and
`/private/tmp/hs-meta-001-continuation-dat.log`.
Result bundles:
`/private/tmp/hs-meta-001-continuation-offline/Logs/Test/Test-HeySophie-2026.11.09_15-41-13-+0000.xcresult`
and `/private/tmp/hs-meta-001-compare/Logs/Test/Test-HeySophie-2026.11.09_15-42-13-+0000.xcresult`.

Comparison local logs use
`/private/tmp/hs-meta-001-profile-PROFILE.log`; raw logs/screenshots are not committed.
