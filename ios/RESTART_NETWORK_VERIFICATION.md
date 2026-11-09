# Normal process restart and bounded network observation

Verified 9 November 2026, using the existing Mac/iPhone 18 Pro iOS 27.0 simulator.
This is synthetic simulator development; no phone or glasses installation occurred.
SDK remains DAT 1.0.1 at `0bd369298eef6a980ad0bdb6c8a5502f2c02a08c`.

## Failures exposed and corrected

A normal app launch initially aborted before SDK initialization: dyld could not find
`@rpath/MWDATCore.framework/MWDATCore`. XCTest had supplied a search path and masked
the packaging defect. The generator now adds `$(inherited) @executable_path/Frameworks`
to the app's runtime search paths. `otool` verified that path in the built executable;
Core/Camera/Mock frameworks were present. Stephen reported four resulting crash
dialogs and ignored them. No Apple Report action, macOS/Xcode reinstallation/update or permission change
was requested; the simulator test app was rebuilt normally. Subsequent normal launches succeeded after the fix.

The initial generated configuration lacked the conventional `DEBUG` compilation
condition, so a deliberately Debug-only proof harness was not compiled. This was
corrected in DAT Debug configurations. An early view-scoped proof task was cancelled
by SwiftUI startup reconciliation, with the mock list subsequently cleared. The
explicitly invoked proof now has one process-wide owner, independent of view task
cancellation/teardown, using the same MetaPhotoCamera bridge and normal app store.
These failed attempts are not counted as restart/capture passes. The ordinary UI
capture controls are not claimed to have received a manual tap test.

## Actual process restart — PASS

The supported `simctl` lifecycle proof is `ios/checks/run_process_proof.py`.
It does not use XCTest to manufacture a restart or substitute a fixture for a
callback. `HS_META_PROOF_MODE=capture|restore` is accepted only by a Debug,
`HS_META_SIMULATOR_CONFIG`, simulator build. A separate non-simulator compile guard
remains in place. The process-wide harness is dormant unless explicitly invoked.

1. Launch a normal app process, configure official MockDeviceKit, receive an actual
   photo callback and persist through the normal `HeySophieCaptures` store.
2. Independently read its manifest and original file on the host. Verify native
   receipt, capture ID/source, byte count and SHA-256; retain file inode/mtime.
3. Explicitly terminate the app with `simctl terminate`. `ps` confirms the original
   process no longer exists. Launch a different normal process in restore mode.
4. The relaunched app uses `restoreLatest` and `verify` to reopen/decode/hash the
   original file. Restore mode does not request an SDK connection or recapture.
5. Compare the whole receipt/manifest, original file bytes and relative filename,
   capture identity, source, inode and modification time before/after. All match.
   Separate process IDs and fresh process-specific reports prevent stale output
   from passing. Native ImageIO validation and host `sips` both confirm JPEG/32x24.
6. A simulator screenshot independently shows SAVED LOCALLY / NOT BACKED UP /
   NOT UPLOADED, restored datMock source, receipt and matching digest. The test
   app is stopped afterward; data is preserved. No app uninstall or reset.

Verified photo: **901 bytes, 32x24, JPEG, source datMock**, SHA-256:
`4636673a5769f5332119e1ecbb6f75aa3eee6c6d83c5ed9ef392bdff1e674dd3`.
The input fixture is still 742 bytes. Output equality is with the actual SDK
callback, not an assumed byte-identical input JPEG.

Private evidence directory: `/private/tmp/hs-meta-001-process-proof-final`.
It contains the normal-process summary, capture/restore reports, restored screen,
verified original JPEG, manifest/receipt and counter/socket observations. The
capture/restore IDs and synthetic SDK identifiers remain private, not committed.
Host output directory was created with mode 0700. App proof metadata is atomically
written with complete file protection and excluded from backup, just as the
original capture protection boundary remains unchanged.

## Runtime network observation — bounded result, not zero-egress proof

Only existing `nettop`, `lsof`, `ps` and `simctl` were used. No monitoring tool,
proxy, VPN, certificate, packet payload capture or system permission was installed
or granted. `tcpdump`'s app-filtered pktap probe failed with
`ioctl(SIOCIFCREATE): Operation not permitted`; no sudo/root retry or permission
change was attempted. Packet-level trace/definitive attribution remains BLOCKED
under current privileges, rather than silently expanding inspection.

Collectors start before launch and use numeric addresses (no observer DNS lookup).
`nettop` samples process TCP/UDP counters once per second; `lsof` samples app-owned
Internet sockets roughly twice per second. Selected system-process counter
summaries provide a control, not unrestricted browsing/packet inspection. Known
helper executable paths were checked to distinguish host from simulator processes.
No package resolution/build occurred inside these observation windows.

| Window | Duration / nettop samples | App flow rows | lsof observations with app Internet sockets |
| --- | --- | --- | --- |
| App stopped / OS baseline | 15 seconds / 15 | 0 | App not running |
| Normal DAT capture + idle | 30 seconds / 30 | 0 | 0 of 58 |
| Normal storage-only relaunch | 20 seconds / 20 | 0 | 0 of 39 |

Observed system counter deltas (in/out bytes between first/last sampled counters):

| Process | Baseline | Capture window | Restore window |
| --- | --- | --- | --- |
| macOS mDNSResponder | 2565 / 2857 | 7325 / 2217 | 1625 / 579 |
| macOS nsurlsessiond | Not present in selected rows | 24753 / 22447 | 5 / 290 |
| macOS apsd | 0 / 0 | 0 / 0 | 0 / 0 |
| Simulator apsd | 0 / 0 | 0 / 0 | 0 / 0 |

Multiple host nsurlsessiond instances can appear; values here summarize the
observed changing counters, not all host traffic or a causal link to capture.
Host mDNS/background URLSession service activity is distinct from an app-owned
flow. Its contents/initiating client were not inspected; timing alone does not
attribute it to Meta telemetry. No app-owned telemetry/crash/media-upload flow
was observed in these bounded windows. The effective installed app plist was
independently read: Analytics.OptOut=true, CrashReporting.OptOut=true, only the
external-accessory mode, no phone purpose strings. Static opt-outs alone are
not used as network proof.

Limitations: short-lived, delegated or unobserved flows, DNS attribution, encrypted
payload purpose and other system traffic cannot be ruled out by counter/socket
sampling. The SDK shares the app process, so these data cannot separate an app
call from an SDK call if one occurs. OS crash diagnostics generated by the initial
launch failure are separate from the SDK's crash opt-out. No Apple report was
submitted by this workflow; OS reporting policy itself was not changed or audited.
No claim of zero telemetry, zero egress, packet-level privacy acceptance or physical
transport/media privacy is made. Any stronger capture requiring root/new inspection
permissions needs a concrete separate approval. No new permission grant was made.

## Reproduction and regression

```sh
HS_META_SIMULATOR_PROFILE=accessory-required HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-compare ios/checks/run_simulator.sh SIMULATOR_UUID --dat
python3 ios/checks/run_process_proof.py SIMULATOR_UUID --output /private/tmp/hs-meta-001-process-proof-final
HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-restart-offline ios/checks/run_simulator.sh SIMULATOR_UUID
HS_META_SIMULATOR_PROFILE=accessory-required HS_META_DERIVED_DATA_PATH=/private/tmp/hs-meta-001-compare ios/checks/run_simulator.sh SIMULATOR_UUID --dat
```

Use a fresh private output directory when reproducing observations. Simulator test
installation is confined to the existing simulator; no physical install command
is part of the process-proof script. The script retains originals and does not
clear the app container. Existing captures must not be deleted to reset a run.

A second end-to-end run of the finished script also passed, retaining originals,
manifest and receipt directly at `/private/tmp/hs-meta-001-restart-evidence-final`.
The repeat likewise observed no app flow rows or sampled app sockets. The numeric
comparison table above refers to the first verified run, whose logs remain intact.

Final offline regression: **19 tests, zero failures**, exit 0. Final DAT regression:
**20 tests, zero failures**, exit 0. No XCTest assertion skipped/weakened; SDK pin,
fixtures and existing bridge/test deadlines unchanged. Python/shell syntax and
whitespace checks are also required before publication.

Regression result bundles:
`/private/tmp/hs-meta-001-restart-offline/Logs/Test/Test-HeySophie-2026.11.09_16-25-58-+0000.xcresult`
and `/private/tmp/hs-meta-001-compare/Logs/Test/Test-HeySophie-2026.11.09_16-27-39-+0000.xcresult`.

Logs: `/private/tmp/hs-meta-001-restart-offline-final.log` and
`/private/tmp/hs-meta-001-restart-dat-complete.log`.

Next: review [the physical-photo proposal](PHYSICAL_PHOTO_PROPOSAL.md). It is a
requirements/rollback document only, with actual phone identity and signing team
explicitly unverified approval inputs. The physical compile flag remains undefined;
no physical transport profile, account enrolment, signing permission, iPhone
installation, Meta setting change, real media, Railway access or deployment was
performed. PR #17 remains draft and unmerged.
