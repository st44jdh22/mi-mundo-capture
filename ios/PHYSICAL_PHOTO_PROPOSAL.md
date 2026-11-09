# First real glasses photograph — proposal only

Status: **NOT AUTHORISED TO EXECUTE**. Prepared for Zara/Lindsey/Stephen review.
The simulator configuration is deliberately not installable on a phone. A passing
mock is not evidence of real glasses capture, phone background operation or privacy.

## Exact target and approval record

- App ID: `app.heysophie.capture.photodev`; callback scheme `heysophie-meta-dev`, DAT `AppLinkURLScheme` = `heysophie-meta-dev://`.
- Mac: Stephen's existing Mac, macOS 26.6.2 / Xcode 27.1 (27A9275) / Swift 6.4, as verified in simulator development.
- Target: **Stephen's iPhone already paired to his Meta Ray-Ban Display glasses**. Exact model, iOS, private UDID, Meta AI version and glasses firmware are not verified. Record them privately before approval; do not choose a different phone automatically.
- SDK: DAT 1.0.1, exact revision `0bd369298eef6a980ad0bdb6c8a5502f2c02a08c`; retain iOS 17.2 deployment minimum. Verify actual iPhone/toolchain compatibility, rather than installing/updating anything automatically.
- First trial: one non-sensitive printed/synthetic target, iPhone unlocked and app foreground, existing pairing, local-only save. No microphone, video, cloud intake, Neural Band UI, voice activation or locked-phone trial.
- Stephen must approve the exact reviewed physical-build commit, target phone, signing team/profile, mode/permission scope, developer registration route, data-retention/export plan and rollback. No approval is inferred from this proposal.

## Signing and installation requirements (not performed)

1. Use a reviewed **separate physical configuration** in the existing project, not the generated simulator plist. It must omit `MWDATMockDevice`, the process-proof harness, simulator flags and generated proof files, and link only Core/Camera. Retain the framework runpath `@executable_path/Frameworks`; the restart investigation found XCTest had masked its absence.
2. The current source deliberately leaves `HS_META_PHYSICAL_APPROVED` undefined. Only a separately approved revision may enable a controlled physical bridge. Before installation it needs explicit registration/camera-permission controls and truthful physical labels; the present simulator screen is not a finished physical flow. Current physical `connect` requires registration first, so simply switching a compiler flag is insufficient.
3. Select an **existing Stephen-approved Apple team** in Xcode and a valid Apple Development signing identity. A provisioning profile must cover this exact App ID, certificate and selected iPhone. The Team ID/certificate/profile and account availability have not been inspected. Do not create identities, register a device, accept agreements, invoke automatic provisioning updates or sign in to another account without approval.
4. Apple documents on-device Xcode testing with a free Personal Team, whose provisioning expires after seven days. This does not prove that a chosen team's capabilities or this configuration will sign successfully. Prefer a compatible existing account; a paid membership, TestFlight or App Store distribution is **not presumed necessary**. Any enrolment, agreement, cost or account change is a new decision.
5. Proposed installation route: one development-signed build from this Mac through Xcode to the named phone over an owner-approved connection. iPhone trust/unlock, Developer Mode (if not already enabled), any restart and developer-app trust must be deliberately approved by Stephen. Do not install a monitoring profile, VPN, root certificate or remote access agent.
6. Check whether this App ID already has an app/data container on the phone. Do not overwrite or uninstall existing unsent data. Document the exact install/update and private preservation procedure before taking action.

Apple sources: [device running](https://developer.apple.com/documentation/xcode/running-your-app-on-simulated-or-physical-devices), [Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device), [account/Personal Team requirements](https://developer.apple.com/help/account/basics/about-your-developer-account/).

## Meta registration and permission requirements

- Existing Meta AI app and glasses pairing must remain intact. Developer Mode was previously reported enabled by Stephen; that is not a new independent hardware check or authority to toggle it.
- The fixed official setup explains Developer Mode can use `MetaAppID=0` and omit production attestation credentials. Production/non-Developer-Mode distribution instead uses a Wearables Developer Center project App ID/client token and Apple Team ID. For the proposed first private developer trial, review the existing Developer Mode route first. No new Meta organization, account, project, release channel, invitation or token is created under this work.
- Populate `MWDAT.TeamID` from the approved signing team. Keep callback scheme and registration URL handling consistent. Invoke `startRegistration()` only as an explicit owner-approved step; preserve the existing app connection scope and use the SDK's `metaWearablesAction` callback filter.
- Ask for **DAT glasses-camera permission** only via the supported Meta flow. This is different from iOS permission to use the phone's camera. Do not silently substitute a phone photo, mock, image import or dictated text.
- Every unexpected prompt is a stop for review, including new Meta consent or local-network access. The owner must see the exact app and scope before granting anything. No credentials are placed in source, logs or the engineering document.

Official evidence: [fixed setup source](https://github.com/meta/meta-wearables-dat-ios/blob/bbae597cd1c748cd29b9375a1624a8d75b1c9e14/plugins/mwdat-ios/skills/getting-started/SKILL.md), [pinned package README](https://github.com/meta/meta-wearables-dat-ios/blob/1.0.1/README.md). The setup-source commit is distinct from the binary release pin. Some live developer documentation is sign-in gated; no sign-in/enrolment was attempted. Hardware-specific eligibility/project needs must be checked before the installation approval, not guessed.

## Transport and privacy review before physical-build approval

| Area | Exact documented keys/values | Decision for first trial |
| --- | --- | --- |
| Bluetooth Classic / camera stream | `UIBackgroundModes`: `external-accessory`; `UISupportedExternalAccessoryProtocols`: `com.meta.ar.wearable` | Proven necessary for the pinned mock path, not yet validated on Stephen's phone. Review this declaration afresh for physical use. It is not permission to keep capturing in background. |
| Bluetooth LE discovery | `NSBluetoothAlwaysUsageDescription` (nonempty truthful explanation); official setup lists `bluetooth-central` and `bluetooth-peripheral` modes | The mock succeeds without these; real discovery may require them. Zara/Lindsey must settle the exact physical plist diff before Stephen approves installation. Do not infer the simulator minimum is sufficient on hardware. |
| Wi-Fi link | `NSLocalNetworkUsageDescription` (nonempty); `NSBonjourServices` = [`_bonjour._tcp`] | Not needed in the successful mock. Include only if the approved real path demonstrates a need; an actual local-network prompt requires owner review. No silent fallback or automatic grant. |
| Other background activity | `processing`, `audio`, background tasks | Excluded from the first-photo proposal absent a separately demonstrated requirement. |
| Phone camera/mic/Photos/contacts | iOS purpose strings and grants for these resources | Excluded; this trial captures a glasses JPEG to the app's private container. |
| DAT analytics/crashes | `MWDAT.Analytics.OptOut=true`; `MWDAT.CrashReporting.OptOut=true` | Must be verified in the final signed app's effective plist. These settings do not disable Apple's OS diagnostics or prove zero traffic. |

The exact hardware BLE/Wi-Fi key set is an explicit **pre-install review dependency**,
not an asserted solved requirement. Do not copy the full sample's capabilities or
use the physical test as permission to broaden them. Keep complete file protection,
backup exclusion and local-only behavior; no entitlement for microphone/always-on
capture and no upload adapter. Review the bounded simulator network findings and
remaining packet-level visibility gap before proposing real-media handling.

Meta AI companion-app, glasses and Apple system traffic are outside the prototype
app's telemetry controls. Simulator sampling cannot establish their physical-device
privacy behavior. The live privacy review must retain that boundary.

## Witnessed acceptance and stop conditions

After separate approval: owner opens the foreground app, completes only approved
registration/permissions, connects existing glasses and captures the prepared target.
Record real `datCameraStream` provenance, stable capture ID, UTC request/receive/save
times, SDK device evidence only actually exposed, delivered MIME/bytes/dimensions
and SHA-256. Preserve SDK JPEG bytes; do not call them built-in camera originals
without evidence. Reopen/hash independently, terminate/relaunch and verify the same
receipt/file again. A private exported readback to the approved Mac must match if
export is authorised. Display SAVED LOCALLY / NOT BACKED UP / NOT UPLOADED only
after verification. A mock/import/phone image cannot pass this hardware trial.

Stop on any unapproved prompt, missing registration, unexpected network destination,
wrong source, checksum failure, disconnection, storage error or signing mismatch.
Preserve originals and report the exact failure; do not keep trying grants or reset
pairing. This foreground trial does not accept locked-phone/hands-free operation.

## Safe rollback (proposal, no actions taken)

1. Stop the app's camera/session and close it; stop any local test observer. Verify ordinary Meta AI/glasses use still works without changing pairing.
2. Preserve every unsent capture first. With separate export approval, copy originals + manifests/receipts to approved private Mac storage and independently verify sizes/hashes. Backup exclusion means uninstall can lose the only copy; do not uninstall before preservation is witnessed.
3. Only if authorised, remove this development app or revert to the prior approved build. Do not downgrade over incompatible data without checking the manifest version and verifying original files remain.
4. Revoke only the app-specific Meta connection/permissions newly granted for this trial, as owner-approved. Leave pre-existing Developer Mode, glasses pairing, WhatsApp routes and other applications untouched. No unpairing, device reset or factory reset.
5. Do not revoke shared signing certificates, delete developer accounts/projects or alter OS privacy settings globally. If iPhone Developer Mode was enabled solely for this trial, turning it off is a separate owner action after checking other development apps.
6. Record the resulting app/grant state, preservation proof and any remaining local data. No production deployment or cloud cleanup is part of rollback.
